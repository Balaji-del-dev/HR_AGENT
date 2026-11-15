"""
Requisition permissions, end to end through the API.

Roles (from the plan): HR admins see every requisition in their tenant,
recruiters only the ones assigned to them, hiring managers their own.
Interviewers, finance approvers and auditors see none.
"""

import pytest

from apps.accounts.roles import Role
from apps.core.tenancy import tenant_scope
from apps.requisitions.models import JobRequisition, RequisitionAssignment
from apps.requisitions.tests.factories import JobRequisitionFactory, RequisitionAssignmentFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/requisitions/"


def detail_url(requisition: JobRequisition) -> str:
    return f"{LIST_URL}{requisition.pk}/"


def ids(response) -> set[str]:
    return {row["id"] for row in response.json()["results"]}


@pytest.fixture
def acme(tenant_a, make_member):
    """One tenant with a person in each role and two requisitions."""
    people = {
        "admin": make_member(tenant_a, Role.HR_ADMIN),
        "recruiter": make_member(tenant_a, Role.RECRUITER),
        "other_recruiter": make_member(tenant_a, Role.RECRUITER),
        "manager": make_member(tenant_a, Role.HIRING_MANAGER),
        "interviewer": make_member(tenant_a, Role.INTERVIEWER),
        "auditor": make_member(tenant_a, Role.AUDITOR),
    }
    assigned = JobRequisitionFactory(tenant=tenant_a, hiring_manager=people["manager"])
    unassigned = JobRequisitionFactory(tenant=tenant_a)
    RequisitionAssignmentFactory(tenant=tenant_a, requisition=assigned, user=people["recruiter"])
    return {**people, "assigned": assigned, "unassigned": unassigned}


# --- Visibility --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("person", "expected"),
    [
        ("admin", {"assigned", "unassigned"}),
        ("recruiter", {"assigned"}),
        ("other_recruiter", set()),
        ("manager", {"assigned"}),
        ("interviewer", set()),
        ("auditor", set()),
    ],
)
def test_list_shows_only_what_the_role_allows(acme, client_for, person, expected) -> None:
    response = client_for(acme[person]).get(LIST_URL)
    assert response.status_code == 200
    assert ids(response) == {str(acme[name].pk) for name in expected}


