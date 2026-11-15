from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import TenantScopedModel


class JDTemplate(TenantScopedModel):
    """A reviewed JD outline the JD Generation Agent starts from. Managed by HR admins."""

    name = models.CharField(max_length=120)
    department = models.CharField(max_length=120, blank=True, help_text="Blank means any department.")
    body = models.TextField(help_text="Markdown outline: section headings and house style notes.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class JobDescription(TenantScopedModel):
    """One version of a requisition's JD. Approved versions become JobRequirement rows."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"

    requisition = models.ForeignKey(
        "requisitions.JobRequisition", on_delete=models.CASCADE, related_name="job_descriptions"
    )
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    responsibilities = models.JSONField(default=list, blank=True)
    # [{"name": "Python", "level": "mandatory", "aliases": ["py"]}, ...]
    requirements = models.JSONField(default=list, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    compliance_flags = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    prompt_version = models.CharField(max_length=80, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["requisition", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["requisition", "version"], name="jd_unique_requisition_version"),
        ]

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"


class JobRequirement(TenantScopedModel):
    """One criterion from an approved JD. Matching compares each one to resume evidence."""

    class Level(models.TextChoices):
        MANDATORY = "mandatory", "Mandatory"
        REQUIRED = "required", "Required"
        PREFERRED = "preferred", "Preferred"

    job_description = models.ForeignKey(JobDescription, on_delete=models.CASCADE, related_name="requirement_rows")
    requisition = models.ForeignKey(
        "requisitions.JobRequisition", on_delete=models.CASCADE, related_name="requirements"
    )
    name = models.CharField(max_length=120)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.REQUIRED)
    aliases = ArrayField(models.CharField(max_length=80), default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["job_description", "position"]
        constraints = [
            models.UniqueConstraint(fields=["job_description", "name"], name="requirement_unique_jd_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.level})"
