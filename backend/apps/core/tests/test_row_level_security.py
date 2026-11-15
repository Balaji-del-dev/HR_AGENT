"""
Row-Level Security, tested at the database itself.

These tests deliberately skip the app's own tenant filters (selectors). They
query through the plain model manager or raw SQL, so they prove the database
alone keeps tenants apart even if application code forgets to filter.
"""

import pytest
from django.apps import apps
from django.conf import settings
from django.db import DatabaseError, connection, transaction

from apps.core.models import TenantScopedModel
from apps.core.tenancy import tenant_scope
from apps.requisitions.models import JobRequisition
from apps.requisitions.tests.factories import JobRequisitionFactory

pytestmark = pytest.mark.django_db

TENANT_TABLE_MODELS = [
    model for model in apps.get_models() if issubclass(model, TenantScopedModel) and not model._meta.proxy
]


def _fetchone(sql: str, params: list[object] | None = None) -> tuple[object, ...]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
    assert row is not None
    return tuple(row)


# --- Guardrails: the schema and roles are set up the way isolation needs ------------


def test_tenant_scoped_models_exist() -> None:
    # Guards the guardrail: if discovery broke, the parametrised test below would pass vacuously.
    assert JobRequisition in TENANT_TABLE_MODELS


@pytest.mark.parametrize("model", TENANT_TABLE_MODELS, ids=lambda m: m._meta.label)
def test_every_tenant_table_has_rls(model: type[TenantScopedModel]) -> None:
    """Fails the build when a new TenantScopedModel's migration lacks EnableRowLevelSecurity."""
    table = model._meta.db_table
    (rls_enabled,) = _fetchone("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", [table])
    assert rls_enabled, f"{table}: add EnableRowLevelSecurity({model._meta.model_name!r}) to its migration"

    using, with_check = _fetchone(
        "SELECT qual, with_check FROM pg_policies WHERE tablename = %s AND policyname = 'tenant_isolation'",
        [table],
    )
    for clause in (using, with_check):
        assert "current_setting('app.tenant_id'" in str(clause)


def test_tests_run_as_the_runtime_role() -> None:
    (current_user,) = _fetchone("SELECT current_user")
    assert current_user == settings.DATABASE_APP_ROLE


def test_runtime_role_cannot_bypass_rls() -> None:
    is_super, bypass_rls = _fetchone("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    assert not is_super
    assert not bypass_rls


@pytest.mark.parametrize("model", TENANT_TABLE_MODELS, ids=lambda m: m._meta.label)
def test_runtime_role_does_not_own_tenant_tables(model: type[TenantScopedModel]) -> None:
    (owner,) = _fetchone("SELECT tableowner FROM pg_tables WHERE tablename = %s", [model._meta.db_table])
    assert owner != settings.DATABASE_APP_ROLE


# --- Behaviour: reads and writes are confined to the active tenant -----------------


@pytest.fixture
def two_tenant_rows(tenant_a, tenant_b):
    return JobRequisitionFactory(tenant=tenant_a), JobRequisitionFactory(tenant=tenant_b)


def test_reads_see_only_the_active_tenant(tenant_a, tenant_b, two_tenant_rows) -> None:
    row_a, row_b = two_tenant_rows
    with tenant_scope(tenant_a.id):
        assert list(JobRequisition.objects.values_list("id", flat=True)) == [row_a.id]
    with tenant_scope(tenant_b.id):
        assert list(JobRequisition.objects.values_list("id", flat=True)) == [row_b.id]


def test_raw_sql_is_isolated_too(tenant_a, two_tenant_rows) -> None:
    with tenant_scope(tenant_a.id):
        (count,) = _fetchone("SELECT count(*) FROM requisitions_jobrequisition")
    assert count == 1


def test_no_active_tenant_sees_nothing(two_tenant_rows) -> None:
    assert JobRequisition.objects.count() == 0


def test_cannot_insert_a_row_for_another_tenant(tenant_a, tenant_b) -> None:
    hiring_manager = JobRequisitionFactory(tenant=tenant_a).hiring_manager
    foreign = JobRequisition(
        tenant_id=tenant_b.id,
        title="Smuggled",
        department="X",
        hiring_manager=hiring_manager,
        created_by=hiring_manager,
    )
    with tenant_scope(tenant_a.id):
        # bulk_create skips Model.save(), so only the database's WITH CHECK clause stands in the way.
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            JobRequisition.objects.bulk_create([foreign])


def test_cannot_move_a_row_to_another_tenant(tenant_a, tenant_b, two_tenant_rows) -> None:
    row_a, _ = two_tenant_rows
    with tenant_scope(tenant_a.id):
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            JobRequisition.objects.filter(pk=row_a.pk).update(tenant_id=tenant_b.id)


def test_cannot_update_or_delete_another_tenants_rows(tenant_a, tenant_b, two_tenant_rows) -> None:
    _, row_b = two_tenant_rows
    with tenant_scope(tenant_a.id):
        assert JobRequisition.objects.filter(pk=row_b.pk).update(title="Hijacked") == 0
        assert JobRequisition.objects.filter(pk=row_b.pk).delete()[0] == 0
    with tenant_scope(tenant_b.id):
        assert JobRequisition.objects.get(pk=row_b.pk).title == row_b.title


def test_table_owner_bypasses_rls_so_the_app_must_never_connect_as_owner(two_tenant_rows) -> None:
    """Documents why the runtime role exists: as owner, RLS does nothing."""
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
        try:
            cursor.execute("SELECT count(*) FROM requisitions_jobrequisition")
            (owner_count,) = cursor.fetchone()
        finally:
            cursor.execute(f"SET ROLE {connection.ops.quote_name(settings.DATABASE_APP_ROLE)}")
    assert owner_count == 2
    assert JobRequisition.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_tenant_setting_does_not_outlive_its_transaction(tenant_a) -> None:
    """A pooled connection must not carry one request's tenant into the next."""
    JobRequisitionFactory(tenant=tenant_a)  # commits inside its own tenant_scope
    with tenant_scope(tenant_a.id):
        assert JobRequisition.objects.count() == 1

    (setting,) = _fetchone("SELECT current_setting('app.tenant_id', true)")
    assert setting in ("", None)
    assert JobRequisition.objects.count() == 0
