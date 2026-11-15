"""Applications and stage changes. Every change has a named person and a reason."""

from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.applications.models import ApplicationStageHistory, JobApplication
from apps.applications.selectors import get_visible_application
from apps.candidates.models import CandidateConsent
from apps.candidates.selectors import get_visible_candidate, has_active_consent
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.matching.models import RecruiterDecision
from apps.requisitions.models import JobRequisition
from apps.requisitions.selectors import get_visible_requisition

Stage = JobApplication.Stage

NEXT_STAGE: dict[str, str] = {
    Stage.APPLIED: Stage.SCREENING,
    Stage.SCREENING: Stage.SHORTLISTED,
    Stage.SHORTLISTED: Stage.INTERVIEW,
    Stage.INTERVIEW: Stage.OFFER,
    Stage.OFFER: Stage.HIRED,
}
ALLOWED: dict[str, set[str]] = {
    Stage.APPLIED: {Stage.SCREENING, Stage.SHORTLISTED, Stage.REJECTED, Stage.WITHDRAWN},
    Stage.SCREENING: {Stage.SHORTLISTED, Stage.REJECTED, Stage.WITHDRAWN},
    Stage.SHORTLISTED: {Stage.INTERVIEW, Stage.REJECTED, Stage.WITHDRAWN},
    Stage.INTERVIEW: {Stage.OFFER, Stage.REJECTED, Stage.WITHDRAWN},
    Stage.OFFER: {Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN},
    Stage.HIRED: set(),
    Stage.REJECTED: set(),
    Stage.WITHDRAWN: set(),
}
OPEN_STAGES = [Stage.APPLIED, Stage.SCREENING, Stage.SHORTLISTED, Stage.INTERVIEW, Stage.OFFER]


def create_application(
    ctx: ExecutionContext, *, requisition_id: UUID, candidate_id: UUID, source: str = ""
) -> JobApplication:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins add applications.")
    requisition = get_visible_requisition(ctx, requisition_id)
    if requisition.status != JobRequisition.Status.APPROVED:
        raise InvalidStateTransition("Applications can only be added to approved requisitions.")
    candidate = get_visible_candidate(ctx, candidate_id)
    if not has_active_consent(candidate.id, CandidateConsent.Purpose.APPLICATION) and not has_active_consent(
        candidate.id, CandidateConsent.Purpose.TALENT_POOL
    ):
        raise PolicyDenied("This candidate has not consented to be considered.")
    try:
        with transaction.atomic():
            application = JobApplication.objects.create(
                requisition=requisition,
                candidate=candidate,
                source=source or candidate.source,
                stage_changed_at=timezone.now(),
                created_by_id=ctx.user_id,
            )
    except IntegrityError as exc:
        raise ApplicationError("This candidate already applied to this requisition.") from exc
    record_audit(ctx, action="application.created", target_type="application", target_id=application.id)
    return application


def _can_decide(ctx: ExecutionContext, application: JobApplication, to_stage: str) -> bool:
    if ctx.has_role(Role.HR_ADMIN):
        return True
    requisition = application.requisition
    if ctx.has_role(Role.RECRUITER) and requisition.assignments.filter(user_id=ctx.user_id).exists():
        return True
    # The hiring panel decides after interviews.
    return (
        ctx.has_role(Role.HIRING_MANAGER)
        and requisition.hiring_manager_id == ctx.user_id
        and application.stage in (Stage.SHORTLISTED, Stage.INTERVIEW, Stage.OFFER)
    )


def record_decision(
    ctx: ExecutionContext,
    *,
    application_id: UUID,
    decision: str,
    reason: str,
    to_stage: str | None = None,
    assessment_id: UUID | None = None,
    run_id: UUID | None = None,
) -> RecruiterDecision:
    """A person decides: advance (to the next or a named stage), hold, or reject. Reason required."""
    require_active_tenant(ctx.tenant_id)
    if not reason or not reason.strip():
        raise ApplicationError("A reason is required for every decision.", details={"reason": ["Required."]})
    if decision not in RecruiterDecision.Decision.values:
        raise ApplicationError("Unknown decision.")
    with transaction.atomic():
        application = get_visible_application(ctx, application_id, for_update=True)
        from_stage = application.stage
        if decision == RecruiterDecision.Decision.ADVANCE:
            target = to_stage or NEXT_STAGE.get(from_stage)
        elif decision == RecruiterDecision.Decision.REJECT:
            target = Stage.REJECTED
        else:
            target = None
        if target is not None and target not in ALLOWED.get(from_stage, set()):
            raise InvalidStateTransition(f"Cannot move from {from_stage} to {target}.")
        if not _can_decide(ctx, application, target or from_stage):
            raise PolicyDenied("You cannot make decisions on this application.")
        if assessment_id and not application.assessments.filter(pk=assessment_id).exists():
            raise ApplicationError("That assessment belongs to another application.")
        record = RecruiterDecision.objects.create(
            application=application,
            assessment_id=assessment_id,
            decision=decision,
            from_stage=from_stage,
            to_stage=target or "",
            reason=reason.strip(),
            actor_id=ctx.user_id,
            agent_run_id=run_id,
        )
        if target is not None:
            _move(ctx, application, target, reason.strip())
        record_audit(
            ctx,
            action=f"decision.{decision}",
            target_type="application",
            target_id=application.id,
            details={"from": from_stage, "to": target, "assessment_id": str(assessment_id or "")},
        )
    return record


def _move(ctx: ExecutionContext, application: JobApplication, to_stage: str, reason: str) -> None:
    ApplicationStageHistory.objects.create(
        application=application, from_stage=application.stage, to_stage=to_stage, actor_id=ctx.user_id, reason=reason
    )
    application.stage = to_stage
    application.stage_changed_at = timezone.now()
    application.save(update_fields=["stage", "stage_changed_at", "updated_at"])


def withdraw(ctx: ExecutionContext, *, application_id: UUID, reason: str) -> JobApplication:
    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        application = get_visible_application(ctx, application_id, for_update=True)
        if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
            raise PolicyDenied("Only recruiters record withdrawals.")
        if Stage.WITHDRAWN not in ALLOWED.get(application.stage, set()):
            raise InvalidStateTransition("This application is already closed.")
        _move(ctx, application, Stage.WITHDRAWN, reason or "Candidate withdrew.")
        record_audit(ctx, action="application.withdrawn", target_type="application", target_id=application.id)
    return application
