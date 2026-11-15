"""Recruiter Assistant, Recruitment Analytics and Compliance Assistant."""

import json
import re
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, PIIMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from agent_engine.bridge import MainThreadBridge
from agent_engine.budget import maybe_current_run
from agent_engine.llm.factory import get_chat_model
from agent_engine.nodes.common import llm_structured, tool_call
from agent_engine.prompts import get_prompt
from agent_engine.schemas import ComplianceFindings, ReportChoice
from agent_engine.state import RecruitingState
from agent_engine.tools import langchain_tools
from apps.core.context import ExecutionContext

ASSISTANT_TOOLS = ["search_candidates", "pipeline_stats", "search_policy_docs"]
# Phone numbers, but never digit runs joined by hyphens to other characters: ids such as
# 2016dbdc-1699-4407-96a7-... contain "1699-4407-96" and must survive redaction intact.
PHONE_PATTERN = r"(?<![\w-])\+?\d[\d\s().-]{7,}\d(?![\w-])"
_CITATION = re.compile(r"\[(candidate|report|policy):[^\]]+\]")


def assistant(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    """An inner tool-calling loop (create_agent) with PII redaction on inputs, tool results and output."""
    ctx = runtime.context
    prompt = get_prompt("recruiter_assistant")
    run = maybe_current_run()
    if run is not None:
        run.record_prompt("recruiter_assistant", prompt.label)
    bridge = MainThreadBridge()
    agent = create_agent(
        get_chat_model(),
        tools=langchain_tools(ctx, agent="assistant", names=ASSISTANT_TOOLS, bridge=bridge),
        system_prompt=prompt.system(),
        middleware=[
            PIIMiddleware(
                "email", strategy="redact", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True
            ),
            PIIMiddleware(
                "phone",
                detector=PHONE_PATTERN,
                strategy="redact",
                apply_to_input=True,
                apply_to_output=True,
                apply_to_tool_results=True,
            ),
            PIIMiddleware("url", strategy="redact", apply_to_tool_results=True),
            ToolCallLimitMiddleware(run_limit=6),  # type: ignore[list-item]
            ModelCallLimitMiddleware(run_limit=8),  # type: ignore[list-item]
        ],
        name="recruiter_assistant",
    )
    history = [
        HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"])
        for m in state["params"].get("history", [])
    ][-10:]
    messages = [*history, HumanMessage(str(state["params"]["message"]))]
    out: dict[str, Any] = bridge.run(lambda: agent.invoke({"messages": messages}, config=config))  # type: ignore[call-overload]
    final = next((m for m in reversed(out["messages"]) if isinstance(m, AIMessage) and m.content), None)
    answer = str(final.content) if final else "I could not find an answer."
    return {"result": {"answer": answer, "citations": sorted({m.group(0) for m in _CITATION.finditer(answer)})}}


def analytics(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    params = state["params"]
    question = str(params.get("question") or params.get("message") or "")
    report_name = params.get("report")
    if not report_name:
        report_name = llm_structured(
            "analytics_route", {"question": question, "reports": _report_menu()}, ReportChoice, config
        ).report
    report = tool_call(
        runtime, "analytics", "run_report", report=report_name, requisition_id=params.get("requisition_id")
    )
    lines = [f"- {row[0]}: {', '.join(str(v) for v in row[1:])}" for row in report["rows"][:12]]
    answer = f"{report['title']} ({', '.join(report['columns'][1:])}):\n" + "\n".join(lines or ["- no data yet"])
    return {"result": {"answer": answer + f"\n[report:{report['name']}]", "report": report}}


def _report_menu() -> dict[str, str]:
    from apps.analytics.reports import REPORTS

    return {name: description for name, (description, _) in REPORTS.items()}


def compliance(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    """Advisory findings. OPA and the services enforce; this agent explains."""
    from apps.candidates.models import CandidateConsent
    from apps.candidates.selectors import get_visible_candidate, has_active_consent
    from apps.core.tenancy import tenant_scope

    ctx = runtime.context
    params = state["params"]
    rules = tool_call(runtime, "compliance", "get_policy_rules")
    text = str(params.get("text", ""))
    findings: list[dict[str, Any]] = []
    if text:
        for flag in tool_call(runtime, "compliance", "check_inclusive_language", text=text):
            findings.append(
                {
                    "category": flag["category"],
                    "excerpt": flag["term"],
                    "explanation": flag["suggestion"],
                    "source": "rules",
                }
            )
        extra = llm_structured(
            "compliance_review",
            {"text": text, "already_flagged": [f["excerpt"] for f in findings]},
            ComplianceFindings,
            config,
        )
        findings += [{**f.model_dump(), "source": "model"} for f in extra.findings if f.excerpt and f.excerpt in text]
    if params.get("candidate_id"):
        with tenant_scope(ctx.tenant_id):
            candidate = get_visible_candidate(ctx, params["candidate_id"])
            for purpose in CandidateConsent.Purpose.values:
                if not has_active_consent(candidate.id, purpose):
                    findings.append(
                        {
                            "category": "consent",
                            "excerpt": purpose,
                            "source": "rules",
                            "explanation": f"No active {purpose} consent: do not process for this purpose.",
                        }
                    )
    return {
        "result": {
            "findings": findings,
            "rules": [r["id"] for r in rules],
            "answer": json.dumps({"findings": len(findings)}),
        }
    }