def test_hidden_requisition_is_404_not_403(acme, client_for) -> None:
    response = client_for(acme["other_recruiter"]).get(detail_url(acme["assigned"]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_other_tenants_admin_cannot_see_or_touch_acme(acme, tenant_b, make_member, client_for) -> None:
    globex_admin = make_member(tenant_b, Role.HR_ADMIN)
    JobRequisitionFactory(tenant=tenant_b)
    client = client_for(globex_admin)

    assert str(acme["assigned"].pk) not in ids(client.get(LIST_URL))
    assert client.get(detail_url(acme["assigned"])).status_code == 404
    assert client.post(f"{detail_url(acme['assigned'])}submit/").status_code == 404


def test_list_filters_by_status(acme, client_for) -> None:
    with tenant_scope(acme["unassigned"].tenant_id):
        JobRequisition.objects.filter(pk=acme["unassigned"].pk).update(status=JobRequisition.Status.SUBMITTED)
    response = client_for(acme["admin"]).get(LIST_URL, {"status": "submitted"})
    assert ids(response) == {str(acme["unassigned"].pk)}


# --- Create ------------------------------------------------------------------------------------


def _payload(manager, **overrides):
    return {"title": "ML Engineer", "department": "AI", "hiring_manager_id": str(manager.pk), **overrides}


def test_recruiter_creates_and_is_auto_assigned(acme, tenant_a, client_for) -> None:
    response = client_for(acme["recruiter"]).post(LIST_URL, _payload(acme["manager"]), format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "draft"
    assert body["created_by_id"] == str(acme["recruiter"].pk)
    assert body["assigned_recruiter_ids"] == [str(acme["recruiter"].pk)]
    with tenant_scope(tenant_a.id):
        assert JobRequisition.objects.get(pk=body["id"]).tenant_id == tenant_a.id


def test_tenant_in_the_payload_is_ignored(acme, tenant_a, tenant_b, client_for) -> None:
    payload = _payload(acme["manager"], tenant_id=str(tenant_b.id), tenant=str(tenant_b.id))
    response = client_for(acme["admin"]).post(LIST_URL, payload, format="json")
    assert response.status_code == 201
    assert "tenant_id" not in response.json()
    with tenant_scope(tenant_a.id):
        assert JobRequisition.objects.filter(pk=response.json()["id"]).exists()


@pytest.mark.parametrize("person", ["interviewer", "auditor"])
def test_roles_without_authoring_rights_cannot_create(acme, client_for, person) -> None:
    response = client_for(acme[person]).post(LIST_URL, _payload(acme["manager"]), format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_hiring_manager_must_belong_to_this_tenant(acme, tenant_b, make_member, client_for) -> None:
    outsider = make_member(tenant_b, Role.HIRING_MANAGER)
    response = client_for(acme["admin"]).post(LIST_URL, _payload(outsider), format="json")
    assert response.status_code == 400
    assert "hiring_manager_id" in response.json()["error"]["details"]


def test_invalid_payload_uses_the_standard_error_shape(acme, client_for) -> None:
    response = client_for(acme["admin"]).post(LIST_URL, _payload(acme["manager"], headcount=0), format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "headcount" in error["details"]


# --- Submit ---------------------------------------------------------------------------------


@pytest.mark.parametrize("person", ["recruiter", "manager", "admin"])
def test_people_on_the_requisition_can_submit_it(acme, client_for, person) -> None:
    response = client_for(acme[person]).post(f"{detail_url(acme['assigned'])}submit/")
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["submitted_at"] is not None


def test_submitting_twice_is_a_conflict(acme, client_for) -> None:
    client = client_for(acme["recruiter"])
    assert client.post(f"{detail_url(acme['assigned'])}submit/").status_code == 200
    response = client.post(f"{detail_url(acme['assigned'])}submit/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


# --- Assign recruiters -----------------------------------------------------------------------


def test_admin_assigns_a_recruiter_who_then_sees_it(acme, client_for) -> None:
    url = f"{detail_url(acme['unassigned'])}assignments/"
    response = client_for(acme["admin"]).post(url, {"recruiter_id": str(acme["other_recruiter"].pk)}, format="json")
    assert response.status_code == 201

    visible = ids(client_for(acme["other_recruiter"]).get(LIST_URL))
    assert visible == {str(acme["unassigned"].pk)}


def test_assigning_is_idempotent(acme, tenant_a, client_for) -> None:
    url = f"{detail_url(acme['assigned'])}assignments/"
    client = client_for(acme["admin"])
    for _ in range(2):
        assert client.post(url, {"recruiter_id": str(acme["recruiter"].pk)}, format="json").status_code == 201
    with tenant_scope(tenant_a.id):
        assert RequisitionAssignment.objects.filter(requisition=acme["assigned"]).count() == 1


def test_recruiter_cannot_assign(acme, client_for) -> None:
    url = f"{detail_url(acme['assigned'])}assignments/"
    response = client_for(acme["recruiter"]).post(url, {"recruiter_id": str(acme["other_recruiter"].pk)}, format="json")
    assert response.status_code == 403


def test_only_recruiters_of_this_tenant_can_be_assigned(acme, tenant_b, make_member, client_for) -> None:
    url = f"{detail_url(acme['assigned'])}assignments/"
    client = client_for(acme["admin"])
    outsider = make_member(tenant_b, Role.RECRUITER)
    for candidate in (acme["interviewer"], outsider):
        response = client.post(url, {"recruiter_id": str(candidate.pk)}, format="json")
        assert response.status_code == 400
