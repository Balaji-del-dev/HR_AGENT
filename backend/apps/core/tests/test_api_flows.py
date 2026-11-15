"""The API as the React app uses it: uploads, agent runs, approvals, permissions, cross-tenant isolation."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.tenancy import tenant_scope
from apps.core.tests.scenario import add_candidate, approved_requisition, resume_pdf, run_queued, staff
from apps.governance.models import DataAccessLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def acme(tenant_a, make_member):
    people = staff(tenant_a, make_member)
    return {"tenant": tenant_a, "people": people, "requisition": approved_requisition(tenant_a, people)}


def test_upload_link_pipeline_spans_and_logged_download(acme, client_for, django_capture_on_commit_callbacks) -> None:
    tenant, people = acme["tenant"], acme["people"]
    client = client_for(people["recruiter"])
    candidate = client.post(
        "/api/v1/candidates/", {"full_name": "Kiran Shah", "email": "kiran@example.com"}, format="json"
    ).json()
    client.post(
        "/api/v1/applications/",
        {"requisition_id": str(acme["requisition"].id), "candidate_id": candidate["id"]},
        format="json",
    )
    link = client.post(
        f"/api/v1/candidates/{candidate['id']}/documents/upload-url/",
        {"filename": "kiran.pdf", "content_type": "application/pdf"},
        format="json",
    )
    assert link.status_code == 201
    upload_url, document_id = link.json()["upload_url"], link.json()["document_id"]

    pdf = resume_pdf("Kiran Shah", "kiran@example.com")
    assert (
        client.post(upload_url, {"file": SimpleUploadedFile("kiran.pdf", pdf)}, format="multipart").status_code == 200
    )
    # The link is single use.
    assert (
        client.post(upload_url, {"file": SimpleUploadedFile("kiran.pdf", pdf)}, format="multipart").status_code == 409
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(f"/api/v1/documents/{document_id}/complete/").status_code == 202
    assert client.get(f"/api/v1/documents/{document_id}/").json()["status"] == "processed"
    spans = client.get(f"/api/v1/documents/{document_id}/spans/").json()
    assert any("FastAPI" in s["text_masked"] for s in spans)
    assert all("Kiran" not in s["text_masked"] for s in spans)

    download = client.post(f"/api/v1/documents/{document_id}/download-url/").json()
    response = client.get(download["url"])
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    with tenant_scope(tenant.id):
        assert DataAccessLog.objects.filter(target_id=document_id, action="download").exists()

    # Signed links are bound to the user they were issued to, even inside the same tenant.
    assert client_for(people["admin"]).get(download["url"]).status_code == 404


def test_agent_run_endpoints_resume_and_stale_answers(acme, client_for) -> None:
    tenant, people = acme["tenant"], acme["people"]
    client = client_for(people["recruiter"])
    response = client.post(f"/api/v1/requisitions/{acme['requisition'].id}/jd-drafts/", {}, format="json")
    assert response.status_code == 202 and response.json()["status"] == "queued"
    run_id = response.json()["id"]
    run_queued(tenant)

    run = client.get(f"/api/v1/agent-runs/{run_id}/").json()
    assert run["status"] == "awaiting_review"
    assert [s["node"] for s in run["steps"]][:2] == ["guard_input", "supervisor"]
    assert run["tool_calls"] and all(c["status"] == "ok" for c in run["tool_calls"])
    approval_id = run["pending_interrupt"]["approval_request_id"]

    approvals = client.get("/api/v1/approvals/", {"status": "pending"}).json()["results"]
    assert approval_id in {a["id"] for a in approvals}
    assert next(a for a in approvals if a["id"] == approval_id)["can_decide"] is True

    stale = client.post(
        f"/api/v1/agent-runs/{run_id}/resume/",
        {"approval_request_id": "00000000-0000-0000-0000-000000000000", "decision": "approve"},
        format="json",
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_resume"

    reject = client.post(f"/api/v1/approvals/{approval_id}/decide/", {"decision": "reject"}, format="json")
    assert reject.status_code == 400  # a rejection needs a reason
    ok = client.post(
        f"/api/v1/agent-runs/{run_id}/resume/",
        {"approval_request_id": approval_id, "decision": "reject", "reason": "Too generic"},
        format="json",
    )
    assert ok.status_code == 202
    again = client.post(f"/api/v1/approvals/{approval_id}/decide/", {"decision": "approve"}, format="json")
    assert again.status_code == 409


def test_interviewer_cannot_start_runs_or_see_unassigned_candidates(acme, client_for) -> None:
    tenant, people = acme["tenant"], acme["people"]
    candidate, _, _ = add_candidate(tenant, people, acme["requisition"], name="Lena Park", email="lena@example.com")
    client = client_for(people["interviewer"])
    # The role check comes first and does not depend on the id, so nothing leaks.
    assert (
        client.post(f"/api/v1/requisitions/{acme['requisition'].id}/match-runs/", {}, format="json").status_code == 403
    )
    assert client.get(f"/api/v1/candidates/{candidate.id}/").status_code == 404
    response = client.post(
        "/api/v1/agent-runs/",
        {"kind": "matching", "params": {"requisition_id": str(acme["requisition"].id)}},
        format="json",
    )
    assert response.status_code == 403


def test_hiring_manager_sees_candidates_without_contact_details(acme, client_for) -> None:
    tenant, people = acme["tenant"], acme["people"]
    candidate, _, _ = add_candidate(tenant, people, acme["requisition"], name="Maya Iyer", email="maya@example.com")
    as_manager = client_for(people["manager"]).get(f"/api/v1/candidates/{candidate.id}/").json()
    assert as_manager["full_name"] == "Maya Iyer" and as_manager["email"] == "" and as_manager["phone"] == ""
    as_recruiter = client_for(people["recruiter"]).get(f"/api/v1/candidates/{candidate.id}/").json()
    assert as_recruiter["email"] == "maya@example.com"
    with tenant_scope(tenant.id):
        assert DataAccessLog.objects.filter(target_id=str(candidate.id), action="view").count() == 2


def test_other_tenant_sees_404_everywhere(acme, tenant_b, make_member, client_for) -> None:
    tenant, people = acme["tenant"], acme["people"]
    candidate, application, document = add_candidate(
        tenant, people, acme["requisition"], name="Noor Ali", email="noor@example.com"
    )
    run_queued(tenant)
    outsider = client_for(make_member(tenant_b, "hr_admin", "recruiter", "auditor"))
    with tenant_scope(tenant.id):
        from apps.agents.models import AgentRun
        from apps.approvals.models import ApprovalRequest

        run = AgentRun.objects.first()
        approval = ApprovalRequest.objects.first()
    for url in (
        f"/api/v1/candidates/{candidate.id}/",
        f"/api/v1/applications/{application.id}/",
        f"/api/v1/documents/{document.id}/",
        f"/api/v1/documents/{document.id}/spans/",
        f"/api/v1/agent-runs/{run.id}/",
        f"/api/v1/approvals/{approval.id}/",
        f"/api/v1/requisitions/{acme['requisition'].id}/assessments/",
    ):
        assert outsider.get(url).status_code == 404, url
    assert outsider.get("/api/v1/candidates/").json()["count"] == 0
    assert outsider.get("/api/v1/audit-events/").json()["count"] == 0


def test_audit_log_is_for_hr_admins_and_auditors_only(acme, client_for) -> None:
    people = acme["people"]
    assert client_for(people["auditor"]).get("/api/v1/audit-events/").status_code == 200
    assert client_for(people["admin"]).get("/api/v1/audit-events/").json()["count"] > 0
    assert client_for(people["recruiter"]).get("/api/v1/audit-events/").status_code == 403


def test_login_locks_out_after_repeated_failures(acme, settings) -> None:
    from apps.accounts.models import User

    user = User.objects.create_user(username="lockme", email="lock@example.com", password="right-password-123")
    client = APIClient(enforce_csrf_checks=False)
    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert client.post(
            "/api/v1/auth/login/", {"username": "lockme", "password": "wrong"}, format="json"
        ).status_code in (401, 403, 429)
    locked = client.post("/api/v1/auth/login/", {"username": "lockme", "password": "right-password-123"}, format="json")
    assert locked.status_code != 200
    assert user.is_active


def test_login_and_me(acme) -> None:
    from apps.accounts.models import User

    User.objects.create_user(username="sam", email="sam@example.com", password="right-password-123")
    client = APIClient()
    assert client.get("/api/v1/auth/me/").status_code == 403
    response = client.post("/api/v1/auth/login/", {"username": "sam", "password": "right-password-123"}, format="json")
    assert response.status_code == 200 and response.json()["username"] == "sam"
    assert client.get("/api/v1/auth/me/").json()["memberships"] == []


def test_scorecards_only_from_panelists(acme, client_for) -> None:
    from apps.applications.services import record_decision
    from apps.core.tests.scenario import ctx_for
    from apps.interviews.scheduling import Interval
    from apps.interviews.services import confirm_slot, create_interview, propose_slots

    tenant, people = acme["tenant"], acme["people"]
    _, application, _ = add_candidate(tenant, people, acme["requisition"], name="Omar Haddad", email="omar@example.com")
    ctx = ctx_for(people["recruiter"], tenant)
    from datetime import timedelta

    from django.utils import timezone

    with tenant_scope(tenant.id):
        record_decision(ctx, application_id=application.id, decision="advance", to_stage="shortlisted", reason="ok")
        interview = create_interview(
            ctx, application_id=application.id, title="Tech", panel_user_ids=[people["interviewer"].pk]
        )
        start = timezone.now() + timedelta(days=2)
        slot = propose_slots(
            ctx, interview_id=interview.id, slots=[Interval(start, start + timedelta(hours=1))], run_id=None
        )[0]
        confirm_slot(ctx, interview_id=interview.id, slot_id=slot.id)
    card = {"recommendation": "yes", "ratings": {"Python": 4}, "strengths": "Clear API design."}
    assert (
        client_for(people["manager"])
        .post(f"/api/v1/interviews/{interview.id}/scorecards/", card, format="json")
        .status_code
        == 403
    )
    assert (
        client_for(people["interviewer"])
        .post(f"/api/v1/interviews/{interview.id}/scorecards/", card, format="json")
        .status_code
        == 201
    )
    assert client_for(people["interviewer"]).get("/api/v1/interviews/", {"mine": "true"}).json()["count"] == 1
