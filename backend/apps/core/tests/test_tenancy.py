"""The Python side of tenant scoping: contextvar, nesting, and model save guards."""

import uuid

import pytest
from django.db import connection

from apps.core.exceptions import TenantScopeError
from apps.core.tenancy import activate_tenant, get_current_tenant_id, require_active_tenant, tenant_scope
from apps.requisitions.models import JobRequisition
from apps.requisitions.tests.factories import JobRequisitionFactory

pytestmark = pytest.mark.django_db


def _db_tenant() -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT NULLIF(current_setting('app.tenant_id', true), '')")
        return cursor.fetchone()[0]


def test_scope_sets_and_clears_both_contextvar_and_database(tenant_a) -> None:
    with tenant_scope(tenant_a.id):
        assert get_current_tenant_id() == tenant_a.id
        assert _db_tenant() == str(tenant_a.id)
    assert get_current_tenant_id() is None
    assert _db_tenant() is None


def test_nested_scope_restores_the_outer_tenant(tenant_a, tenant_b) -> None:
    """SET LOCAL survives a savepoint release, so the inner scope must restore explicitly."""
    with tenant_scope(tenant_a.id):
        with tenant_scope(tenant_b.id):
            assert _db_tenant() == str(tenant_b.id)
        assert get_current_tenant_id() == tenant_a.id
        assert _db_tenant() == str(tenant_a.id)


def test_scope_rolled_back_by_an_error_restores_the_outer_tenant(tenant_a, tenant_b) -> None:
    with tenant_scope(tenant_a.id):
        with pytest.raises(ValueError), tenant_scope(tenant_b.id):
            raise ValueError("boom")
        assert get_current_tenant_id() == tenant_a.id
        assert _db_tenant() == str(tenant_a.id)


def test_scope_accepts_string_ids(tenant_a) -> None:
    with tenant_scope(str(tenant_a.id)) as active:
        assert active == tenant_a.id


@pytest.mark.django_db(transaction=True)
def test_activate_outside_a_transaction_is_refused() -> None:
    with pytest.raises(TenantScopeError, match="open transaction"):
        activate_tenant(uuid.uuid4())


def test_activate_rejects_non_uuid() -> None:
    with pytest.raises(TypeError):
        activate_tenant("not-a-uuid")  # type: ignore[arg-type]


def test_require_active_tenant(tenant_a, tenant_b) -> None:
    with pytest.raises(TenantScopeError):
        require_active_tenant(tenant_a.id)
    with tenant_scope(tenant_a.id):
        require_active_tenant(tenant_a.id)
        with pytest.raises(TenantScopeError):
            require_active_tenant(tenant_b.id)


def test_save_fills_tenant_from_the_active_scope(tenant_a) -> None:
    requisition = JobRequisitionFactory(tenant=tenant_a)
    assert requisition.tenant_id == tenant_a.id


def test_save_without_an_active_tenant_is_refused(tenant_a) -> None:
    requisition = JobRequisitionFactory(tenant=tenant_a)
    requisition.title = "Changed"
    with pytest.raises(TenantScopeError, match="no active tenant"):
        requisition.save()


def test_save_for_a_different_tenant_is_refused(tenant_a, tenant_b) -> None:
    requisition = JobRequisitionFactory(tenant=tenant_a)
    with tenant_scope(tenant_b.id), pytest.raises(TenantScopeError, match="while"):
        JobRequisition(
            tenant_id=tenant_a.id,
            title="x",
            department="y",
            hiring_manager=requisition.hiring_manager,
            created_by=requisition.hiring_manager,
        ).save()
