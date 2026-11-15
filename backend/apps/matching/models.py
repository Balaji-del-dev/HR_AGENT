"""AI assessments and human decisions, kept in separate tables.

A MatchingAssessment is a criteria matrix: for each job requirement, is it
documented in the resume, with which evidence. It has no overall score, so
nothing can quietly reject a candidate. RecruiterDecision records what a
person decided and why.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class MatchingAssessment(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    application = models.ForeignKey("applications.JobApplication", on_delete=models.CASCADE, related_name="assessments")
    requisition = models.ForeignKey("requisitions.JobRequisition", on_delete=models.CASCADE, related_name="+")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="assessments")
    job_description = models.ForeignKey("jobs.JobDescription", on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Versions used, so any result can be reproduced.
    prompt_version = models.CharField(max_length=80, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    graph_version = models.CharField(max_length=40, blank=True)
    # {"documented": 3, "not_documented": 1, "unclear": 0, "unsupported_claims_dropped": 1}
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class CriterionResult(TenantScopedModel):
    class Status(models.TextChoices):
        DOCUMENTED = "documented", "Documented"
        NOT_DOCUMENTED = "not_documented", "Not documented"
        UNCLEAR = "unclear", "Unclear"

    assessment = models.ForeignKey(MatchingAssessment, on_delete=models.CASCADE, related_name="criteria")
    requirement = models.ForeignKey(
        "jobs.JobRequirement", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    criterion = models.CharField(max_length=120)
    level = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=Status.choices)
    model_status = models.CharField(max_length=16, choices=Status.choices, help_text="Before validation.")
    evidence = models.JSONField(default=list, blank=True)  # validated [{"span_id", "quote"}]
    rejected_evidence = models.JSONField(default=list, blank=True)  # claims the Validation Agent dropped
    validation_note = models.TextField(blank=True)
    question = models.TextField(blank=True, help_text="What to ask the candidate about a gap.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["assessment", "position"]


class RecruiterDecision(TenantScopedModel):
    class Decision(models.TextChoices):
        ADVANCE = "advance", "Advance"
        HOLD = "hold", "Hold"
        REJECT = "reject", "Reject"

    application = models.ForeignKey("applications.JobApplication", on_delete=models.CASCADE, related_name="decisions")
    assessment = models.ForeignKey(
        MatchingAssessment, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions"
    )
    decision = models.CharField(max_length=8, choices=Decision.choices)
    from_stage = models.CharField(max_length=16)
    to_stage = models.CharField(max_length=16, blank=True)
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey("agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
