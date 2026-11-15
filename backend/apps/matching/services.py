"""Stores the Matching and Validation Agents' criteria matrix. There is no overall score."""

from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet

from apps.applications.selectors import get_visible_application, visible_applications
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, NotFound
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.jobs.selectors import approved_jd
from apps.matching.models import CriterionResult, MatchingAssessment


def save_assessment(
    ctx: ExecutionContext,
    *,
    application_id: UUID,
    criteria: list[dict[str, Any]],
    run_id: UUID | None,
    prompt_version: str,
    model_name: str,
    graph_version: str,
) -> MatchingAssessment:
    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        application = get_visible_application(ctx, application_id)
        jd = approved_jd(application.requisition_id)
        if jd is None:
            raise ApplicationError("The requisition has no approved JD to match against.")
        statuses = [item["status"] for item in criteria]
        assessment = MatchingAssessment.objects.create(
            application=application,
            requisition_id=application.requisition_id,
            candidate_id=application.candidate_id,
            job_description=jd,
            agent_run_id=run_id,
            status=MatchingAssessment.Status.COMPLETED,
            prompt_version=prompt_version,
            model_name=model_name,
            graph_version=graph_version,
            summary={
                "documented": statuses.count(CriterionResult.Status.DOCUMENTED),
                "not_documented": statuses.count(CriterionResult.Status.NOT_DOCUMENTED),
                "unclear": statuses.count(CriterionResult.Status.UNCLEAR),
                "unsupported_claims_dropped": sum(len(item.get("rejected_evidence", [])) for item in criteria),
                "mandatory_gaps": [
                    item["criterion"]
                    for item in criteria
                    if item["level"] == "mandatory" and item["status"] != CriterionResult.Status.DOCUMENTED
                ],
            },
        )
        CriterionResult.objects.bulk_create(
            [
                CriterionResult(
                    tenant_id=ctx.tenant_id,
                    assessment=assessment,
                    requirement_id=item.get("requirement_id"),
                    criterion=item["criterion"],
                    level=item["level"],
                    status=item["status"],
                    model_status=item.get("model_status", item["status"]),
                    evidence=item.get("evidence", []),
                    rejected_evidence=item.get("rejected_evidence", []),
                    validation_note=item.get("validation_note", ""),
                    question=item.get("question", ""),
                    position=index,
                )
                for index, item in enumerate(criteria)
            ]
        )
        record_audit(
            ctx,
            action="assessment.saved",
            target_type="application",
            target_id=application.id,
            run_id=run_id,
            details=assessment.summary,
        )
    return assessment


def assessments_for_requisition(ctx: ExecutionContext, requisition_id: UUID) -> QuerySet[MatchingAssessment]:
    return (
        MatchingAssessment.objects.filter(
            tenant_id=ctx.tenant_id,
            requisition_id=requisition_id,
            application__in=visible_applications(ctx).values("pk"),
        )
        .select_related("application", "job_description")
        .prefetch_related("criteria")
    )


def latest_assessment(ctx: ExecutionContext, application_id: UUID) -> MatchingAssessment:
    application = get_visible_application(ctx, application_id)
    assessment = application.assessments.prefetch_related("criteria").order_by("-created_at").first()
    if assessment is None:
        raise NotFound("No assessment yet for this application.")
    return assessment
