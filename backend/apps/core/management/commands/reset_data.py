"""Delete every hiring record and keep only tenants, users and their roles.

    DB_USER=hr_owner DB_PASSWORD=... python manage.py reset_data --yes
    python manage.py reset_data --yes --keep-settings   # also keep pay bands, templates, retention rules

Removes requisitions, JDs, candidates, resumes (rows and stored files), applications,
assessments, interviews, offers, approvals, emails, agent runs and their LangGraph
checkpoints, integrations, the audit and access logs and sign-in attempt logs.

Keeps tenants, users, memberships (roles), prompt versions and model configs, and
Django's own tables. Local development only: it refuses to run unless DEBUG is on.
It needs the owner role, because the runtime role may not delete audit events.
"""

import shutil
from typing import Any

import psycopg
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from psycopg import sql

from apps.core.db.privileges import CHECKPOINT_SCHEMA

# Models whose rows survive a reset.
KEEP = {
    "accounts.user",
    "accounts.membership",
    "core.tenant",
    "agents.promptversion",
    "agents.modelconfig",
}
# Per-tenant configuration kept with --keep-settings.
SETTINGS_MODELS = {
    "requisitions.compband",
    "jobs.jdtemplate",
    "communications.emailtemplate",
    "governance.retentionpolicy",
}
# Third-party tables that only hold activity, cleared with the rest.
EXTRA_APPS = {"axes"}


def _tables_to_clear(keep_settings: bool) -> list[str]:
    keep = KEEP | (SETTINGS_MODELS if keep_settings else set())
    tables = []
    for model in apps.get_models(include_auto_created=True):
        label = model._meta.label_lower
        ours = model._meta.app_config.name.startswith("apps.") or model._meta.app_label in EXTRA_APPS
        if not ours or label in keep or not model._meta.managed:
            continue
        owner = model._meta.auto_created  # a many-to-many table belongs to the model that declares it
        if isinstance(owner, type) and owner._meta.label_lower in keep:
            continue  # e.g. a user's groups and permissions
        tables.append(model._meta.db_table)
    return sorted(set(tables))


class Command(BaseCommand):
    help = "Delete all hiring data, keeping only tenants, users and roles (local development only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
        parser.add_argument(
            "--keep-settings", action="store_true", help="Keep pay bands, JD and email templates, and retention rules."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("reset_data only runs with DEBUG on.")
        db = settings.DATABASES["default"]
        if db["USER"] == settings.DATABASE_APP_ROLE:
            raise CommandError(
                f"Run this as the owner role, not {db['USER']!r}: "
                "DB_USER=hr_owner DB_PASSWORD=... python manage.py reset_data"
            )
        tables = _tables_to_clear(options["keep_settings"])
        if not options["yes"]:
            self.stdout.write(f"This deletes all rows in {len(tables)} tables of {db['NAME']} on port {db['PORT']}:")
            self.stdout.write("  " + ", ".join(tables))
            if input("Type 'yes' to continue: ").strip().lower() != "yes":
                raise CommandError("Cancelled. Nothing was deleted.")

        conninfo = (
            f"host={db['HOST']} port={db['PORT']} dbname={db['NAME']} user={db['USER']} password={db['PASSWORD']}"
        )
        with psycopg.connect(conninfo, autocommit=False) as conn:
            conn.execute("SET lock_timeout = '15s'")  # fail clearly if a running request holds a table
            conn.execute(
                sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(sql.SQL(", ").join(map(sql.Identifier, tables)))
            )
            checkpoint_tables = [
                name
                for (name,) in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tablename <> 'checkpoint_migrations'",
                    [CHECKPOINT_SCHEMA],
                ).fetchall()
            ]
            if checkpoint_tables:
                conn.execute(
                    sql.SQL("TRUNCATE {}").format(
                        sql.SQL(", ").join(sql.Identifier(CHECKPOINT_SCHEMA, t) for t in checkpoint_tables)
                    )
                )
            conn.commit()

        removed = 0
        root = settings.OBJECT_STORAGE_ROOT
        if root.exists():
            for child in root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {len(tables)} tables and {len(checkpoint_tables)} checkpoint tables; "
                f"removed {removed} storage folders. Tenants, users and roles are unchanged."
            )
        )
