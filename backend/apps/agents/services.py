"""Agent-run entry points for the API: start a run, ask the assistant, resume, cancel."""

from typing import Any
from uuid import UUID

from django.db import transaction

from apps.agents.models import AgentRun, AssistantThread
from apps.agents.selectors import get_my_thread, get_visible_run, thread_history
from apps.approvals.services import decide as decide_approval
from apps.core.context import ExecutionContext
from apps.core.exceptions import InvalidStateTransition
from apps.core.tenancy import require_active_tenant


def start(ctx: ExecutionContext, *, kind: str, params: dict[str, Any]) -> AgentRun:
    from agent_engine.runtime import start_run

    with transaction.atomic():
        return start_run(ctx, kind=kind, params=params)


def ask_assistant(ctx: ExecutionContext, *, message: str, thread_id: UUID | None = None) -> AgentRun:
    from agent_engine.runtime import start_run

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        if thread_id:
            thread = get_my_thread(ctx, thread_id)
        else:
            thread = AssistantThread.objects.create(user_id=ctx.user_id, title=message[:80])
        thread.save(update_fields=["updated_at"])
        return start_run(
            ctx, kind="assistant", params={"message": message, "history": thread_history(thread)}, thread_id=thread.id
        )


def resume(
    ctx: ExecutionContext, *, run_id: UUID, decision: str, reason: str, edits: dict[str, Any], approval_request_id: UUID
) -> AgentRun:
    """POST /agent-runs/{id}/resume/: the same as deciding the pending approval request."""
    require_active_tenant(ctx.tenant_id)
    run = get_visible_run(ctx, run_id)
    pending = run.pending_interrupt or {}
    if run.status != AgentRun.Status.AWAITING_REVIEW or pending.get("approval_request_id") != str(approval_request_id):
        from agent_engine.runtime import StaleResume

        raise StaleResume()
    decide_approval(ctx, request_id=approval_request_id, decision=decision, reason=reason, edits=edits)
    run.refresh_from_db()
    return run


def cancel(ctx: ExecutionContext, *, run_id: UUID) -> AgentRun:
    from agent_engine.runtime import cancel_run

    get_visible_run(ctx, run_id)
    try:
        return cancel_run(ctx, run_id=run_id)
    except InvalidStateTransition:
        raise
