from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        from apps.core.db.privileges import grant_app_role_privileges

        # sender=self: run once per `migrate`, after every app's migrations.
        post_migrate.connect(grant_app_role_privileges, sender=self, dispatch_uid="core.grant_app_role")
