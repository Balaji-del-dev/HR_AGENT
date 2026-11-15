from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TenantScopedModel


class Interview(TenantScopedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    application = models.ForeignKey("applications.JobApplication", on_delete=models.CASCADE, related_name="interviews")
    title = models.CharField(max_length=200)
    round = models.PositiveSmallIntegerField(default=1)
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True, help_text="Room or video link.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["application", "round"]
        constraints = [
            models.CheckConstraint(
                condition=Q(scheduled_end__isnull=True) | Q(scheduled_end__gt=F("scheduled_start")),
                name="interview_end_after_start",
            ),
        ]


class InterviewPanelist(TenantScopedModel):
    """An interviewer on a panel: the object-level grant for interviewers."""

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="panel")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["interview", "user"], name="panelist_unique_interview_user"),
        ]


class InterviewSlot(TenantScopedModel):
    """A time the Scheduling Agent proposed. The recruiter confirms one."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFIRMED = "confirmed", "Confirmed"
        DECLINED = "declined", "Declined"

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="slots")
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["interview", "start"]
        constraints = [
            models.CheckConstraint(condition=Q(end__gt=F("start")), name="slot_end_after_start"),
        ]


class Scorecard(TenantScopedModel):
    """Structured feedback from one interviewer for one interview."""

    class Recommendation(models.TextChoices):
        STRONG_NO = "strong_no", "Strong no"
        NO = "no", "No"
        YES = "yes", "Yes"
        STRONG_YES = "strong_yes", "Strong yes"

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="scorecards")
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    recommendation = models.CharField(max_length=12, choices=Recommendation.choices, blank=True)
    ratings = models.JSONField(default=dict, blank=True)  # {"Python": 4, "System design": 3}
    strengths = models.TextField(blank=True)
    concerns = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["interview", "interviewer"], name="scorecard_unique_interviewer"),
        ]
