"""Audit, access logs, retention and data-subject requests.

AuditEvent and DataAccessLog are append-only: the runtime database role has
INSERT and SELECT on them but no UPDATE or DELETE (see apps.core.db.privileges).
They store ids, never names or contact details, so they never need erasing.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class AuditEvent(TenantScopedModel):
    class ActorType(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent (on behalf of a user)"
        SYSTEM = "system", "System"

    actor_id = models.UUIDField(null=True, blank=True)
    actor_type = models.CharField(max_length=8, choices=ActorType.choices, default=ActorType.USER)
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=60)
    target_id = models.CharField(max_length=64, blank=True)
    run_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "target_type", "target_id"], name="audit_target"),
            models.Index(fields=["tenant", "created_at"], name="audit_created"),
        ]


class DataAccessLog(TenantScopedModel):
    class Action(models.TextChoices):
        VIEW = "view", "View"
        DOWNLOAD = "download", "Download"
        EXPORT = "export", "Export"

    actor_id = models.UUIDField()
    action = models.CharField(max_length=10, choices=Action.choices)
    target_type = models.CharField(max_length=60)
    target_id = models.CharField(max_length=64)
    request_id = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["-created_at"]


class RetentionPolicy(TenantScopedModel):
    class Target(models.TextChoices):
        CANDIDATES = "candidates", "Candidates with no open application"
        DOCUMENTS = "documents", "Resume files and extracted text"
        AGENT_RUNS = "agent_runs", "Finished agent runs and their checkpoints"

    target = models.CharField(max_length=16, choices=Target.choices)
    retain_days = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "target"], name="retention_unique_target")]


class DeletionRequest(TenantScopedModel):
    """A candidate's request to erase their data."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    candidate_ref = models.CharField(max_length=64, help_text="Stable id kept after erasure.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class SecurityIncident(TenantScopedModel):
    class Kind(models.TextChoices):
        SECURITY = "security", "Security"
        PRIVACY = "privacy", "Privacy"
        AI = "ai", "AI incident"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN)
    run_id = models.UUIDField(null=True, blank=True)
    reported_by_id = models.UUIDField(null=True, blank=True)
    root_cause = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
