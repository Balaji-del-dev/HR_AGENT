from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    name = "apps.communications"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.communications.services import on_email_decided

        register_handler("email", on_email_decided)
