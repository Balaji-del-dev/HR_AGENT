from django.apps import AppConfig


class OffersConfig(AppConfig):
    name = "apps.offers"

    def ready(self) -> None:
        from apps.approvals.services import register_handler
        from apps.offers.services import on_offer_decided

        register_handler("offer", on_offer_decided)
