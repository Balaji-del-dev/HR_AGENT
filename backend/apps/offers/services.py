"""Offers: drafted inside the band, approved by HR then finance, by people other than the requester."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet

from apps.accounts.roles import Role
from apps.applications.models import JobApplication
from apps.applications.selectors import get_visible_application, visible_applications
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.offers.models import Offer, OfferStatusHistory
from policies.engine import decide as policy_decide

APPROVAL_CHAIN = [Role.HR_ADMIN, Role.FINANCE_APPROVER]


def visible_offers(ctx: ExecutionContext) -> QuerySet[Offer]:
    queryset = Offer.objects.filter(tenant_id=ctx.tenant_id)
    if ctx.has_role(Role.FINANCE_APPROVER) and not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER):
        return queryset.exclude(status=Offer.Status.DRAFT)
    return queryset.filter(application__in=visible_applications(ctx).values("pk"))


def get_visible_offer(ctx: ExecutionContext, offer_id: UUID, *, for_update: bool = False) -> Offer:
    queryset = visible_offers(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    offer = queryset.select_related("comp_band", "application").filter(pk=offer_id).first()
    if offer is None:
        raise NotFound("Offer not found.")
    return offer


def _set_status(ctx: ExecutionContext, offer: Offer, status: str, reason: str = "") -> None:
    OfferStatusHistory.objects.create(
        offer=offer, from_status=offer.status, to_status=status, actor_id=ctx.user_id, reason=reason
    )
    offer.status = status
    offer.save(update_fields=["status", "updated_at"])


def create_offer_draft(
    ctx: ExecutionContext,
    *,
    application_id: UUID,
    base_salary: Decimal,
    title: str = "",
    bonus_percent: Decimal | None = None,
    start_date: date | None = None,
    rationale: str = "",
    run_id: UUID | None = None,
) -> Offer:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins draft offers.")
    with transaction.atomic():
        application = get_visible_application(ctx, application_id, for_update=True)
        if application.stage not in (JobApplication.Stage.INTERVIEW, JobApplication.Stage.OFFER):
            raise InvalidStateTransition("Offers are drafted for candidates in the interview or offer stage.")
        band = application.requisition.comp_band
        if band is None:
            raise ApplicationError("The requisition has no approved comp band.")
        verdict = policy_decide(
            "offer.within_band",
            ctx,
            {
                "base_salary": base_salary,
                "band_min": band.min_salary,
                "band_max": band.max_salary,
            },
        )
        if not verdict.allowed:
            raise PolicyDenied(verdict.reason)
        if bonus_percent is not None and not Decimal(0) <= bonus_percent <= Decimal(100):
            raise ApplicationError("Bonus must be between 0 and 100 percent.")
        offer = Offer.objects.create(
            application=application,
            comp_band=band,
            title=title or application.requisition.title,
            base_salary=base_salary,
            currency=band.currency,
            bonus_percent=bonus_percent,
            start_date=start_date,
            rationale=rationale,
            created_by_id=ctx.user_id,
            agent_run_id=run_id,
        )
        record_audit(ctx, action="offer.drafted", target_type="offer", target_id=offer.id, run_id=run_id)
    return offer


def submit_offer(
    ctx: ExecutionContext, *, offer_id: UUID, run_id: UUID | None = None, review_round: int = 1
) -> ApprovalRequest:

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        offer = get_visible_offer(ctx, offer_id, for_update=True)
        if offer.status != Offer.Status.DRAFT:
            raise InvalidStateTransition("Only draft offers can be submitted.")
        _set_status(ctx, offer, Offer.Status.PENDING_APPROVAL, "Submitted for approval.")
        return _open_step(ctx, offer, step=1, run_id=run_id, review_round=review_round)


def _open_step(
    ctx: ExecutionContext, offer: Offer, *, step: int, run_id: UUID | None, review_round: int
) -> ApprovalRequest:
    from apps.approvals.services import open_request

    role = APPROVAL_CHAIN[step - 1]
    label = "HR" if role == Role.HR_ADMIN else "Finance"
    return open_request(
        ctx,
        kind=ApprovalRequest.Kind.OFFER,
        target_id=offer.id,
        title=f"{label} approval: offer for {offer.title}",
        summary=(
            f"{offer.currency} {offer.base_salary:,.0f} "
            f"(band {offer.comp_band.min_salary:,.0f}-{offer.comp_band.max_salary:,.0f})"
        ),
        payload={
            "offer_id": str(offer.id),
            "application_id": str(offer.application_id),
            "title": offer.title,
            "base_salary": str(offer.base_salary),
            "currency": offer.currency,
            "bonus_percent": str(offer.bonus_percent) if offer.bonus_percent is not None else None,
            "start_date": offer.start_date.isoformat() if offer.start_date else None,
            "band": {
                "min": str(offer.comp_band.min_salary),
                "max": str(offer.comp_band.max_salary),
                "level": offer.comp_band.level,
                "department": offer.comp_band.department,
            },
            "rationale": offer.rationale,
            "step": step,
            "chain": [str(r) for r in APPROVAL_CHAIN],
        },
        required_roles=[role],
        requisition_id=offer.application.requisition_id,
        agent_run_id=run_id,
        review_round=review_round,
        step=step,
        chain_length=len(APPROVAL_CHAIN),
    )


def on_offer_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    offer = (
        Offer.objects.select_for_update()
        .select_related("comp_band", "application")
        .filter(pk=request.target_id)
        .first()
    )
    if offer is None:
        raise NotFound("Offer not found.")
    if offer.status != Offer.Status.PENDING_APPROVAL:
        raise InvalidStateTransition("This offer is not waiting for approval.")
    if decision.decision != ApprovalDecision.Decision.APPROVE:
        _set_status(
            ctx, offer, Offer.Status.REJECTED if decision.decision == "reject" else Offer.Status.DRAFT, decision.reason
        )
        return True
    if request.step < len(APPROVAL_CHAIN):
        _open_step(ctx, offer, step=request.step + 1, run_id=request.agent_run_id, review_round=request.review_round)
        return False  # the run stays paused until the last step
    _set_status(ctx, offer, Offer.Status.APPROVED, "All approvals given.")
    if offer.application.stage == JobApplication.Stage.INTERVIEW:
        from apps.applications.services import _move

        _move(ctx, offer.application, JobApplication.Stage.OFFER, "Offer approved.")
    return True


def record_outcome(ctx: ExecutionContext, *, offer_id: UUID, status: str, reason: str = "") -> Offer:
    """Sent, accepted, declined or withdrawn, recorded by a recruiter."""
    require_active_tenant(ctx.tenant_id)
    allowed: dict[str, set[str]] = {
        Offer.Status.APPROVED: {Offer.Status.SENT, Offer.Status.WITHDRAWN},
        Offer.Status.SENT: {Offer.Status.ACCEPTED, Offer.Status.DECLINED, Offer.Status.WITHDRAWN},
    }
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters record offer outcomes.")
    with transaction.atomic():
        offer = get_visible_offer(ctx, offer_id, for_update=True)
        if status not in allowed.get(offer.status, set()):
            raise InvalidStateTransition(f"Cannot move an offer from {offer.status} to {status}.")
        _set_status(ctx, offer, status, reason)
        if status == Offer.Status.ACCEPTED:
            from apps.applications.services import record_decision

            record_decision(
                ctx,
                application_id=offer.application_id,
                decision="advance",
                to_stage=JobApplication.Stage.HIRED,
                reason=reason or "Offer accepted.",
            )
        record_audit(ctx, action=f"offer.{status}", target_type="offer", target_id=offer.id)
    return offer
