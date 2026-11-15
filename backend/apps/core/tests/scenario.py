"""Builders for realistic test data, created through the real services (not raw ORM writes)."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.accounts.services import build_execution_context
from apps.approvals.models import ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope
from document_ai.pdf import make_pdf

RESUME_LINES = [
    "{name}",
    "{email} | +91 98765 43210 | linkedin.com/in/someone",
    "Summary",
    "Backend engineer who builds reliable APIs and data pipelines.",
    "Experience",
    "Senior Engineer, Acme Labs 2021-2024",
    "Built FastAPI services in Python and ran them on AWS.",
    "Designed LangGraph agents for document review.",
    "Engineer, Beta Systems 2018-2021",
    "Maintained Django apps and PostgreSQL databases.",
    "Education",
    "B.Tech, Anna University 2018",
    "Skills",
    "Python, FastAPI, Django, PostgreSQL, AWS, LangGraph",
]


def resume_pdf(name: str, email: str, extra: Iterable[str] = (), **kwargs: Any) -> bytes:
    lines = [line.format(name=name, email=email) for line in RESUME_LINES] + list(extra)
    return make_pdf(lines, **kwargs)


def ctx_for(user: Any, tenant: Tenant) -> ExecutionContext:
    return build_execution_context(user_id=user.pk, requested_tenant_id=tenant.id)


def staff(tenant: Tenant, make_member: Any) -> dict[str, Any]:
    return {
        "admin": make_member(tenant, "hr_admin"),
        "admin2": make_member(tenant, "hr_admin"),
        "recruiter": make_member(tenant, "recruiter"),
        "manager": make_member(tenant, "hiring_manager"),
        "interviewer": make_member(tenant, "interviewer"),
        "finance": make_member(tenant, "finance_approver"),
        "auditor": make_member(tenant, "auditor"),
    }


def approved_requisition(
    tenant: Tenant, people: dict[str, Any], *, must: list[str] | None = None, nice: list[str] | None = None
) -> Any:
    """A requisition approved by HR with an approved JD (requirements built from must/nice)."""
    from apps.approvals.services import decide
    from apps.jobs.services import approve_jd, create_jd_draft
    from apps.requisitions.services import create_comp_band, create_requisition, submit_requisition

    must = must if must is not None else ["Python", "FastAPI", "LangGraph", "RAG"]
    nice = nice if nice is not None else ["AWS"]
    admin_ctx = ctx_for(people["admin"], tenant)
    recruiter_ctx = ctx_for(people["recruiter"], tenant)
    with tenant_scope(tenant.id):
        band = create_comp_band(
            admin_ctx,
            department="Engineering",
            level="L4",
            min_salary=Decimal("2000000"),
            max_salary=Decimal("3000000"),
        )
        requisition = create_requisition(
            recruiter_ctx,
            title="Senior Backend Engineer",
            department="Engineering",
            location="Chennai",
            level="L4",
            summary="We need an engineer to build the agent platform's APIs and pipelines for HR teams.",
            must_have_skills=must,
            nice_to_have_skills=nice,
            comp_band_id=band.id,
            hiring_manager_id=people["manager"].pk,
        )
        submit_requisition(recruiter_ctx, requisition_id=requisition.id)
        approval = ApprovalRequest.objects.get(target_id=requisition.id, kind="requisition")
        decide(admin_ctx, request_id=approval.id, decision="approve")
        requirements = [{"name": s, "level": "mandatory"} for s in must] + [
            {"name": s, "level": "preferred"} for s in nice
        ]
        jd = create_jd_draft(
            recruiter_ctx,
            requisition_id=requisition.id,
            title=requisition.title,
            summary=requisition.summary,
            responsibilities=["Build APIs"],
            requirements=requirements,
            body="# JD",
        )
        approve_jd(recruiter_ctx, jd)
        requisition.refresh_from_db()
    return requisition


def add_candidate(
    tenant: Tenant,
    people: dict[str, Any],
    requisition: Any,
    *,
    name: str,
    email: str,
    pdf: bytes | None = None,
    talent_pool: bool = False,
) -> tuple[Any, Any, Any]:
    """Candidate + application + a processed resume (pipeline run synchronously). Returns (candidate, app, doc)."""
    from apps.applications.services import create_application
    from apps.candidates.services import create_candidate
    from apps.documents.services import receive_upload, request_upload
    from apps.documents.tasks import process_document

    ctx = ctx_for(people["recruiter"], tenant)
    with tenant_scope(tenant.id):
        candidate = create_candidate(ctx, full_name=name, email=email, talent_pool_consent=talent_pool)
        application = (
            create_application(ctx, requisition_id=requisition.id, candidate_id=candidate.id) if requisition else None
        )
        document, link = request_upload(ctx, candidate_id=candidate.id, filename="resume.pdf")
        token = link.url.rstrip("/").split("/")[-1]
        receive_upload(ctx, token=token, data=pdf or resume_pdf(name, email))
        document.refresh_from_db()
        document.status = "processing"
        document.save(update_fields=["status"])
    process_document(document_id=str(document.id), tenant_id=str(tenant.id))
    with tenant_scope(tenant.id):
        document.refresh_from_db()
    return candidate, application, document


def run_queued(tenant: Tenant) -> list[str]:
    """Execute every queued run of the tenant synchronously (what the worker would do)."""
    from agent_engine.runtime import execute_queued

    return execute_queued(tenant.id)


def decide_and_resume(
    tenant: Tenant, user: Any, request_id: UUID, decision: str, *, reason: str = "", edits: dict[str, Any] | None = None
) -> str | None:
    """Decide an approval as ``user`` and, if that resumed a run, execute the resume synchronously."""
    from agent_engine.runtime import execute_run
    from apps.approvals.services import decide

    ctx = ctx_for(user, tenant)
    captured: list[dict[str, Any]] = []
    import apps.core.tasks as core_tasks

    original = core_tasks.enqueue_on_commit

    def capture(task: Any, ctx: ExecutionContext, *args: Any, **kwargs: Any) -> None:
        if task.name.endswith("resume_graph"):
            captured.append(kwargs)
        else:
            original(task, ctx, *args, **kwargs)

    import agent_engine.runtime as runtime

    runtime.enqueue_on_commit = capture  # type: ignore[assignment]
    try:
        with tenant_scope(tenant.id):
            decide(ctx, request_id=request_id, decision=decision, reason=reason, edits=edits or {})
    finally:
        runtime.enqueue_on_commit = original  # type: ignore[assignment]
    if not captured:
        return None
    return execute_run(UUID(captured[0]["run_id"]), tenant.id, resume=captured[0]["decision"])
