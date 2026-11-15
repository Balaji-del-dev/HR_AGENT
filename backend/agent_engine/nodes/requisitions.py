"""Job Requisition Agent and JD Generation Agent."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from agent_engine.nodes.common import llm_structured, tool_call
from agent_engine.schemas import JDDraftOut, RequisitionSuggestions
from agent_engine.state import RecruitingState
from apps.core.context import ExecutionContext


def find_requisition_issues(requisition: dict[str, Any], departments: list[str]) -> list[dict[str, str]]:
    """Missing or inconsistent fields, found by code. The model only phrases the fixes."""
    issues = []
    if len(requisition.get("summary", "").split()) < 8:
        issues.append({"field": "summary", "issue": "The business need is missing or very short."})
    if not requisition.get("level"):
        issues.append({"field": "level", "issue": "No level is set."})
    if not requisition.get("must_have_skills"):
        issues.append({"field": "must_have_skills", "issue": "No must-have skills are listed."})
    elif len(requisition["must_have_skills"]) > 8:
        issues.append({"field": "must_have_skills", "issue": "More than eight must-haves narrows the pool sharply."})
    if requisition.get("comp_band") is None:
        issues.append({"field": "comp_band", "issue": "No approved comp band is linked."})
    elif requisition.get("level") and requisition["comp_band"]["level"] != requisition["level"]:
        issues.append({"field": "comp_band", "issue": "The comp band's level does not match the requisition level."})
    if not requisition.get("location"):
        issues.append({"field": "location", "issue": "No location or remote policy is given."})
    if requisition.get("headcount", 1) > 20:
        issues.append({"field": "headcount", "issue": "Headcount above 20 is unusual for one requisition."})
    if departments and requisition.get("department") not in departments:
        issues.append({"field": "department", "issue": "The department name does not match any existing one."})
    return issues


def requisition_review(
    state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig
) -> dict[str, Any]:
    agent = "requisition_review"
    requisition_id = state["params"]["requisition_id"]
    requisition = tool_call(runtime, agent, "get_requisition", requisition_id=requisition_id)
    departments = tool_call(runtime, agent, "list_departments")
    tool_call(runtime, agent, "get_comp_band", requisition_id=requisition_id)
    issues = find_requisition_issues(requisition, departments)
    suggestions: list[dict[str, str]] = []
    if issues:
        answer = llm_structured(
            "requisition_review", {"requisition": requisition, "issues": issues}, RequisitionSuggestions, config
        )
        known = {issue["field"] for issue in issues}
        suggestions = [s.model_dump() for s in answer.suggestions if s.field in known]
    return {
        "result": {
            "requisition_id": requisition_id,
            "issues": issues,
            "suggestions": suggestions,
            "ready_to_submit": not issues,
        }
    }


def jd_draft(state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig) -> dict[str, Any]:
    """Draft (or redraft after feedback), check the language, and save the draft for review."""
    from agent_engine.prompts import get_prompt

    agent = "jd_generation"
    requisition_id = state["params"]["requisition_id"]
    requisition = tool_call(runtime, agent, "get_requisition", requisition_id=requisition_id)
    templates = tool_call(runtime, agent, "get_jd_templates", department=requisition["department"])
    data = {
        "requisition": requisition,
        "templates": templates,
        "feedback": state.get("feedback", ""),
        "previous_draft": (state.get("context") or {}).get("last_jd"),
    }
    draft = llm_structured("jd_generation", data, JDDraftOut, config)

    # Code, not the model, guarantees every must-have is a mandatory criterion.
    requirements = [r.model_dump() for r in draft.requirements]
    names = {r["name"].lower() for r in requirements}
    for skill in requisition["must_have_skills"]:
        if skill.lower() in names:
            for r in requirements:
                if r["name"].lower() == skill.lower():
                    r["level"] = "mandatory"
        else:
            requirements.insert(0, {"name": skill, "level": "mandatory", "aliases": []})
    for skill in requisition["nice_to_have_skills"]:
        if skill.lower() not in names:
            requirements.append({"name": skill, "level": "preferred", "aliases": []})

    text = "\n".join([draft.title, draft.summary, draft.body, *draft.responsibilities])
    flags = tool_call(runtime, agent, "check_inclusive_language", text=text)
    saved = tool_call(
        runtime,
        agent,
        "create_jd_draft",
        requisition_id=requisition_id,
        title=draft.title,
        summary=draft.summary,
        responsibilities=draft.responsibilities,
        requirements=requirements,
        body=draft.body,
        prompt_version=get_prompt("jd_generation").label,
    )
    review = {
        "type": "review_jd",
        "kind": "job_description",
        "target_id": saved["id"],
        "title": f"Review JD draft v{saved['version']}",
    }
    return {
        "drafts": [{"type": "job_description", "id": saved["id"], "version": saved["version"]}],
        "review": review,
        "context": {"last_jd": draft.model_dump()},
        "result": {"job_description_id": saved["id"], "version": saved["version"], "language_flags": flags},
    }
