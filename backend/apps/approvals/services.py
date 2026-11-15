"""One approval flow for every gated draft.

Apps register a handler per approval kind (in their AppConfig.ready). When a
person decides, the handler runs the side effect in plain service code: the
LLM never executes anything. If the request belongs to a paused agent run,
the run is resumed with the decision after the transaction commits.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.roles import Role
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from policies.engine import decide as policy_decide

# A handler returns True when a linked agent run should resume now, False to keep it paused
# (an offer waiting for its next approval step).
Handler = Callable[[ExecutionContext, ApprovalRequest, ApprovalDecision], bool]
_handlers: dict[str, Handler] = {}


def register_handler(kind: str, handler: Handler) -> None:
    _handlers[kind] = handler


def open_request(
    ctx: ExecutionContext,
    *,
    kind: str,
    target_id: UUID,
    title: str,
    required_roles: list[str],
    summary: str = "",
    payload: dict[str, Any] | None = None,
    assignee_id: UUID | None = None,
    requisition_id: UUID | None = None,
    agent_run_id: UUID | None = None,
    review_round: int = 1,
    step: int = 1,
    chain_length: int = 1,
) -> ApprovalRequest:
    """Create a pending request. Idempotent per (agent run, review round, step)."""
    require_active_tenant(ctx.tenant_id)
    defaults = {
        "kind": kind,
        "target_id": target_id,
        "title": title[:200],
        "summary": summary,
        "payload": payload or {},
        "required_roles": required_roles,
        "assignee_id": assignee_id,
        "requisition_id": requisition_id,
        "chain_length": chain_length,
        "requested_by_id": ctx.user_id,
    }
    if agent_run_id is not None:
        request, created = ApprovalRequest.objects.get_or_create(
            agent_run_id=agent_run_id, review_round=review_round, step=step, defaults=defaults
        )
    else:
        request, created = ApprovalRequest.objects.create(step=step, **defaults), True
    if created:
        record_audit(
            ctx,
            action="approval.opened",
            target_type=kind,
            target_id=target_id,
            details={"approval_request_id": str(request.id), "step": step},
        )
        _notify_approvers(request)
        if agent_run_id is not None and step > 1:
            _follow_chain(agent_run_id, request)
    return request


def _follow_chain(run_id: UUID, request: ApprovalRequest) -> None:
    """A paused run waits on its chain's current step: point its interrupt at the new request."""
    from apps.agents.models import AgentRun

    run = AgentRun.objects.select_for_update().filter(pk=run_id).first()
    if run is not None and run.pending_interrupt:
        run.pending_interrupt = {**run.pending_interrupt, "approval_request_id": str(request.id), "step": request.step}
        run.save(update_fields=["pending_interrupt", "updated_at"])


def _notify_approvers(request: ApprovalRequest) -> None:
    from apps.accounts.selectors import users_with_role
    from apps.core.realtime import notify_users

    user_ids: set[UUID] = set()
    if request.assignee_id:
        user_ids.add(request.assignee_id)
    else:
        for role in request.required_roles:
            user_ids.update(users_with_role(tenant_id=request.tenant_id, role=role).values_list("id", flat=True))
    notify_users(
        user_ids,
        {
            "type": "approval.requested",
            "approval_request_id": str(request.id),
            "kind": request.kind,
            "title": request.title,
        },
    )


def visible_requests(ctx: ExecutionContext) -> QuerySet[ApprovalRequest]:
    """Requests the caller can decide, plus the ones they asked for. HR admins and auditors see all."""
    queryset = ApprovalRequest.objects.filter(tenant_id=ctx.tenant_id)
    if ctx.has_role(Role.HR_ADMIN, Role.AUDITOR):
        return queryset
    mine = Q(requested_by_id=ctx.user_id) | Q(assignee_id=ctx.user_id)
    decidable = Q(assignee__isnull=True, required_roles__overlap=sorted(ctx.roles))
    return queryset.filter(mine | decidable)


