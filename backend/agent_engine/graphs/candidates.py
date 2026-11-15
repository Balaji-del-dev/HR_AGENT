"""The candidate pipeline subgraph: gather evidence, fan out one branch per application, save.

    match_prepare -> Send(assess_application) x N -> match_save

Branches run in parallel worker threads, so they only call the model and run
pure validation; every database read and write happens in match_prepare and
match_save on the graph's main thread.
"""

from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_engine.nodes.candidates import assess_application, fan_out, match_prepare, match_save
from agent_engine.state import RecruitingState
from apps.core.context import ExecutionContext


class CandidatePipelineOutput(TypedDict):
    """Only these keys flow back to the parent, so its list reducers do not double-count."""

    context: NotRequired[dict[str, Any]]
    result: NotRequired[dict[str, Any]]
    review: NotRequired[dict[str, Any] | None]
    drafts: NotRequired[list[dict[str, Any]]]


def build_candidate_pipeline() -> CompiledStateGraph:  # type: ignore[type-arg]
    builder = StateGraph(RecruitingState, context_schema=ExecutionContext, output_schema=CandidatePipelineOutput)
    builder.add_node("match_prepare", match_prepare)
    builder.add_node("assess_application", assess_application)
    builder.add_node("match_save", match_save)
    builder.add_edge(START, "match_prepare")
    builder.add_conditional_edges("match_prepare", fan_out, ["assess_application", "match_save"])
    builder.add_edge("assess_application", "match_save")
    builder.add_edge("match_save", END)
    return builder.compile(name="candidate_pipeline")
