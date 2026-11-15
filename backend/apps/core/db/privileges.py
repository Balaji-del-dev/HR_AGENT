"""Grants for the runtime database role."""

import logging
import re
from typing import Any

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

# Tables the runtime role may only add to and read. Audit history cannot be
# rewritten by application code, an agent, or anyone with the app's credentials.
APPEND_ONLY_TABLES = ("governance_auditevent", "governance_dataaccesslog")

# Schema that holds LangGraph checkpoints (created by `manage.py setup_agent_checkpoints`).
CHECKPOINT_SCHEMA = "langgraph"


def grant_app_role_privileges(using: str = "default", **_: Any) -> None:
    """Give the runtime role DML (not DDL, not TRUNCATE) on every table and sequence.

    Runs after each `migrate`, so tables added by any app are covered. Granting
    is idempotent. Ownership stays with the migration role, which is what keeps
    the runtime role subject to Row-Level Security.
    """
    role = settings.DATABASE_APP_ROLE
    if not _ROLE_NAME.match(role):
        raise ValueError(f"DATABASE_APP_ROLE {role!r} is not a valid role name.")
    connection = connections[using]
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        (current_user,) = cursor.fetchone()
        if current_user == role:
            return  # nothing to grant to ourselves; migrations should not run as this role anyway
        quoted = connection.ops.quote_name(role)
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted}")
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted}")
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(%s)",
            [list(APPEND_ONLY_TABLES)],
        )
        for (table,) in cursor.fetchall():
            cursor.execute(f"REVOKE UPDATE, DELETE ON {connection.ops.quote_name(table)} FROM {quoted}")
    logger.info("granted runtime privileges", extra={"role": role})
