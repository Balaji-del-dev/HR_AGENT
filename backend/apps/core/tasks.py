"""Celery base task that runs every task inside its tenant's scope."""

from typing import Any
from uuid import UUID

import structlog
from celery import Task
from django.db import transaction

from apps.core.context import ExecutionContext
from apps.core.exceptions import TenantScopeError
from apps.core.tenancy import tenant_scope


class TenantTask(Task):  # type: ignore[misc]
    """Base class for tasks that touch tenant data.

    The task declares ``tenant_id`` as a keyword parameter and the caller
    passes it by keyword (use :func:`enqueue_on_commit`). Keeping it in the
    signature means Celery's own argument check still covers it. The task
    body then runs in one transaction with that tenant active, so Row-Level
    Security applies to the worker exactly as it does to a web request.

        @shared_task(base=TenantTask)
        def extract_document(*, tenant_id: str, document_id: str) -> None: ...
    """

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tenant_id = kwargs.get("tenant_id")
        if tenant_id is None:
            raise TenantScopeError(f"Task {self.name} was called without tenant_id (pass it by keyword).")
        with structlog.contextvars.bound_contextvars(tenant_id=str(tenant_id), task=self.name):
            with tenant_scope(UUID(str(tenant_id))):
                return super().__call__(*args, **kwargs)


def enqueue_on_commit(task: Task, ctx: ExecutionContext, *args: Any, **kwargs: Any) -> None:
    """Queue ``task`` for ctx's tenant once the current transaction commits.

    A worker then never sees a row that was rolled back.
    """
    task_kwargs = {**kwargs, "tenant_id": str(ctx.tenant_id)}
    transaction.on_commit(lambda: task.apply_async(args=args, kwargs=task_kwargs))
