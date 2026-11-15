"""Communication, Interview Scheduling, Interview Feedback and Offer Workflow Agents."""

import hashlib
from decimal import Decimal
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from agent_engine.nodes.common import llm_structured, tool_call
from agent_engine.schemas import EmailDraftOut, FeedbackSummary, OfferProposal
from agent_engine.state import RecruitingState
from apps.core.context import ExecutionContext


def _idempotency_key(*parts: Any) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:64]


def comms(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    from apps.applications.selectors import get_visible_application
    from apps.core.tenancy import tenant_scope

    agent = "communication"
    ctx = runtime.context
    params = state["params"]
    kind = params.get("kind", "update")
    with tenant_scope(ctx.tenant_id):
        application = get_visible_application(ctx, params["application_id"])
        job_title, stage = application.requisition.title, application.stage
    template = tool_call(runtime, agent, "get_template", kind=kind, key=params.get("template_key", ""))
    data = {
        "kind": kind,
        "template": template,
        "job_title": job_title,
        "stage": stage,
        "instructions": params.get("instructions", ""),
        "feedback": state.get("feedback", ""),
    }
    draft = llm_structured("communication", data, EmailDraftOut, config)
    flags = tool_call(runtime, agent, "check_inclusive_language", text=f"{draft.subject}\n{draft.body}")
    saved = tool_call(
        runtime,
        agent,
        "create_email_draft",
        application_id=params["application_id"],
        kind=kind,
        subject=draft.subject,
        body=draft.body,
        idempotency_key=_idempotency_key(ctx.run_id, params["application_id"], kind, state.get("review_round", 1)),
    )
    return {
        "drafts": [{"type": "email", "id": saved["id"]}],
        "review": {
            "type": "approve_email",
            "kind": "email",
            "target_id": saved["id"],
            "title": f"Approve email: {saved['subject']}",
        },
        "result": {"email_draft_id": saved["id"], "language_flags": flags},
    }


INVITE_SUBJECT = "Interview for {{ job_title }} at {{ company_name }}"
INVITE_BODY = (
    "Hi {{ candidate_first_name }},\n\nThank you for your interest in the {{ job_title }} role. We would like to "
    "invite you to an interview on {{ slot_time }}.\n\nPlease reply to confirm, or let us know if you need a "
    "different time or any accommodations.\n\nBest regards,\n{{ recruiter_name }}"
)


def scheduling(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    """Free/busy and slot finding are plain code; the recruiter confirms one slot, and only then is the invite sent."""
    agent = "scheduling"
    ctx = runtime.context
    interview_id = state["params"]["interview_id"]
    free = tool_call(
        runtime, agent, "calendar_free_busy", interview_id=interview_id, days=int(state["params"].get("days", 7))
    )
    if not free:
        return {
            "result": {
                "interview_id": interview_id,
                "slots": [],
                "note": "No common free time in the window. Widen it or adjust the panel.",
            }
        }
    slots = tool_call(runtime, agent, "propose_interview_slots", interview_id=interview_id, slots=free)
    template = tool_call(runtime, agent, "get_template", kind="invite")
    invite = tool_call(
        runtime,
        agent,
        "create_invite_draft",
        interview_id=interview_id,
        subject=(template or {}).get("subject") or INVITE_SUBJECT,
        body=(template or {}).get("body") or INVITE_BODY,
        idempotency_key=_idempotency_key(ctx.run_id, interview_id, "invite", state.get("review_round", 1)),
    )
    payload = {
        "interview_id": interview_id,
        "slots": slots,
        "recommended_slot_id": slots[0]["id"],
        "email_draft_id": invite["id"],
    }
    return {
        "drafts": [{"type": "invite", "id": invite["id"]}, *({"type": "slot", **s} for s in slots)],
        "review": {
            "type": "confirm_schedule",
            "kind": "interview_schedule",
            "target_id": interview_id,
            "title": "Confirm an interview time",
            "payload": payload,
        },
        "result": {"interview_id": interview_id, "slots": slots, "email_draft_id": invite["id"]},
    }


def feedback(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    agent = "feedback"
    application_id = state["params"]["application_id"]
    cards = tool_call(runtime, agent, "get_scorecards", application_id=application_id)
    if not cards:
        return {"result": {"application_id": application_id, "summary": "No submitted scorecards yet.", "points": []}}
    summary = llm_structured(
        "feedback_summary",
        {"scorecards": [{k: v for k, v in c.items() if k != "scorecard_id"} for c in cards]},
        FeedbackSummary,
        config,
    )
    refs = {card["ref"]: card["scorecard_id"] for card in cards}
    points = [
        {**p.model_dump(), "scorecard_id": refs[p.scorecard_ref]} for p in summary.points if p.scorecard_ref in refs
    ]
    dropped = len(summary.points) - len(points)
    return {
        "result": {
            "application_id": application_id,
            "summary": summary.summary,
            "points": points,
            "disagreements": summary.disagreements,
            "uncited_points_dropped": dropped,
            "scorecards": len(cards),
        }
    }


def offer(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    from apps.applications.selectors import get_visible_application
    from apps.core.tenancy import tenant_scope

    agent = "offer"
    ctx = runtime.context
    application_id = state["params"]["application_id"]
    with tenant_scope(ctx.tenant_id):
        requisition_id = str(get_visible_application(ctx, application_id).requisition_id)
    band = tool_call(runtime, agent, "get_comp_band", requisition_id=requisition_id)
    if band is None:
        return {"result": {"application_id": application_id, "note": "The requisition has no comp band."}}
    cards = tool_call(runtime, agent, "get_scorecards", application_id=application_id)
    proposal = llm_structured(
        "offer_proposal",
        {
            "band": band,
            "level": band["level"],
            "feedback": state.get("feedback", ""),
            "scorecards": [{"recommendation": c["recommendation"], "ratings": c["ratings"]} for c in cards],
        },
        OfferProposal,
        config,
    )
    low, high = Decimal(band["min"]), Decimal(band["max"])
    salary = Decimal(str(proposal.base_salary)).quantize(Decimal("1"))
    clamped = salary < low or salary > high
    salary = min(max(salary, low), high)  # code keeps the offer inside the band whatever the model said
    saved = tool_call(
        runtime,
        agent,
        "create_offer_draft",
        application_id=application_id,
        base_salary=salary,
        bonus_percent=Decimal(str(proposal.bonus_percent)) if proposal.bonus_percent is not None else None,
        rationale=proposal.rationale,
    )
    return {
        "drafts": [{"type": "offer", "id": saved["id"]}],
        "review": {
            "type": "approve_offer",
            "kind": "offer",
            "target_id": saved["id"],
            "title": f"Approve offer: {saved['currency']} {saved['base_salary']}",
        },
        "result": {"offer_id": saved["id"], "base_salary": saved["base_salary"], "clamped_to_band": clamped},
    }
