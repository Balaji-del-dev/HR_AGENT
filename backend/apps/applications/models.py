from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class JobApplication(TenantScopedModel):
    """A candidate in a requisition's pipeline. Stages change only through a recorded decision."""

    class Stage(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREENING = "screening", "Screening"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    requisition = models.ForeignKey(
        "requisitions.JobRequisition", on_delete=models.CASCADE, related_name="applications"
    )
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="applications")
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.APPLIED)
    source = models.CharField(max_length=40, blank=True)
    stage_changed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "requisition", "stage"], name="application_req_stage")]
        constraints = [
            models.UniqueConstraint(fields=["requisition", "candidate"], name="application_unique_req_candidate"),
        ]

    def __str__(self) -> str:
        return f"{self.candidate_id} -> {self.requisition_id} ({self.stage})"


class ApplicationStageHistory(TenantScopedModel):
    """Every stage change, with the person who made it and why."""

    application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name="stage_history")
    from_stage = models.CharField(max_length=16, choices=JobApplication.Stage.choices)
    to_stage = models.CharField(max_length=16, choices=JobApplication.Stage.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField()

    class Meta:
        ordering = ["application", "created_at"]
