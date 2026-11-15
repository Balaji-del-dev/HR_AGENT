"""Agent run records. The graph code lives in agent_engine/; these tables trace every run."""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class AgentRun(TenantScopedModel):
    """One LangGraph run. Its id is the LangGraph thread_id, so paused runs can be resumed."""

    class Kind(models.TextChoices):
        REQUISITION_REVIEW = "requisition_review", "Requisition review"
        JD_GENERATION = "jd_generation", "JD generation"
        SOURCING = "sourcing", "Candidate sourcing"
        RESUME_PARSING = "resume_parsing", "Resume parsing"
        MATCHING = "matching", "Candidate matching"
        COMMUNICATION = "communication", "Communication"
        SCHEDULING = "scheduling", "Interview scheduling"
        FEEDBACK_SUMMARY = "feedback_summary", "Interview feedback"
        OFFER = "offer", "Offer workflow"
        ASSISTANT = "assistant", "Recruiter assistant"
        ANALYTICS = "analytics", "Recruitment analytics"
        COMPLIANCE = "compliance", "Compliance check"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        AWAITING_REVIEW = "awaiting_review", "Awaiting review"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        BUDGET_EXCEEDED = "budget_exceeded", "Budget exceeded"

    kind = models.CharField(max_length=24, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    requisition = models.ForeignKey(
        "requisitions.JobRequisition", on_delete=models.CASCADE, null=True, blank=True, related_name="agent_runs"
    )
    thread = models.ForeignKey("AssistantThread", on_delete=models.CASCADE, null=True, blank=True, related_name="runs")
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(default=dict, blank=True)
    pending_interrupt = models.JSONField(null=True, blank=True)
    graph_name = models.CharField(max_length=60, default="supervisor")
    graph_version = models.CharField(max_length=20)
    prompt_versions = models.JSONField(default=dict, blank=True)  # {"jd_generation": "jd_generation@3"}
    model_name = models.CharField(max_length=120, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    tool_call_count = models.PositiveIntegerField(default=0)
    guard_flags = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status"], name="agentrun_tenant_status")]

    def __str__(self) -> str:
        return f"{self.kind} {self.id} ({self.status})"


class AgentStep(TenantScopedModel):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveIntegerField()
    node = models.CharField(max_length=60)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["run", "sequence"]


class ToolCall(TenantScopedModel):
    class Status(models.TextChoices):
        OK = "ok", "OK"
        DENIED = "denied", "Denied by policy"
        INVALID = "invalid", "Invalid arguments"
        ERROR = "error", "Error"

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    tool = models.CharField(max_length=60)
    agent = models.CharField(max_length=40)
    arguments = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    policy_reason = models.CharField(max_length=200, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["run", "created_at"]


class AssistantThread(TenantScopedModel):
    """A Recruiter Assistant conversation. Each turn is an AgentRun."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    title = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or str(self.id)


class PromptVersion(models.Model):
    """A prompt template as shipped in Git. Platform-wide, not tenant data."""

    name = models.CharField(max_length=60)
    version = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    template = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="prompt_unique_name_version"),
            models.UniqueConstraint(fields=["name", "sha256"], name="prompt_unique_name_sha"),
        ]

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


class ModelConfig(models.Model):
    """Inventory of models allowed for each purpose, with their latest eval results."""

    name = models.CharField(max_length=80, unique=True)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120)
    purpose = models.CharField(max_length=60, default="general")
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class EvalResult(models.Model):
    """One run of an evaluation suite (extraction, matching, fairness, red team...)."""

    suite = models.CharField(max_length=60)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120)
    prompt_versions = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict)
    thresholds = models.JSONField(default=dict, blank=True)
    passed = models.BooleanField()
    details = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.suite} ({'pass' if self.passed else 'fail'})"
