"""Starting, running and resuming agent runs.

* ``start_run`` validates and records an AgentRun (status queued) and queues
  ``run_graph`` after the transaction commits. No LLM call happens in the web
  process.
* ``execute_run`` streams the graph in a Celery worker. Each update becomes an
  AgentStep row and a WebSocket event on group run_<id>. At an interrupt the
  run is saved as awaiting_review and the task ends, so no worker waits on people.
* ``enqueue_resume`` refuses stale answers: the decision must name the approval
  request the run is actually paused on.

The LangGraph thread_id is the AgentRun id; checkpoints live in PostgreSQL
(schema ``langgraph``) so paused runs survive restarts and deploys.
"""

import atexit
import logging
import threading
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from langgraph.types import Command

from agent_engine.budget import BudgetExceeded, RunContext, bind_run
from agent_engine.llm.factory import callbacks_for, model_label
from agent_engine.state import initial_state
from agent_engine.version import GRAPH_VERSION
from apps.agents.models import AgentRun, AgentStep
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, PolicyDenied, TenantAccessDenied
from apps.core.realtime import publish_run_event
from apps.core.tasks import enqueue_on_commit
from apps.core.tenancy import require_active_tenant, tenant_scope
from policies.engine import decide as policy_decide

logger = logging.getLogger(__name__)

REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "requisition_review": ("requisition_id",),
    "jd_generation": ("requisition_id",),
    "sourcing": ("requisition_id",),
    "resume_parsing": ("document_id",),
    "matching": ("requisition_id",),
    "communication": ("application_id", "kind"),
    "scheduling": ("interview_id",),
    "feedback_summary": ("application_id",),
    "offer": ("application_id",),
    "assistant": ("message",),
    "analytics": (),
    "compliance": (),
}


class StaleResume(InvalidStateTransition):
    code = "stale_resume"
    default_message = "This run is not waiting for that decision."


# ---------------------------------------------------------------- checkpointer

_checkpointer_lock = threading.Lock()
_checkpointer: Any = None


def checkpoint_conninfo() -> str:
    db = settings.DATABASES["default"]
    return (
        f"host={db['HOST']} port={db['PORT']} dbname={db['NAME']} user={db['USER']} password={db['PASSWORD']} "
        "options='-c search_path=langgraph'"
    )


def get_checkpointer() -> Any:
    global _checkpointer
    with _checkpointer_lock:
        if _checkpointer is None:
            if settings.AGENT_CHECKPOINTER == "memory":
                from langgraph.checkpoint.memory import InMemorySaver

                _checkpointer = InMemorySaver()
            else:
                from langgraph.checkpoint.postgres import PostgresSaver
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                pool = ConnectionPool(
                    checkpoint_conninfo(),
                    min_size=1,
                    max_size=4,
                    open=True,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                )
                atexit.register(pool.close)
                _checkpointer = PostgresSaver(pool)  # type: ignore[arg-type]
        return _checkpointer


def delete_checkpoints(run_id: UUID) -> None:
    get_checkpointer().delete_thread(str(run_id))


def _graph() -> Any:
    from agent_engine.graphs.supervisor import build_supervisor_graph

    return build_supervisor_graph(get_checkpointer())


# ---------------------------------------------------------------- start and resume


def _check_targets(ctx: ExecutionContext, kind: str, params: dict[str, Any]) -> UUID | None:
    """The run's targets must be visible to the requester now. Returns the requisition, if any."""
    from apps.applications.selectors import get_visible_application
    from apps.documents.selectors import get_visible_document
    from apps.interviews.services import get_visible_interview
    from apps.requisitions.models import JobRequisition
    from apps.requisitions.selectors import get_visible_requisition

    missing = [key for key in REQUIRED_PARAMS[kind] if not params.get(key)]
    if missing:
        raise ApplicationError("Missing run inputs.", details={key: ["Required."] for key in missing})
    if params.get("requisition_id"):
        requisition = get_visible_requisition(ctx, UUID(str(params["requisition_id"])))
        if kind == "matching" and requisition.status != JobRequisition.Status.APPROVED:
            raise InvalidStateTransition("Matching needs an approved requisition.")
        return requisition.id
    if params.get("application_id"):
        return get_visible_application(ctx, UUID(str(params["application_id"]))).requisition_id
    if params.get("interview_id"):
        return get_visible_interview(ctx, UUID(str(params["interview_id"]))).application.requisition_id
    if params.get("document_id"):
        get_visible_document(ctx, UUID(str(params["document_id"])))
    return None