def get_visible_request(ctx: ExecutionContext, request_id: UUID, *, for_update: bool = False) -> ApprovalRequest:
    queryset = visible_requests(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    request = queryset.filter(pk=request_id).first()
    if request is None:
        raise NotFound("Approval request not found.")
    return request


def can_decide(ctx: ExecutionContext, request: ApprovalRequest) -> bool:
    return policy_decide("approval.decide", ctx, _policy_resource(request)).allowed


def _policy_resource(request: ApprovalRequest) -> dict[str, Any]:
    previous = []
    if request.kind == ApprovalRequest.Kind.OFFER:
        previous = [
            str(user_id)
            for user_id in ApprovalDecision.objects.filter(
                request__kind=ApprovalRequest.Kind.OFFER,
                request__target_id=request.target_id,
                decision=ApprovalDecision.Decision.APPROVE,
            ).values_list("decided_by_id", flat=True)
        ]
    return {
        "kind": request.kind,
        "required_roles": list(request.required_roles),
        "assignee_id": str(request.assignee_id) if request.assignee_id else None,
        "requested_by_id": str(request.requested_by_id),
        "previous_approver_ids": previous,
    }


def decide(
    ctx: ExecutionContext,
    *,
    request_id: UUID,
    decision: str,
    reason: str = "",
    edits: dict[str, Any] | None = None,
) -> ApprovalRequest:
    """Record a person's decision and run its effect. A second decision on the same request is a 409."""
    require_active_tenant(ctx.tenant_id)
    if decision not in ApprovalDecision.Decision.values:
        raise ApplicationError(
            "Unknown decision.", details={"decision": [f"Must be one of {ApprovalDecision.Decision.values}."]}
        )
    if decision != ApprovalDecision.Decision.APPROVE and not reason.strip():
        raise ApplicationError(
            "A reason is required to reject or request changes.", details={"reason": ["This field is required."]}
        )

    with transaction.atomic():
        request = get_visible_request(ctx, request_id, for_update=True)
        if request.status != ApprovalRequest.Status.PENDING:
            raise InvalidStateTransition(f"This request was already decided ({request.status}).")
        verdict = policy_decide("approval.decide", ctx, _policy_resource(request))
        if not verdict.allowed:
            raise PolicyDenied(verdict.reason)

        record = ApprovalDecision.objects.create(
            request=request, decided_by_id=ctx.user_id, decision=decision, reason=reason, edits=edits or {}
        )
        outcomes: dict[str, str] = {
            ApprovalDecision.Decision.APPROVE: ApprovalRequest.Status.APPROVED,
            ApprovalDecision.Decision.REJECT: ApprovalRequest.Status.REJECTED,
            ApprovalDecision.Decision.REQUEST_CHANGES: ApprovalRequest.Status.CHANGES_REQUESTED,
        }
        request.status = outcomes[decision]
        request.decided_at = timezone.now()
        request.save(update_fields=["status", "decided_at", "updated_at"])

        handler = _handlers.get(request.kind)
        resume = handler(ctx, request, record) if handler else True
        record_audit(
            ctx,
            action=f"approval.{decision}",
            target_type=request.kind,
            target_id=request.target_id,
            details={"approval_request_id": str(request.id), "reason": reason, "edited": bool(edits)},
        )
        if resume and request.agent_run_id:
            from agent_engine.runtime import enqueue_resume

            enqueue_resume(
                ctx,
                run_id=request.agent_run_id,
                decision={
                    "approval_request_id": str(request.id),
                    "decision": decision,
                    "reason": reason,
                    "edits": edits or {},
                    "decided_by": str(ctx.user_id),
                },
            )
    return request


def cancel_open_requests_for_run(ctx: ExecutionContext, *, run_id: UUID) -> int:
    require_active_tenant(ctx.tenant_id)
    return ApprovalRequest.objects.filter(agent_run_id=run_id, status=ApprovalRequest.Status.PENDING).update(
        status=ApprovalRequest.Status.CANCELLED, decided_at=timezone.now()
    )
