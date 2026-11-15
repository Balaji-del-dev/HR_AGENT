"""Requisition business rules. The only code that writes requisition data.

API views and agent tools both call these functions, so people and agents
pass the same tenant, permission and state checks.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.selectors import member_has_role
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.requisitions import policies
from apps.requisitions.models import CompBand, JobRequisition, RequisitionAssignment
from apps.requisitions.selectors import get_visible_requisition

EDITABLE_FIELDS = (
    "title",
    "department",
    "location",
    "level",
    "employment_type",
    "headcount",
    "summary",
    "must_have_skills",
    "nice_to_have_skills",
    "comp_band_id",
    "hiring_manager_id",
)


def _check_hiring_manager(ctx: ExecutionContext, hiring_manager_id: UUID) -> None:
    if not member_has_role(tenant_id=ctx.tenant_id, user_id=hiring_manager_id, role=Role.HIRING_MANAGER):
        raise ApplicationError(
            "The hiring manager must be an active hiring manager in this tenant.",
            details={"hiring_manager_id": ["Not a hiring manager in this tenant."]},
        )


def _check_comp_band(ctx: ExecutionContext, comp_band_id: UUID | None) -> None:
    if (
        comp_band_id is not None
        and not CompBand.objects.filter(pk=comp_band_id, tenant_id=ctx.tenant_id, is_active=True).exists()
    ):
        raise ApplicationError("Unknown comp band.", details={"comp_band_id": ["Not an active comp band."]})


def _clean_skills(values: list[str] | None) -> list[str]:
    seen: dict[str, str] = {}
    for value in values or []:
        cleaned = " ".join(str(value).split())[:80]
        if cleaned and cleaned.lower() not in seen:
            seen[cleaned.lower()] = cleaned
    return list(seen.values())


def create_requisition(
    ctx: ExecutionContext,
    *,
    title: str,
    department: str,
    hiring_manager_id: UUID,
    location: str = "",
    headcount: int = 1,
    level: str = "",
    employment_type: str = JobRequisition.EmploymentType.FULL_TIME,
    summary: str = "",
    must_have_skills: list[str] | None = None,
    nice_to_have_skills: list[str] | None = None,
    comp_band_id: UUID | None = None,
) -> JobRequisition:
    require_active_tenant(ctx.tenant_id)
    if not policies.can_create(ctx):
        raise PolicyDenied("Only HR admins, recruiters and hiring managers can create requisitions.")
    _check_hiring_manager(ctx, hiring_manager_id)
    _check_comp_band(ctx, comp_band_id)

    with transaction.atomic():
        requisition = JobRequisition.objects.create(
            title=title,
            department=department,
            location=location,
            headcount=headcount,
            level=level,
            employment_type=employment_type,
            summary=summary,
            must_have_skills=_clean_skills(must_have_skills),
            nice_to_have_skills=_clean_skills(nice_to_have_skills),
            comp_band_id=comp_band_id,
            hiring_manager_id=hiring_manager_id,
            created_by_id=ctx.user_id,
        )
        if ctx.has_role(Role.RECRUITER):
            RequisitionAssignment.objects.create(requisition=requisition, user_id=ctx.user_id)
        record_audit(ctx, action="requisition.created", target_type="requisition", target_id=requisition.id)
    return requisition


def update_requisition(ctx: ExecutionContext, *, requisition_id: UUID, **changes: Any) -> JobRequisition:
    """Edit a draft (or a rejected requisition being reworked)."""
    require_active_tenant(ctx.tenant_id)
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ApplicationError(f"Cannot edit {sorted(unknown)}.")
    with transaction.atomic():
        requisition = get_visible_requisition(ctx, requisition_id, for_update=True)
        if not policies.can_submit(ctx, requisition):
            raise PolicyDenied("You cannot edit this requisition.")
        if requisition.status not in (JobRequisition.Status.DRAFT, JobRequisition.Status.REJECTED):
            raise InvalidStateTransition("Only draft or rejected requisitions can be edited.")
        if "hiring_manager_id" in changes:
            _check_hiring_manager(ctx, changes["hiring_manager_id"])
        if "comp_band_id" in changes:
            _check_comp_band(ctx, changes["comp_band_id"])
        for field in ("must_have_skills", "nice_to_have_skills"):
            if field in changes:
                changes[field] = _clean_skills(changes[field])
        for field, value in changes.items():
            setattr(requisition, field, value)
        if requisition.status == JobRequisition.Status.REJECTED:
            requisition.status = JobRequisition.Status.DRAFT
        requisition.save()
        record_audit(
            ctx,
            action="requisition.updated",
            target_type="requisition",
            target_id=requisition.id,
            details={"fields": sorted(changes)},
        )
    return requisition


def submit_requisition(ctx: ExecutionContext, *, requisition_id: UUID) -> JobRequisition:
    """Move a draft to submitted and open an approval request for HR admins."""
    from apps.approvals.services import open_request

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        requisition = get_visible_requisition(ctx, requisition_id, for_update=True)
        if not policies.can_submit(ctx, requisition):
            raise PolicyDenied("You cannot submit this requisition.")
        if requisition.status != JobRequisition.Status.DRAFT:
            raise InvalidStateTransition(f"Only draft requisitions can be submitted; this one is {requisition.status}.")
        requisition.status = JobRequisition.Status.SUBMITTED
        requisition.submitted_at = timezone.now()
        requisition.save(update_fields=["status", "submitted_at", "updated_at"])
        open_request(
            ctx,
            kind=ApprovalRequest.Kind.REQUISITION,
            target_id=requisition.id,
            title=f"Approve requisition: {requisition.title}",
            summary=(
                f"{requisition.department} · {requisition.headcount} opening(s) · "
                f"{requisition.level or 'level not set'}"
            ),
            payload={
                "requisition_id": str(requisition.id),
                "title": requisition.title,
                "department": requisition.department,
                "headcount": requisition.headcount,
            },
            required_roles=[Role.HR_ADMIN],
            requisition_id=requisition.id,
        )
        record_audit(ctx, action="requisition.submitted", target_type="requisition", target_id=requisition.id)
    return requisition


def on_requisition_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    requisition = JobRequisition.objects.select_for_update().filter(pk=request.target_id).first()
    if requisition is None:
        raise NotFound("Requisition not found.")
    if requisition.status != JobRequisition.Status.SUBMITTED:
        raise InvalidStateTransition("This requisition is no longer waiting for approval.")
    if decision.decision == ApprovalDecision.Decision.APPROVE:
        requisition.status = JobRequisition.Status.APPROVED
        requisition.approved_by_id = ctx.user_id
        requisition.approved_at = timezone.now()
    else:
        requisition.status = JobRequisition.Status.REJECTED  # back to the author for rework
    requisition.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return True


def close_requisition(ctx: ExecutionContext, *, requisition_id: UUID, reason: str) -> JobRequisition:
    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        requisition = get_visible_requisition(ctx, requisition_id, for_update=True)
        if not ctx.has_role(Role.HR_ADMIN) and ctx.user_id != requisition.hiring_manager_id:
            raise PolicyDenied("Only HR admins and the hiring manager can close a requisition.")
        if requisition.status == JobRequisition.Status.CLOSED:
            raise InvalidStateTransition("Already closed.")
        requisition.status = JobRequisition.Status.CLOSED
        requisition.save(update_fields=["status", "updated_at"])
        record_audit(
            ctx,
            action="requisition.closed",
            target_type="requisition",
            target_id=requisition.id,
            details={"reason": reason},
        )
    return requisition


def assign_recruiter(ctx: ExecutionContext, *, requisition_id: UUID, recruiter_id: UUID) -> RequisitionAssignment:
    """Give a recruiter access to a requisition. Idempotent."""
    require_active_tenant(ctx.tenant_id)
    if not policies.can_assign_recruiters(ctx):
        raise PolicyDenied("Only HR admins can assign recruiters.")
    requisition = get_visible_requisition(ctx, requisition_id)
    if not member_has_role(tenant_id=ctx.tenant_id, user_id=recruiter_id, role=Role.RECRUITER):
        raise ApplicationError(
            "The user must be an active recruiter in this tenant.",
            details={"recruiter_id": ["Not a recruiter in this tenant."]},
        )
    assignment, created = RequisitionAssignment.objects.get_or_create(requisition=requisition, user_id=recruiter_id)
    if created:
        record_audit(
            ctx,
            action="requisition.recruiter_assigned",
            target_type="requisition",
            target_id=requisition.id,
            details={"recruiter_id": str(recruiter_id)},
        )
    return assignment


def create_comp_band(
    ctx: ExecutionContext,
    *,
    department: str,
    level: str,
    min_salary: Decimal,
    max_salary: Decimal,
    currency: str = "INR",
) -> CompBand:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN):
        raise PolicyDenied("Only HR admins manage comp bands.")
    if min_salary <= 0 or min_salary > max_salary:
        raise ApplicationError("The band minimum must be positive and not above the maximum.")
    band = CompBand.objects.create(
        department=department, level=level, min_salary=min_salary, max_salary=max_salary, currency=currency.upper()
    )
    record_audit(ctx, action="comp_band.created", target_type="comp_band", target_id=band.id)
    return band