def start_run(ctx: ExecutionContext, *, kind: str, params: dict[str, Any], thread_id: UUID | None = None) -> AgentRun:
    from agent_engine.tasks import run_graph
    from apps.governance.services import record_audit

    require_active_tenant(ctx.tenant_id)
    if kind not in REQUIRED_PARAMS:
        raise ApplicationError(f"Unknown run kind {kind}.")
    verdict = policy_decide(f"run:{kind}", ctx)
    if not verdict.allowed:
        raise PolicyDenied(verdict.reason)
    params = {key: (str(value) if isinstance(value, UUID) else value) for key, value in params.items()}
    requisition_id = _check_targets(ctx, kind, params)
    run = AgentRun.objects.create(
        kind=kind,
        requested_by_id=ctx.user_id,
        requisition_id=requisition_id,
        input=params,
        graph_version=GRAPH_VERSION,
        model_name=model_label(),
        thread_id=thread_id,
    )
    enqueue_on_commit(run_graph, ctx, run_id=str(run.id))
    record_audit(ctx, action="agent_run.queued", target_type="agent_run", target_id=run.id, details={"kind": kind})
    publish_run_event(run.id, {"type": "run.queued", "status": run.status})
    return run


def start_run_for_user(*, user_id: UUID, tenant_id: UUID, kind: str, payload: dict[str, Any]) -> AgentRun | None:
    """System-triggered runs (for example after a resume is processed) act as the user who caused them."""
    from apps.accounts.services import build_execution_context

    try:
        ctx = build_execution_context(user_id=user_id, requested_tenant_id=tenant_id)
    except TenantAccessDenied:
        logger.warning("user lost access; not starting %s run", kind)
        return None
    try:
        return start_run(ctx, kind=kind, params=payload)
    except PolicyDenied:
        logger.info("user may not start %s runs; skipped", kind)
        return None


def enqueue_resume(ctx: ExecutionContext, *, run_id: UUID, decision: dict[str, Any]) -> AgentRun:
    from agent_engine.tasks import resume_graph

    require_active_tenant(ctx.tenant_id)
    run = AgentRun.objects.select_for_update().filter(pk=run_id, tenant_id=ctx.tenant_id).first()
    if run is None:
        raise StaleResume("Run not found.")
    pending = run.pending_interrupt or {}
    if run.status != AgentRun.Status.AWAITING_REVIEW or pending.get("approval_request_id") != decision.get(
        "approval_request_id"
    ):
        raise StaleResume()
    run.status = AgentRun.Status.QUEUED
    run.save(update_fields=["status", "updated_at"])
    enqueue_on_commit(resume_graph, ctx, run_id=str(run.id), decision=decision)
    publish_run_event(run.id, {"type": "run.resumed", "status": run.status})
    return run


def cancel_run(ctx: ExecutionContext, *, run_id: UUID) -> AgentRun:
    from apps.approvals.services import cancel_open_requests_for_run

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        run = AgentRun.objects.select_for_update().filter(pk=run_id, tenant_id=ctx.tenant_id).first()
        if run is None:
            raise StaleResume("Run not found.")
        if run.requested_by_id != ctx.user_id and not ctx.has_role("hr_admin"):
            raise PolicyDenied("Only the person who started a run, or an HR admin, can cancel it.")
        if run.status in (AgentRun.Status.COMPLETED, AgentRun.Status.FAILED, AgentRun.Status.CANCELLED):
            raise InvalidStateTransition("This run has already finished.")
        run.status = AgentRun.Status.CANCELLED
        run.finished_at = timezone.now()
        run.pending_interrupt = None
        run.save()
        cancel_open_requests_for_run(ctx, run_id=run.id)
        publish_run_event(run.id, {"type": "run.cancelled", "status": run.status})
    return run


# ---------------------------------------------------------------- execution (Celery worker)


def _load_context(run: AgentRun) -> ExecutionContext:
    from dataclasses import replace

    from apps.accounts.services import build_execution_context

    ctx = build_execution_context(user_id=run.requested_by_id, requested_tenant_id=run.tenant_id)
    return replace(ctx, run_id=run.id)


