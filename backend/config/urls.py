from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.api.views import HealthView, ReadinessView

api_v1 = [
    path("", include(f"apps.{app}.api.urls"))
    for app in (
        "accounts",
        "requisitions",
        "jobs",
        "candidates",
        "documents",
        "applications",
        "interviews",
        "offers",
        "communications",
        "approvals",
        "agents",
        "integrations",
        "analytics",
        "governance",
    )
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", HealthView.as_view(), name="healthz"),
    path("readyz/", ReadinessView.as_view(), name="readyz"),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]

if settings.DEBUG:
    urlpatterns.append(path("api-auth/", include("rest_framework.urls")))
