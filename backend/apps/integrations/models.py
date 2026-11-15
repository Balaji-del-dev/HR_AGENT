from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TenantScopedModel


class IntegrationConnection(TenantScopedModel):
    """A configured connector. Secrets are never stored here, only the name of the env var holding them."""

    class Kind(models.TextChoices):
        ATS = "ats", "Applicant tracking system"
        CALENDAR = "calendar", "Calendar"
        EMAIL = "email", "Email"

    class Provider(models.TextChoices):
        CSV_IMPORT = "csv_import", "CSV import (local ATS)"
        WEBHOOK = "webhook", "Signed webhook (any ATS)"
        LOCAL_CALENDAR = "local_calendar", "Built-in calendar"
        DJANGO_MAIL = "django_mail", "Django mail backend"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict, blank=True)
    secret_env_var = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class SyncRun(TenantScopedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="sync_runs")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class WebhookEvent(TenantScopedModel):
    """An inbound ATS event. The unique event id makes redelivery harmless."""

    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="events")
    event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "event_id"], name="webhook_unique_event"),
        ]


class CalendarBusyBlock(TenantScopedModel):
    """A busy period on the built-in calendar. Scheduling reads these for free/busy."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    start = models.DateTimeField()
    end = models.DateTimeField()
    title = models.CharField(max_length=200, default="Busy")
    interview = models.ForeignKey(
        "interviews.Interview", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["user", "start"]
        constraints = [
            models.CheckConstraint(condition=Q(end__gt=F("start")), name="busy_end_after_start"),
        ]
