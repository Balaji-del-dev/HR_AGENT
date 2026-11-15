"""Migration operations for tenant isolation."""

from typing import Any

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation
from django.db.migrations.state import ProjectState

from apps.core.tenancy import CURRENT_TENANT_SQL

POLICY_NAME = "tenant_isolation"


class EnableRowLevelSecurity(Operation):
    """Turn on Row-Level Security for a TenantScopedModel's table.

    Add it to the migration that creates the model, right after CreateModel::

        EnableRowLevelSecurity("jobrequisition"),

    The table owner (the migration role) still bypasses the policy; the
    runtime role does not, because it neither owns the table nor has BYPASSRLS.
    """

    reversible = True
    reduces_to_sql = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__qualname__, [self.model_name], {})

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        pass  # database-only change

    def _table(self, app_label: str, schema_editor: BaseDatabaseSchemaEditor, state: ProjectState) -> str:
        model = state.apps.get_model(app_label, self.model_name)
        return schema_editor.quote_name(model._meta.db_table)

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, schema_editor, to_state)
        policy = schema_editor.quote_name(POLICY_NAME)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"USING (tenant_id = {CURRENT_TENANT_SQL}) "
            f"WITH CHECK (tenant_id = {CURRENT_TENANT_SQL})"
        )

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, schema_editor, from_state)
        schema_editor.execute(f"DROP POLICY IF EXISTS {schema_editor.quote_name(POLICY_NAME)} ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    def describe(self) -> str:
        return f"Enable row-level security on {self.model_name}"

    @property
    def migration_name_fragment(self) -> str:
        return f"rls_{self.model_name}"
