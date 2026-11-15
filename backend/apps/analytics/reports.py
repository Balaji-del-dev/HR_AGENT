"""Whitelisted, read-only reports. The Recruitment Analytics Agent can only pick one of these.

Every report is scoped to requisitions the caller can see and returns the SQL
it ran, so people can check the numbers.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.db.models import Avg, Count, F, Q, QuerySet

from apps.agents.models import AgentRun, ToolCall
from apps.applications.models import ApplicationStageHistory, JobApplication
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError
from apps.matching.models import RecruiterDecision
from apps.requisitions.selectors import visible_requisitions


@dataclass
class Report:
    name: str
    title: str
    columns: list[str]
    rows: list[list[Any]]
    query: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "columns": self.columns,
            "rows": self.rows,
            "query": self.query,
            "notes": self.notes,
        }


def _applications(ctx: ExecutionContext, requisition_id: UUID | None) -> QuerySet[JobApplication]:
    queryset = JobApplication.objects.filter(
        tenant_id=ctx.tenant_id, requisition__in=visible_requisitions(ctx).values("pk")
    )
    if requisition_id:
        queryset = queryset.filter(requisition_id=requisition_id)
    return queryset


def pipeline_funnel(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    order = [s.value for s in JobApplication.Stage]
    queryset = _applications(ctx, requisition_id).values("stage").annotate(count=Count("id")).order_by("stage")
    counts = {row["stage"]: row["count"] for row in queryset}
    rows = [[stage, counts.get(stage, 0)] for stage in order]
    return Report("pipeline_funnel", "Applications by stage", ["stage", "applications"], rows, str(queryset.query))


def time_in_stage(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    history = ApplicationStageHistory.objects.filter(application__in=_applications(ctx, requisition_id).values("pk"))
    rows: list[list[Any]] = []
    entered: dict[tuple[UUID, str], Any] = {}
    durations: dict[str, list[float]] = {}
    for item in history.order_by("application_id", "created_at").values(
        "application_id", "from_stage", "to_stage", "created_at"
    ):
        start = entered.get((item["application_id"], item["from_stage"]))
        if start is not None:
            durations.setdefault(item["from_stage"], []).append((item["created_at"] - start).total_seconds() / 3600)
        entered[(item["application_id"], item["to_stage"])] = item["created_at"]
    for stage, values in sorted(durations.items()):
        rows.append([stage, round(sum(values) / len(values), 1), len(values)])
    return Report(
        "time_in_stage",
        "Average hours spent in each stage",
        ["stage", "avg_hours", "transitions"],
        rows,
        str(history.query),
        ["Only stages left through a recorded decision are counted."],
    )


def source_breakdown(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    queryset = (
        _applications(ctx, requisition_id)
        .values("source")
        .annotate(applications=Count("id"), hired=Count("id", filter=Q(stage=JobApplication.Stage.HIRED)))
        .order_by("-applications")
    )
    rows = [[row["source"] or "unknown", row["applications"], row["hired"]] for row in queryset]
    return Report(
        "source_breakdown",
        "Applications and hires by source",
        ["source", "applications", "hired"],
        rows,
        str(queryset.query),
    )


def override_rate(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    """How often people decided against the evidence: rejected with every mandatory criterion
    documented, or advanced with a mandatory gap. High rates are a review signal, not an error."""
    decisions = RecruiterDecision.objects.filter(
        application__in=_applications(ctx, requisition_id).values("pk"), assessment__isnull=False
    ).select_related("assessment")
    total = against = 0
    for decision in decisions:
        gaps = decision.assessment.summary.get("mandatory_gaps", []) if decision.assessment else []
        total += 1
        if (decision.decision == "reject" and not gaps) or (decision.decision == "advance" and gaps):
            against += 1
    rate = round(100 * against / total, 1) if total else 0.0
    return Report(
        "override_rate",
        "Decisions that went against the documented evidence",
        ["decisions_with_assessment", "against_evidence", "rate_percent"],
        [[total, against, rate]],
        str(decisions.query),
    )


def requisition_status(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    queryset = visible_requisitions(ctx).values("status").annotate(count=Count("id")).order_by("status")
    return Report(
        "requisition_status",
        "Requisitions by status",
        ["status", "requisitions"],
        [[row["status"], row["count"]] for row in queryset],
        str(queryset.query),
    )


def agent_health(ctx: ExecutionContext, requisition_id: UUID | None = None) -> Report:
    """Must-be-zero signals and run outcomes."""
    runs = AgentRun.objects.filter(tenant_id=ctx.tenant_id)
    by_status = runs.values("kind", "status").annotate(count=Count("id"), tokens=Avg(F("tokens_in") + F("tokens_out")))
    denied = ToolCall.objects.filter(tenant_id=ctx.tenant_id, status=ToolCall.Status.DENIED).count()
    rows = [[row["kind"], row["status"], row["count"], round(row["tokens"] or 0)] for row in by_status.order_by("kind")]
    return Report(
        "agent_health",
        "Agent runs by kind and status",
        ["kind", "status", "runs", "avg_tokens"],
        rows,
        str(by_status.query),
        [f"Tool calls denied by policy: {denied}"],
    )


REPORTS: dict[str, tuple[str, Callable[..., Report]]] = {
    "pipeline_funnel": ("Applications by stage (the hiring funnel)", pipeline_funnel),
    "time_in_stage": ("Average time candidates spend in each stage", time_in_stage),
    "source_breakdown": ("Where applicants and hires come from", source_breakdown),
    "override_rate": ("How often decisions went against the documented evidence", override_rate),
    "requisition_status": ("Requisitions by status", requisition_status),
    "agent_health": ("Agent runs, outcomes and policy denials", agent_health),
}


def run_report(ctx: ExecutionContext, name: str, *, requisition_id: UUID | None = None) -> Report:
    entry = REPORTS.get(name)
    if entry is None:
        raise ApplicationError(f"Unknown report {name!r}.", details={"report": sorted(REPORTS)})
    return entry[1](ctx, requisition_id)
