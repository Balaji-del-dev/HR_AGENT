from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantScopedModel


class Offer(TenantScopedModel):
    """An offer inside an approved comp band. HR, then finance, approve it before it is sent."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    application = models.ForeignKey("applications.JobApplication", on_delete=models.CASCADE, related_name="offers")
    comp_band = models.ForeignKey("requisitions.CompBand", on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    bonus_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    rationale = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(base_salary__gt=0), name="offer_salary_positive"),
        ]


class OfferStatusHistory(TenantScopedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["offer", "created_at"]
