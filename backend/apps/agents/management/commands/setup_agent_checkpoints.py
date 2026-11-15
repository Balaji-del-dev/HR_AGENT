"""Create the LangGraph checkpoint tables (schema ``langgraph``) and grant them to the runtime role.

Run as the owner role, after `migrate` (``make migrate`` does both). PostgresSaver.setup()
creates indexes CONCURRENTLY, so everything here runs on its own autocommit connection,
outside any Django transaction.
"""

from typing import Any

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand
from psycopg import sql

from apps.core.db.privileges import _ROLE_NAME, CHECKPOINT_SCHEMA


class Command(BaseCommand):
    help = "Create or upgrade the LangGraph checkpoint schema."

    def handle(self, *args: Any, **options: Any) -> None:
        from langgraph.checkpoint.postgres import PostgresSaver

        from agent_engine.runtime import checkpoint_conninfo

        role = settings.DATABASE_APP_ROLE
        if not _ROLE_NAME.match(role):
            raise ValueError(f"DATABASE_APP_ROLE {role!r} is not a valid role name.")
        schema, app_role = sql.Identifier(CHECKPOINT_SCHEMA), sql.Identifier(role)
        with psycopg.connect(checkpoint_conninfo(), autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
        with PostgresSaver.from_conn_string(checkpoint_conninfo()) as saver:
            saver.setup()
        with psycopg.connect(checkpoint_conninfo(), autocommit=True) as conn:
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, app_role))
            conn.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(
                    schema, app_role
                )
            )
            conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, app_role))
        self.stdout.write(self.style.SUCCESS("LangGraph checkpoint schema is ready."))
