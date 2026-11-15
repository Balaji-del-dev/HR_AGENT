from uuid import UUID

from django.db.models import Q, QuerySet

from apps.accounts.roles import Role
from apps.agents.models import AgentRun, AssistantThread
from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound
from apps.requisitions.selectors import visible_requisitions


def visible_runs(ctx: ExecutionContext) -> QuerySet[AgentRun]:
    """HR admins and auditors see every run; others see runs they started or on requisitions they can see."""
    queryset = AgentRun.objects.filter(tenant_id=ctx.tenant_id)
    if ctx.has_role(Role.HR_ADMIN, Role.AUDITOR):
        return queryset
    return queryset.filter(Q(requested_by_id=ctx.user_id) | Q(requisition__in=visible_requisitions(ctx).values("pk")))


def get_visible_run(ctx: ExecutionContext, run_id: UUID) -> AgentRun:
    run = visible_runs(ctx).filter(pk=run_id).first()
    if run is None:
        raise NotFound("Agent run not found.")
    return run


def my_threads(ctx: ExecutionContext) -> QuerySet[AssistantThread]:
    return AssistantThread.objects.filter(tenant_id=ctx.tenant_id, user_id=ctx.user_id)


def get_my_thread(ctx: ExecutionContext, thread_id: UUID) -> AssistantThread:
    thread = my_threads(ctx).filter(pk=thread_id).first()
    if thread is None:
        raise NotFound("Conversation not found.")
    return thread


def thread_history(thread: AssistantThread, limit: int = 10) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for run in thread.runs.filter(status=AgentRun.Status.COMPLETED).order_by("created_at")[:limit]:
        history.append({"role": "user", "content": str(run.input.get("message", ""))})
        history.append({"role": "assistant", "content": str((run.output.get("result") or {}).get("answer", ""))})
    return history
