"""Job descriptions: versioned drafts, approval, and the requirement rows matching uses."""

from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.roles import Role
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.jobs.inclusive import check_inclusive_language
from apps.jobs.models import JDTemplate, JobDescription, JobRequirement
from apps.jobs.selectors import get_visible_jd
from apps.requisitions.models import JobRequisition
from apps.requisitions.selectors import get_visible_requisition

LEVELS = set(JobRequirement.Level.values)


def normalize_requirements(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim, de-duplicate and validate requirement dicts from a person or a model."""
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        name = " ".join(str(item.get("name", "")).split())[:120]
        level = str(item.get("level", "required")).lower()
        if not name or name.lower() in seen:
            continue
        if level not in LEVELS:
            level = JobRequirement.Level.REQUIRED
        aliases = [" ".join(str(alias).split())[:80] for alias in item.get("aliases", []) if str(alias).strip()]
        seen.add(name.lower())
        cleaned.append({"name": name, "level": level, "aliases": aliases[:8]})
    return cleaned


def compliance_flags_for(*, title: str, summary: str, body: str, responsibilities: list[str]) -> list[dict[str, Any]]:
    text = "\n".join([title, summary, body, *responsibilities])
    return [flag.as_dict() for flag in check_inclusive_language(text)]


def create_jd_draft(
    ctx: ExecutionContext,
    *,
    requisition_id: UUID,
    title: str,
    summary: str = "",
    responsibilities: list[str] | None = None,
    requirements: list[dict[str, Any]] | None = None,
    body: str = "",
    agent_run_id: UUID | None = None,
    prompt_version: str = "",
) -> JobDescription:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins write JDs.")
    with transaction.atomic():
        requisition = get_visible_requisition(ctx, requisition_id, for_update=True)
        if requisition.status in (JobRequisition.Status.CLOSED, JobRequisition.Status.REJECTED):
            raise InvalidStateTransition("This requisition is not open.")
        version = (requisition.job_descriptions.aggregate(v=Max("version"))["v"] or 0) + 1
        responsibilities = [str(item).strip() for item in (responsibilities or []) if str(item).strip()]
        jd = JobDescription.objects.create(
            requisition=requisition,
            version=version,
            title=title[:200],
            summary=summary,
            responsibilities=responsibilities,
            requirements=normalize_requirements(requirements or []),
            body=body,
            compliance_flags=compliance_flags_for(
                title=title, summary=summary, body=body, responsibilities=responsibilities
            ),
            created_by_id=ctx.user_id,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
        )
        record_audit(
            ctx,
            action="jd.drafted",
            target_type="job_description",
            target_id=jd.id,
            details={"version": version, "by_agent": agent_run_id is not None},
        )
    return jd


def update_jd_draft(ctx: ExecutionContext, *, jd_id: UUID, **changes: Any) -> JobDescription:
    require_active_tenant(ctx.tenant_id)
    allowed = {"title", "summary", "responsibilities", "requirements", "body"}
    if set(changes) - allowed:
        raise ApplicationError(f"Cannot edit {sorted(set(changes) - allowed)}.")
    with transaction.atomic():
        jd = get_visible_jd(ctx, jd_id, for_update=True)
        if jd.status != JobDescription.Status.DRAFT:
            raise InvalidStateTransition("Only drafts can be edited; approval edits go through the approval.")
        _apply_edits(jd, changes)
        jd.save()
    return jd


def _apply_edits(jd: JobDescription, edits: dict[str, Any]) -> None:
    for field in ("title", "summary", "body"):
        if field in edits:
            setattr(jd, field, str(edits[field]))
    if "responsibilities" in edits:
        jd.responsibilities = [str(item).strip() for item in edits["responsibilities"] if str(item).strip()]
    if "requirements" in edits:
        jd.requirements = normalize_requirements(edits["requirements"])
    jd.compliance_flags = compliance_flags_for(
        title=jd.title, summary=jd.summary, body=jd.body, responsibilities=jd.responsibilities
    )


def submit_jd_for_approval(
    ctx: ExecutionContext, *, jd_id: UUID, agent_run_id: UUID | None = None, review_round: int = 1
) -> ApprovalRequest:
    from apps.approvals.services import open_request

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        jd = get_visible_jd(ctx, jd_id, for_update=True)
        if jd.status != JobDescription.Status.DRAFT:
            raise InvalidStateTransition("Only drafts can be sent for approval.")
        if not jd.requirements:
            raise ApplicationError("A JD needs at least one requirement before approval.")
        jd.status = JobDescription.Status.PENDING_APPROVAL
        jd.save(update_fields=["status", "updated_at"])
        return open_request(
            ctx,
            kind=ApprovalRequest.Kind.JOB_DESCRIPTION,
            target_id=jd.id,
            title=f"Approve JD: {jd.title} (v{jd.version})",
            summary=f"{len(jd.requirements)} requirements · {len(jd.compliance_flags)} language flags",
            payload={
                "job_description_id": str(jd.id),
                "requisition_id": str(jd.requisition_id),
                "version": jd.version,
                "title": jd.title,
                "summary": jd.summary,
                "responsibilities": jd.responsibilities,
                "requirements": jd.requirements,
                "body": jd.body,
                "compliance_flags": jd.compliance_flags,
            },
            required_roles=[Role.RECRUITER, Role.HR_ADMIN],
            requisition_id=jd.requisition_id,
            agent_run_id=agent_run_id,
            review_round=review_round,
        )


def on_jd_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    jd = JobDescription.objects.select_for_update().filter(pk=request.target_id).first()
    if jd is None:
        raise NotFound("Job description not found.")
    if jd.status != JobDescription.Status.PENDING_APPROVAL:
        raise InvalidStateTransition("This JD is no longer waiting for approval.")
    if decision.decision == ApprovalDecision.Decision.APPROVE:
        if decision.edits:
            _apply_edits(jd, decision.edits)
        approve_jd(ctx, jd)
    else:
        jd.status = JobDescription.Status.REJECTED
        jd.save(update_fields=["status", "updated_at"])
    return True


def approve_jd(ctx: ExecutionContext, jd: JobDescription) -> JobDescription:
    """Make this version the requisition's approved JD and rebuild its requirement rows."""
    if not jd.requirements:
        raise ApplicationError("A JD needs at least one requirement before approval.")
    JobDescription.objects.filter(requisition_id=jd.requisition_id, status=JobDescription.Status.APPROVED).exclude(
        pk=jd.pk
    ).update(status=JobDescription.Status.SUPERSEDED)
    jd.status = JobDescription.Status.APPROVED
    jd.approved_by_id = ctx.user_id
    jd.approved_at = timezone.now()
    jd.save()
    JobRequirement.objects.bulk_create(
        [
            JobRequirement(
                tenant_id=jd.tenant_id,
                job_description=jd,
                requisition_id=jd.requisition_id,
                name=item["name"],
                level=item["level"],
                aliases=item.get("aliases", []),
                position=index,
            )
            for index, item in enumerate(jd.requirements)
        ]
    )
    record_audit(
        ctx,
        action="jd.approved",
        target_type="job_description",
        target_id=jd.id,
        details={"version": jd.version, "requirements": len(jd.requirements)},
    )
    return jd


def create_template(ctx: ExecutionContext, *, name: str, body: str, department: str = "") -> JDTemplate:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN):
        raise PolicyDenied("Only HR admins manage JD templates.")
    return JDTemplate.objects.create(name=name, body=body, department=department)
