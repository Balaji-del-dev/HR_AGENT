from django.apps import AppConfig


class MatchingConfig(AppConfig):
    name = "apps.matching"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.matching.review import on_shortlist_decided

        register_handler("shortlist_review", on_shortlist_decided)
