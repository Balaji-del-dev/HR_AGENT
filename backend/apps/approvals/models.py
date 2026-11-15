from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import TenantScopedModel


class ApprovalRequest(TenantScopedModel):
    """One gated decision on one draft: a JD, an email, an offer step, a shortlist.

    Only a user holding one of ``required_roles`` (and, when ``assignee`` is
    set, only that user) can decide it. Offers use a chain: step 1 is HR,
    step 2 is finance; each step is its own request.
    """

    class Kind(models.TextChoices):
        REQUISITION = "requisition", "Requisition"
        JOB_DESCRIPTION = "job_description", "Job description"
        EMAIL = "email", "Email"
        OFFER = "offer", "Offer"
        SHORTLIST_REVIEW = "shortlist_review", "Shortlist review"
        INTERVIEW_SCHEDULE = "interview_schedule", "Interview schedule"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(max_length=24, choices=Kind.choices)
    target_id = models.UUIDField(help_text="The draft or record being decided.")
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True, help_text="Snapshot shown to the approver.")
    required_roles = ArrayField(models.CharField(max_length=32))
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    requisition = models.ForeignKey(
        "requisitions.JobRequisition", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    step = models.PositiveSmallIntegerField(default=1)
    chain_length = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey(
        "agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_requests"
    )
    review_round = models.PositiveSmallIntegerField(default=1)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status"], name="approval_tenant_status")]
        constraints = [
            models.UniqueConstraint(
                fields=["agent_run", "review_round", "step"],
                condition=models.Q(agent_run__isnull=False),
                name="approval_unique_run_round_step",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ApprovalDecision(TenantScopedModel):
    class Decision(models.TextChoices):
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        REQUEST_CHANGES = "request_changes", "Request changes"

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="decisions")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=16, choices=Decision.choices)
    reason = models.TextField(blank=True)
    edits = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["request", "created_at"]
