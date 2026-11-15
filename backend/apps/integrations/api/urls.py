from django.urls import path

from apps.integrations.api.views import AtsWebhookView, router

urlpatterns = [
    path(
        "integrations/webhooks/<slug:tenant_slug>/<uuid:connection_id>/", AtsWebhookView.as_view(), name="ats-webhook"
    ),
    *router.urls,
]
