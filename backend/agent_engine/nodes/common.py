"""Nodes every graph shares, and the helper every LLM call goes through."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from agent_engine.budget import maybe_current_run
from agent_engine.guards.checks import (
    foreign_tenant_ids,
    protected_attribute_mentions,
    redact_contact_details,
    scan_input,
    strings_in,
)
from agent_engine.llm.factory import model_label, structured_model
from agent_engine.prompts import get_prompt
from agent_engine.state import RecruitingState
from agent_engine.tools import call_tool
from apps.core.context import ExecutionContext
from apps.core.tenancy import tenant_scope

logger = logging.getLogger(__name__)
MAX_REVIEW_ROUNDS = 3

KIND_TO_INTENT = {
    "requisition_review": "requisition_review",
    "jd_generation": "job_jd",
    "sourcing": "sourcing",
    "resume_parsing": "resume_parsing",
    "matching": "candidates",
    "communication": "comms",
    "scheduling": "scheduling",
    "feedback_summary": "feedback",
    "offer": "offer",
    "assistant": "assistant",
    "analytics": "analytics",
    "compliance": "compliance",
}
# The agent identity each intent's tools are checked against.
AGENT_FOR_INTENT = {
    "requisition_review": "requisition_review",
    "job_jd": "jd_generation",
    "sourcing": "sourcing",
    "resume_parsing": "resume_parsing",
    "candidates": "matching",
    "comms": "communication",
    "scheduling": "scheduling",
    "feedback": "feedback",
    "offer": "offer",
    "assistant": "assistant",
    "analytics": "analytics",
    "compliance": "compliance",
}


def ctx_of(runtime: Runtime[ExecutionContext]) -> ExecutionContext:
    return runtime.context


def tool_call(runtime: Runtime[ExecutionContext], agent: str, name: str, **arguments: Any) -> Any:
    return call_tool(ctx_of(runtime), agent=agent, name=name, **arguments)


def llm_structured[SchemaT: BaseModel](
    prompt_name: str, data: dict[str, Any], schema: type[SchemaT], config: RunnableConfig | None = None
) -> SchemaT:
    """Render a versioned prompt, call the model with structured output, validate.

    One retry with the validation error appended; then the error propagates and
    the node decides what to do (usually: record it and continue without the claim).
    """
    prompt = get_prompt(prompt_name)
    run = maybe_current_run()
    if run is not None:
        run.record_prompt(prompt_name, prompt.label)
    messages = prompt.render(data)
    runnable = structured_model(schema)
    try:
        return runnable.invoke(messages, config=config)
    except (ValidationError, ValueError) as exc:
        logger.info("structured output invalid; retrying once", extra={"prompt": prompt_name})
        retry = [
            *messages,
            HumanMessage(
                f"Your previous answer was invalid: {str(exc)[:500]}. Answer again, following the schema exactly."
            ),
        ]
        return runnable.invoke(retry, config=config)


def current_model_label() -> str:
    return model_label()


# ---------------------------------------------------------------- shared graph nodes


def guard_input(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    params = state.get("params", {})
    flags = []
    for key in ("message", "instructions", "question", "text"):
        if isinstance(params.get(key), str):
            flags += scan_input(params[key], source=key)
    return {"flags": flags}


def supervisor(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    """Deterministic routing first: almost every run arrives from a specific endpoint.
    Only free-text assistant messages go to the LLM classifier, and an unclear
    intent asks the user instead of guessing."""
    from agent_engine.llm.heuristics import ANALYTICS_WORDS
    from agent_engine.schemas import RouteDecision

    kind = state["kind"]
    intent = KIND_TO_INTENT.get(kind)
    if intent is None:
        return {"intent": "clarify", "result": {"answer": f"Unknown run kind {kind}."}}
    if kind != "assistant":
        return {"intent": intent}
    message = str(state["params"].get("message", "")).strip()
    if ANALYTICS_WORDS.search(message) and len(message.split()) <= 12:
        return {"intent": "analytics"}
    decision = llm_structured("supervisor_route", {"message": message}, RouteDecision, config)
    if decision.intent == "unclear":
        question = decision.clarifying_question or "Could you say more about what you need?"
        return {"intent": "clarify", "result": {"answer": question, "needs_clarification": True}}
    return {"intent": decision.intent}


def route_intent(state: RecruitingState) -> str:
    return "audit" if state.get("intent") == "clarify" else str(state["intent"])


def output_checks(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    """Step 9: stop contact details, protected attributes and foreign tenant ids leaving the graph."""
    ctx = ctx_of(runtime)
    result = dict(state.get("result") or {})
    flags: list[dict[str, Any]] = []
    with tenant_scope(ctx.tenant_id):
        foreign = foreign_tenant_ids(" ".join(strings_in(result) + strings_in(state.get("drafts", []))), ctx)
        if foreign:
            from apps.governance.services import report_incident

            report_incident(
                kind="security",
                severity="critical",
                title="Agent output contained another tenant's id",
                description=f"Run {ctx.run_id} produced ids {foreign}; output withheld.",
                run_id=ctx.run_id,
                reported_by_id=ctx.user_id,
            )
            return {
                "result": {"withheld": True, "reason": "Output referenced data outside your tenant."},
                "review": None,
                "flags": [{"guard": "output", "label": "foreign_tenant_id"}],
            }
    if isinstance(result.get("answer"), str):
        redacted, count = redact_contact_details(result["answer"])
        if count:
            result["answer"] = redacted
            flags.append({"guard": "output", "label": "contact_details_redacted", "count": count})
    if state.get("intent") == "candidates":
        mentions = protected_attribute_mentions(" ".join(strings_in(state.get("assessments", []))))
        if mentions:
            flags.append({"guard": "output", "label": "protected_attribute_mention", "terms": mentions})
    return {"result": result, "flags": flags}


def route_after_checks(state: RecruitingState) -> str:
    return "open_review" if state.get("review") else "audit"


def open_review(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    """Create the ApprovalRequest once, before pausing (the node after it may re-run on resume)."""
    review = dict(state["review"] or {})
    agent = AGENT_FOR_INTENT[str(state["intent"])]
    opened = tool_call(
        runtime,
        agent,
        "start_approval",
        kind=review["kind"],
        target_id=review["target_id"],
        review_round=state.get("review_round", 1),
        payload=review.get("payload", {}),
    )
    review["approval_request_id"] = opened["approval_request_id"]
    return {"review": review}


def human_review(state: RecruitingState) -> dict[str, Any]:
    review = state["review"] or {}
    decision = interrupt(
        {
            "type": review["type"],
            "approval_request_id": review["approval_request_id"],
            "kind": review["kind"],
            "target_id": str(review["target_id"]),
            "title": review.get("title", ""),
            "round": state.get("review_round", 1),
        }
    )
    return {"review_decision": decision}


def apply_decision(state: RecruitingState) -> dict[str, Any]:
    """The approval handler already ran the side effect. Here the graph only decides where to go next."""
    decision = state.get("review_decision") or {}
    round_ = state.get("review_round", 1)
    outcome = {
        "review_outcome": decision.get("decision"),
        "approval_request_id": decision.get("approval_request_id"),
        "decided_by": decision.get("decided_by"),
    }
    if decision.get("decision") == "request_changes":
        if round_ >= MAX_REVIEW_ROUNDS:
            return {
                "result": {
                    **(state.get("result") or {}),
                    **outcome,
                    "note": f"Stopped after {MAX_REVIEW_ROUNDS} review rounds; continue manually.",
                }
            }
        return {"feedback": decision.get("reason", ""), "review_round": round_ + 1, "review": None, "drafts": []}
    return {"result": {**(state.get("result") or {}), **outcome}}


def route_after_decision(state: RecruitingState) -> str:
    decision = state.get("review_decision") or {}
    if decision.get("decision") == "request_changes" and state.get("review") is None:
        return str(state["intent"])
    return "audit"


def audit(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    from apps.governance.services import record_audit

    ctx = ctx_of(runtime)
    result = state.get("result") or {}
    with tenant_scope(ctx.tenant_id):
        record_audit(
            ctx,
            action="agent_run.finished",
            target_type="agent_run",
            target_id=ctx.run_id,
            details={
                "intent": state.get("intent"),
                "review_outcome": result.get("review_outcome"),
                "errors": len(state.get("errors", [])),
                "flags": len(state.get("flags", [])),
            },
        )
    return {}
