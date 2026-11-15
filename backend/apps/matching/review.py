"""The shortlist review: the recruiter's per-candidate decisions after a matching run."""

from uuid import UUID

from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError


def on_shortlist_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    """On approve, ``edits["decisions"]`` lists one decision per candidate, each with a reason.

    Rejecting the review records nothing: the candidates stay where they are.
    """
    from apps.applications.services import record_decision

    if decision.decision != ApprovalDecision.Decision.APPROVE:
        return True
    items = decision.edits.get("decisions", [])
    if not isinstance(items, list) or not items:
        raise ApplicationError("Record at least one candidate decision.", details={"decisions": ["Required."]})
    assessments = {item["application_id"]: item.get("assessment_id") for item in request.payload.get("assessments", [])}
    for item in items:
        application_id = str(item.get("application_id", ""))
        if application_id not in assessments:
            raise ApplicationError("A decision names an application outside this review.")
        record_decision(
            ctx,
            application_id=UUID(application_id),
            decision=str(item.get("decision", "")),
            reason=str(item.get("reason", "")),
            to_stage=item.get("to_stage") or None,
            assessment_id=UUID(assessments[application_id]) if assessments[application_id] else None,
            run_id=request.agent_run_id,
        )
    return True
