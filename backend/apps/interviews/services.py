"""Interviews, panels, slot confirmation and scorecards."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.selectors import member_has_any_role
from apps.applications.models import JobApplication
from apps.applications.selectors import get_visible_application, visible_applications
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.interviews.models import Interview, InterviewPanelist, InterviewSlot, Scorecard
from apps.interviews.scheduling import Interval, find_common_slots


def visible_interviews(ctx: ExecutionContext) -> QuerySet[Interview]:
    return Interview.objects.filter(
        tenant_id=ctx.tenant_id, application__in=visible_applications(ctx).values("pk")
    ).prefetch_related("panel", "slots")


def get_visible_interview(ctx: ExecutionContext, interview_id: UUID, *, for_update: bool = False) -> Interview:
    queryset = visible_interviews(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    interview = queryset.filter(pk=interview_id).first()
    if interview is None:
        raise NotFound("Interview not found.")
    return interview


def create_interview(
    ctx: ExecutionContext,
    *,
    application_id: UUID,
    title: str,
    panel_user_ids: list[UUID],
    round: int = 1,
    duration_minutes: int = 60,
    location: str = "",
) -> Interview:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins set up interviews.")
    if not panel_user_ids:
        raise ApplicationError("An interview needs at least one panelist.")
    application = get_visible_application(ctx, application_id)
    if application.stage not in (JobApplication.Stage.SHORTLISTED, JobApplication.Stage.INTERVIEW):
        raise InvalidStateTransition("Only shortlisted candidates can be interviewed.")
    for user_id in panel_user_ids:
        if not member_has_any_role(
            tenant_id=ctx.tenant_id,
            user_id=user_id,
            roles=[Role.INTERVIEWER, Role.HIRING_MANAGER, Role.RECRUITER, Role.HR_ADMIN],
        ):
            raise ApplicationError(
                "Every panelist must be an active member who can interview.", details={"panel_user_ids": [str(user_id)]}
            )
    with transaction.atomic():
        interview = Interview.objects.create(
            application=application,
            title=title,
            round=round,
            duration_minutes=duration_minutes,
            location=location,
            created_by_id=ctx.user_id,
        )
        InterviewPanelist.objects.bulk_create(
            [
                InterviewPanelist(tenant_id=ctx.tenant_id, interview=interview, user_id=u)
                for u in dict.fromkeys(panel_user_ids)
            ]
        )
        record_audit(ctx, action="interview.created", target_type="interview", target_id=interview.id)
    return interview


def free_slots(
    ctx: ExecutionContext, *, interview_id: UUID, start: datetime | None = None, days: int = 7
) -> list[Interval]:
    from apps.integrations.selectors import busy_intervals

    interview = get_visible_interview(ctx, interview_id)
    window_start = start or (timezone.now() + timedelta(hours=24))
    panel = list(interview.panel.values_list("user_id", flat=True))
    busy = busy_intervals(user_ids=panel, start=window_start, end=window_start + timedelta(days=days * 2))
    return find_common_slots(
        busy=busy, window_start=window_start, days=days, duration=timedelta(minutes=interview.duration_minutes)
    )


def propose_slots(
    ctx: ExecutionContext, *, interview_id: UUID, slots: list[Interval], run_id: UUID | None
) -> list[InterviewSlot]:
    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        interview = get_visible_interview(ctx, interview_id, for_update=True)
        if interview.status != Interview.Status.PROPOSED:
            raise InvalidStateTransition("Slots can only be proposed before the interview is scheduled.")
        interview.slots.filter(status=InterviewSlot.Status.PROPOSED).delete()
        created = InterviewSlot.objects.bulk_create(
            [
                InterviewSlot(
                    tenant_id=ctx.tenant_id, interview=interview, start=s.start, end=s.end, agent_run_id=run_id
                )
                for s in slots
            ]
        )
    return created


def confirm_slot(ctx: ExecutionContext, *, interview_id: UUID, slot_id: UUID) -> Interview:
    """Schedule the interview in the chosen slot and block the panel's calendars. Idempotent."""
    from apps.integrations.models import CalendarBusyBlock

    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters confirm interview times.")
    with transaction.atomic():
        interview = get_visible_interview(ctx, interview_id, for_update=True)
        slot = interview.slots.filter(pk=slot_id).first()
        if slot is None:
            raise NotFound("Slot not found.")
        if interview.status == Interview.Status.SCHEDULED and slot.status == InterviewSlot.Status.CONFIRMED:
            return interview
        if interview.status != Interview.Status.PROPOSED:
            raise InvalidStateTransition("This interview is no longer being scheduled.")
        interview.slots.exclude(pk=slot.pk).update(status=InterviewSlot.Status.DECLINED)
        slot.status = InterviewSlot.Status.CONFIRMED
        slot.save(update_fields=["status", "updated_at"])
        interview.status = Interview.Status.SCHEDULED
        interview.scheduled_start, interview.scheduled_end = slot.start, slot.end
        interview.save(update_fields=["status", "scheduled_start", "scheduled_end", "updated_at"])
        for user_id in interview.panel.values_list("user_id", flat=True):
            CalendarBusyBlock.objects.get_or_create(
                user_id=user_id,
                interview=interview,
                defaults={"start": slot.start, "end": slot.end, "title": f"Interview: {interview.title}"},
            )
        application = interview.application
        if application.stage == JobApplication.Stage.SHORTLISTED:
            from apps.applications.services import _move

            _move(ctx, application, JobApplication.Stage.INTERVIEW, "Interview scheduled.")
        record_audit(
            ctx,
            action="interview.scheduled",
            target_type="interview",
            target_id=interview.id,
            details={"slot_id": str(slot.id)},
        )
    return interview


