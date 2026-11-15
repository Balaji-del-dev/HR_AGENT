"""Celery tasks on the agents queue. One run per task; acks_late so a crash re-delivers it."""

from typing import Any
from uuid import UUID

from celery import shared_task


@shared_task(acks_late=True)
def run_graph(*, run_id: str, tenant_id: str) -> str:
    from agent_engine.runtime import execute_run

    return execute_run(UUID(run_id), UUID(tenant_id))


@shared_task(acks_late=True)
def resume_graph(*, run_id: str, tenant_id: str, decision: dict[str, Any]) -> str:
    from agent_engine.runtime import execute_run

    return execute_run(UUID(run_id), UUID(tenant_id), resume=decision)
