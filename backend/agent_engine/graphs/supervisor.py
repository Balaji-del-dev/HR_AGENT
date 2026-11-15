"""The parent graph: guard, route, run one agent subgraph, check output, and pause for a person.

    START -> guard_input -> supervisor -> <agent> -> output_checks
          -> (draft to review?) open_review -> human_review [interrupt] -> apply_decision
          -> (changes requested?) back to <agent>  |  audit -> END

Read-only answers go straight from output_checks to audit. Anything with a
side effect stops at human_review until the named person decides.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, RetryPolicy

from agent_engine.graphs.candidates import build_candidate_pipeline
from agent_engine.nodes import common
from agent_engine.nodes.candidates import resume_parsing, sourcing
from agent_engine.nodes.insight import analytics, assistant, compliance
from agent_engine.nodes.requisitions import jd_draft, requisition_review
from agent_engine.nodes.workflow import comms, feedback, offer, scheduling
from agent_engine.state import RecruitingState
from apps.core.context import ExecutionContext

AGENT_NODES = {
    "requisition_review": requisition_review,
    "job_jd": jd_draft,
    "sourcing": sourcing,
    "resume_parsing": resume_parsing,
    "comms": comms,
    "scheduling": scheduling,
    "feedback": feedback,
    "offer": offer,
    "assistant": assistant,
    "analytics": analytics,
    "compliance": compliance,
}
INTENTS = [*AGENT_NODES, "candidates"]


def build_supervisor_graph(checkpointer: Checkpointer = None) -> CompiledStateGraph:  # type: ignore[type-arg]
    builder = StateGraph(RecruitingState, context_schema=ExecutionContext)
    builder.add_node("guard_input", common.guard_input)
    builder.add_node("supervisor", common.supervisor)
    for name, node in AGENT_NODES.items():
        builder.add_node(name, node)
    builder.add_node("candidates", build_candidate_pipeline())
    builder.add_node("output_checks", common.output_checks)
    builder.add_node("open_review", common.open_review, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("human_review", common.human_review)
    builder.add_node("apply_decision", common.apply_decision)
    builder.add_node("audit", common.audit)

    builder.add_edge(START, "guard_input")
    builder.add_edge("guard_input", "supervisor")
    builder.add_conditional_edges("supervisor", common.route_intent, [*INTENTS, "audit"])
    for name in INTENTS:
        builder.add_edge(name, "output_checks")
    builder.add_conditional_edges("output_checks", common.route_after_checks, ["open_review", "audit"])
    builder.add_edge("open_review", "human_review")
    builder.add_edge("human_review", "apply_decision")
    builder.add_conditional_edges("apply_decision", common.route_after_decision, [*INTENTS, "audit"])
    builder.add_edge("audit", END)
    return builder.compile(checkpointer=checkpointer, name="supervisor")
