from django.apps import AppConfig


class RequisitionsConfig(AppConfig):
    name = "apps.requisitions"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.requisitions.services import on_requisition_decided

        register_handler("requisition", on_requisition_decided)
