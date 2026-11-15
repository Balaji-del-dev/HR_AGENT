from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class EmailTemplate(TenantScopedModel):
    """A reviewed message template. Placeholders use Jinja2 syntax, e.g. {{ candidate_first_name }}."""

    class Kind(models.TextChoices):
        OUTREACH = "outreach", "Outreach"
        UPDATE = "update", "Status update"
        DECLINE = "decline", "Decline"
        INVITE = "invite", "Interview invite"
        OFFER = "offer", "Offer"

    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="emailtemplate_unique_key")]

    def __str__(self) -> str:
        return self.name


class EmailDraft(TenantScopedModel):
    """A message waiting for a person. It is sent only after an approved ApprovalRequest."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="email_drafts")
    application = models.ForeignKey(
        "applications.JobApplication", on_delete=models.CASCADE, null=True, blank=True, related_name="email_drafts"
    )
    interview = models.ForeignKey(
        "interviews.Interview", on_delete=models.CASCADE, null=True, blank=True, related_name="email_drafts"
    )
    kind = models.CharField(max_length=16, choices=EmailTemplate.Kind.choices)
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    idempotency_key = models.CharField(max_length=80, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class EmailMessage(TenantScopedModel):
    """A message that was actually sent. One per draft, which makes sending idempotent."""

    draft = models.OneToOneField(EmailDraft, on_delete=models.CASCADE, related_name="message")
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField()
    provider = models.CharField(max_length=40)
