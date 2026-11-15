"""
Active-tenant handling for one unit of work (an API request or a Celery task).

The active tenant lives in two places that must agree:

* a contextvar, read by Python code (model saves, service guards, logs);
* the PostgreSQL setting ``app.tenant_id``, read by the Row-Level Security
  policies. It is set with ``set_config(..., is_local => true)`` so it ends
  with the transaction and cannot leak to the next user of a pooled connection.

Use :func:`tenant_scope` to run code for a tenant. Inside an API request, the
base view calls :func:`activate_tenant` directly, because ATOMIC_REQUESTS has
already opened the transaction.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper

from apps.core.exceptions import TenantScopeError

TENANT_SETTING = "app.tenant_id"

# The SQL every tenant-isolation policy compares tenant_id against. Once a
# transaction that set the value ends, current_setting() returns '' rather than
# NULL, and ''::uuid is an error; NULLIF turns "no tenant" into NULL, which
# matches no rows.
CURRENT_TENANT_SQL = f"NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"

_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> UUID | None:
    return _current_tenant.get()


def _write_db_setting(connection: BaseDatabaseWrapper, tenant_id: UUID | None) -> None:
    value = "" if tenant_id is None else str(tenant_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_SETTING, value])


def activate_tenant(tenant_id: UUID, *, using: str = DEFAULT_DB_ALIAS) -> Token[UUID | None]:
    """Make ``tenant_id`` active for the rest of the current transaction."""
    if not isinstance(tenant_id, UUID):
        raise TypeError(f"tenant_id must be a UUID, got {type(tenant_id).__name__}")
    connection = connections[using]
    if not connection.in_atomic_block:
        raise TenantScopeError(
            "activate_tenant() needs an open transaction: outside one, the "
            "transaction-local database setting would be lost immediately."
        )
    _write_db_setting(connection, tenant_id)
    return _current_tenant.set(tenant_id)


def deactivate(*, using: str = DEFAULT_DB_ALIAS) -> None:
    """Clear the active tenant. Called by middleware at the start and end of each request.

    In production the request transaction has already ended, so only the
    contextvar needs clearing. When the request ran inside an outer
    transaction (tests), the database setting is cleared too.
    """
    _current_tenant.set(None)
    connection = connections[using]
    if connection.connection is not None and connection.in_atomic_block and not connection.needs_rollback:
        _write_db_setting(connection, None)


@contextmanager
def tenant_scope(tenant_id: UUID | str, *, using: str = DEFAULT_DB_ALIAS) -> Iterator[UUID]:
    """Run the block inside a transaction with ``tenant_id`` active.

    Nesting is safe: on normal exit the enclosing tenant (or none) is restored
    in both the contextvar and the database. ``SET LOCAL`` values survive a
    savepoint release, so the restore must be explicit. On error the savepoint
    rollback restores the database value by itself.
    """
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    connection = connections[using]
    nested = connection.in_atomic_block
    previous = _current_tenant.get()
    with transaction.atomic(using=using):
        token = activate_tenant(tenant_uuid, using=using)
        try:
            yield tenant_uuid
            if nested:
                _write_db_setting(connection, previous)
        finally:
            _current_tenant.reset(token)


def require_active_tenant(tenant_id: UUID) -> None:
    """Fail loudly if code runs for one tenant while another (or none) is active."""
    active = _current_tenant.get()
    if active != tenant_id:
        raise TenantScopeError(f"Expected active tenant {tenant_id}, but {active} is active.")