def execute_run(run_id: UUID, tenant_id: UUID, *, resume: dict[str, Any] | None = None) -> str:
    from agent_engine.prompts import sync_prompts

    with tenant_scope(tenant_id):
        run = AgentRun.objects.select_for_update().get(pk=run_id)
        if run.status != AgentRun.Status.QUEUED:
            return f"skipped ({run.status})"
        try:
            ctx = _load_context(run)
        except TenantAccessDenied:
            _finish(run, AgentRun.Status.FAILED, error="The requesting user no longer has access to this tenant.")
            return "failed"
        run.status = AgentRun.Status.RUNNING
        run.started_at = run.started_at or timezone.now()
        run.pending_interrupt = None
        run.save()
        publish_run_event(run.id, {"type": "run.started", "status": run.status})
        sync_prompts()
        budget = RunContext(
            run_id=run.id,
            max_tool_calls=settings.AGENT_MAX_TOOL_CALLS,
            max_tokens=settings.AGENT_MAX_TOKENS,
            tool_calls=run.tool_call_count,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            prompt_versions=dict(run.prompt_versions),
        )
        sequence = run.steps.count()
        kind, params = run.kind, dict(run.input)

    graph = _graph()
    config: dict[str, Any] = {
        "configurable": {"thread_id": str(run_id)},
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
        "callbacks": callbacks_for(run_id),
        "metadata": {"run_id": str(run_id), "tenant_id": str(tenant_id), "kind": kind},
    }
    inputs: Any = Command(resume=resume) if resume is not None else initial_state(kind=kind, params=params)
    pending: dict[str, Any] | None = None
    try:
        with bind_run(budget):
            for chunk in graph.stream(inputs, config, context=ctx, stream_mode="updates"):
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        pending = dict(update[0].value)
                        continue
                    sequence += 1
                    _record_step(run_id, tenant_id, sequence, node, update)
        state = graph.get_state(config)
    except BudgetExceeded as exc:
        return _close(run_id, tenant_id, budget, AgentRun.Status.BUDGET_EXCEEDED, error=str(exc))
    except Exception as exc:
        logger.exception("agent run failed", extra={"run_id": str(run_id)})
        return _close(run_id, tenant_id, budget, AgentRun.Status.FAILED, error=f"{type(exc).__name__}: {exc}"[:2000])

    values = state.values or {}
    output = {
        "result": values.get("result") or {},
        "drafts": values.get("drafts") or [],
        "intent": values.get("intent"),
        "errors": values.get("errors") or [],
    }
    if pending is not None:
        return _close(
            run_id,
            tenant_id,
            budget,
            AgentRun.Status.AWAITING_REVIEW,
            output=output,
            pending=pending,
            flags=values.get("flags") or [],
        )
    return _close(run_id, tenant_id, budget, AgentRun.Status.COMPLETED, output=output, flags=values.get("flags") or [])


def execute_queued(tenant_id: UUID) -> list[str]:
    """Run every queued run of a tenant in this process, oldest first. For the demo seed and tests;
    production runs go through the agents queue."""
    results: list[str] = []
    while True:
        with tenant_scope(tenant_id):
            run = AgentRun.objects.filter(status=AgentRun.Status.QUEUED).order_by("created_at").first()
        if run is None:
            return results
        results.append(execute_run(run.id, tenant_id))


def _summarize(update: Any) -> dict[str, Any]:
    if not isinstance(update, dict):
        return {}
    summary: dict[str, Any] = {"keys": sorted(update)}
    if isinstance(update.get("result"), dict):
        summary["result_keys"] = sorted(update["result"])
    if update.get("review"):
        summary["review"] = {
            k: update["review"].get(k) for k in ("type", "kind", "approval_request_id") if k in update["review"]
        }
    if update.get("assessments"):
        summary["assessments"] = len(update["assessments"])
    if update.get("flags"):
        summary["flags"] = len(update["flags"])
    return summary


def _record_step(run_id: UUID, tenant_id: UUID, sequence: int, node: str, update: Any) -> None:
    summary = _summarize(update)
    with tenant_scope(tenant_id):
        AgentStep.objects.create(run_id=run_id, sequence=sequence, node=node, summary=summary)
        publish_run_event(run_id, {"type": "run.step", "node": node, "sequence": sequence, "summary": summary})


def _finish(run: AgentRun, status: str, *, error: str = "") -> None:
    run.status = status
    run.error = error
    run.finished_at = timezone.now()
    run.save()
    publish_run_event(run.id, {"type": "run.finished", "status": status, "error": error})


def _close(
    run_id: UUID,
    tenant_id: UUID,
    budget: RunContext,
    status: str,
    *,
    output: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
    error: str = "",
    flags: list[dict[str, Any]] | None = None,
) -> str:
    from apps.core.realtime import notify_users

    with tenant_scope(tenant_id):
        run = AgentRun.objects.select_for_update().get(pk=run_id)
        if run.status == AgentRun.Status.CANCELLED:
            return "cancelled"
        run.status = status
        run.tokens_in, run.tokens_out = budget.tokens_in, budget.tokens_out
        run.prompt_versions = budget.prompt_versions
        if budget.model_name:
            run.model_name = budget.model_name
        if output is not None:
            run.output = output
        if flags is not None:
            run.guard_flags = flags
        run.pending_interrupt = pending
        run.error = error
        if status != AgentRun.Status.AWAITING_REVIEW:
            run.finished_at = timezone.now()
        run.save()
        event: dict[str, Any] = {"type": "run.awaiting_review" if pending else "run.finished", "status": status}
        if pending:
            event["interrupt"] = pending
        if error:
            event["error"] = error
        publish_run_event(run.id, event)
        notify_users(
            [run.requested_by_id], {"type": "run.status", "run_id": str(run.id), "kind": run.kind, "status": status}
        )
    return status
