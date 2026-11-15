from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.jobs"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.jobs.services import on_jd_decided

        register_handler("job_description", on_jd_decided)
