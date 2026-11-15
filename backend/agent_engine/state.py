"""Graph state. Identity is not here: it travels as runtime context (ExecutionContext),
which the model never sees and cannot change."""

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages

Intent = Literal[
    "requisition_review",
    "job_jd",
    "sourcing",
    "resume_parsing",
    "candidates",
    "comms",
    "scheduling",
    "feedback",
    "offer",
    "assistant",
    "analytics",
    "compliance",
    "clarify",
]


class RecruitingState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    kind: str  # the AgentRun kind
    params: dict[str, Any]  # the run input, validated by the API
    intent: NotRequired[Intent | None]
    requisition_id: NotRequired[str | None]
    candidate_ids: NotRequired[list[str]]
    context: NotRequired[dict[str, Any]]  # data gathered by tools for the next node
    extractions: Annotated[list[dict[str, Any]], operator.add]
    assessments: Annotated[list[dict[str, Any]], operator.add]  # merged from parallel Send branches
    drafts: NotRequired[list[dict[str, Any]]]  # emails, invites, offers, JDs awaiting approval
    review: NotRequired[dict[str, Any] | None]  # what the human gate should show
    review_round: NotRequired[int]
    review_decision: NotRequired[dict[str, Any] | None]
    feedback: NotRequired[str]  # "request changes" text from the reviewer
    result: NotRequired[dict[str, Any]]
    flags: Annotated[list[dict[str, Any]], operator.add]  # guard findings
    errors: Annotated[list[str], operator.add]
    assess_task: NotRequired[dict[str, Any]]  # payload of one Send branch


def initial_state(*, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [],
        "kind": kind,
        "params": params,
        "requisition_id": params.get("requisition_id"),
        "extractions": [],
        "assessments": [],
        "flags": [],
        "errors": [],
        "review_round": 1,
    }