def on_schedule_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    """Approval of an interview_schedule request: confirm the chosen slot and send the invite."""
    from apps.communications.models import EmailDraft
    from apps.communications.services import approve_draft

    if decision.decision != ApprovalDecision.Decision.APPROVE:
        draft_id = request.payload.get("email_draft_id")
        if draft_id:
            EmailDraft.objects.filter(pk=draft_id).update(status=EmailDraft.Status.REJECTED)
        return True
    slot_id = decision.edits.get("slot_id") or request.payload.get("recommended_slot_id")
    if not slot_id:
        raise ApplicationError("Choose a slot to confirm.", details={"slot_id": ["Required."]})
    interview = confirm_slot(ctx, interview_id=request.target_id, slot_id=UUID(str(slot_id)))
    draft_id = request.payload.get("email_draft_id")
    if draft_id:
        slot = interview.slots.get(pk=slot_id)
        when = timezone.localtime(slot.start).strftime("%A %d %B %Y, %H:%M %Z")
        draft = EmailDraft.objects.get(pk=draft_id)
        body = draft.body.replace("{{ slot_time }}", when)
        approve_draft(ctx, draft_id=draft.id, edits={"body": body})
    return True


def submit_scorecard(
    ctx: ExecutionContext,
    *,
    interview_id: UUID,
    recommendation: str,
    ratings: dict[str, Any],
    strengths: str = "",
    concerns: str = "",
    notes: str = "",
) -> Scorecard:
    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        interview = get_visible_interview(ctx, interview_id, for_update=True)
        if not interview.panel.filter(user_id=ctx.user_id).exists():
            raise PolicyDenied("Only panelists submit scorecards for this interview.")
        if interview.status not in (Interview.Status.SCHEDULED, Interview.Status.COMPLETED):
            raise InvalidStateTransition("Scorecards are submitted after the interview is scheduled.")
        if recommendation not in Scorecard.Recommendation.values:
            raise ApplicationError("Choose a recommendation.")
        clean = {str(k)[:80]: int(v) for k, v in ratings.items() if str(v).isdigit() and 1 <= int(v) <= 5}
        try:
            scorecard = Scorecard.objects.create(
                interview=interview,
                interviewer_id=ctx.user_id,
                recommendation=recommendation,
                ratings=clean,
                strengths=strengths,
                concerns=concerns,
                notes=notes,
                submitted_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise InvalidStateTransition("You already submitted a scorecard for this interview.") from exc
        if interview.scheduled_end and interview.scheduled_end <= timezone.now():
            interview.status = Interview.Status.COMPLETED
            interview.save(update_fields=["status", "updated_at"])
        record_audit(ctx, action="scorecard.submitted", target_type="interview", target_id=interview.id)
    return scorecard


def scorecards_for_application(ctx: ExecutionContext, application_id: UUID) -> QuerySet[Scorecard]:
    application = get_visible_application(ctx, application_id)
    queryset = Scorecard.objects.filter(interview__application=application, submitted_at__isnull=False)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER):
        queryset = queryset.filter(interviewer_id=ctx.user_id)  # interviewers see only their own
    return queryset.select_related("interview").order_by("interview__round", "submitted_at")
