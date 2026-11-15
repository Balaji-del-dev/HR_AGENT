from django.apps import AppConfig


class InterviewsConfig(AppConfig):
    name = "apps.interviews"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.interviews.services import on_schedule_decided

        register_handler("interview_schedule", on_schedule_decided)
