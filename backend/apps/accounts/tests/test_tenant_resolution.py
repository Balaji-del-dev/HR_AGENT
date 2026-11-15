"""How a request picks its tenant: membership decides, never the client alone."""

import uuid

import pytest

from apps.accounts.roles import Role
from apps.accounts.services import build_execution_context
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.core.exceptions import TenantAccessDenied, TenantRequired

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/requisitions/"


def test_single_membership_is_used_without_a_header(tenant_a, make_member) -> None:
    user = make_member(tenant_a, Role.RECRUITER, Role.INTERVIEWER)
    ctx = build_execution_context(user_id=user.pk, requested_tenant_id=None, request_id="r1")
    assert ctx.tenant_id == tenant_a.id
    assert ctx.roles == frozenset({"recruiter", "interviewer"})
    assert ctx.request_id == "r1"


def test_several_memberships_require_the_header(tenant_a, tenant_b, make_member) -> None:
    user = make_member(tenant_a, Role.RECRUITER)
    make_member(tenant_b, Role.HR_ADMIN, user=user)
    with pytest.raises(TenantRequired):
        build_execution_context(user_id=user.pk, requested_tenant_id=None)
    ctx = build_execution_context(user_id=user.pk, requested_tenant_id=tenant_b.id)
    assert ctx.roles == frozenset({"hr_admin"})  # roles come from the chosen tenant only


@pytest.mark.parametrize("case", ["other_tenant", "unknown_tenant", "inactive_membership", "inactive_tenant"])
def test_access_is_denied_the_same_way(case, tenant_a, tenant_b, make_member) -> None:
    user = UserFactory()
    requested = tenant_a.id
    if case == "other_tenant":
        MembershipFactory(tenant=tenant_b, user=user)
    elif case == "unknown_tenant":
        MembershipFactory(tenant=tenant_a, user=user)
        requested = uuid.uuid4()
    elif case == "inactive_membership":
        MembershipFactory(tenant=tenant_a, user=user, is_active=False)
    elif case == "inactive_tenant":
        MembershipFactory(tenant=tenant_a, user=user)
        tenant_a.is_active = False
        tenant_a.save()

    with pytest.raises(TenantAccessDenied):
        build_execution_context(user_id=user.pk, requested_tenant_id=requested)


def test_user_with_no_membership_is_denied() -> None:
    with pytest.raises(TenantAccessDenied):
        build_execution_context(user_id=UserFactory().pk, requested_tenant_id=None)


# --- The same rules over HTTP -------------------------------------------------------------


def test_anonymous_request_is_rejected(client) -> None:
    response = client.get(LIST_URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


def test_header_for_a_foreign_tenant_is_forbidden(tenant_a, tenant_b, make_member, client_for) -> None:
    user = make_member(tenant_a, Role.HR_ADMIN)
    response = client_for(user, tenant=tenant_b).get(LIST_URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_access_denied"


def test_malformed_tenant_header_is_a_validation_error(tenant_a, make_member, client_for) -> None:
    client = client_for(make_member(tenant_a, Role.HR_ADMIN))
    response = client.get(LIST_URL, HTTP_X_TENANT_ID="acme")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_multi_tenant_user_without_header_gets_tenant_required(tenant_a, tenant_b, make_member, client_for) -> None:
    user = make_member(tenant_a, Role.RECRUITER)
    make_member(tenant_b, Role.RECRUITER, user=user)
    response = client_for(user).get(LIST_URL)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "tenant_required"


def test_error_body_carries_the_request_id(tenant_a, make_member, client_for) -> None:
    user = make_member(tenant_a, Role.RECRUITER)
    response = client_for(user).get(LIST_URL, HTTP_X_TENANT_ID=str(uuid.uuid4()), HTTP_X_REQUEST_ID="trace-abc-123")
    assert response.json()["error"]["request_id"] == "trace-abc-123"
