"""Candidate Sourcing, Resume Parsing, Candidate Matching and Candidate Validation Agents."""

import re
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Send

from agent_engine.nodes.common import current_model_label, llm_structured, tool_call
from agent_engine.schemas import CriterionAssessment, ResumeExtraction
from agent_engine.state import RecruitingState
from apps.core.context import ExecutionContext
from document_ai.segmentation import parse_span_id

# ---------------------------------------------------------------- sourcing


def sourcing(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    agent = "sourcing"
    requisition_id = state["params"]["requisition_id"]
    applicants = tool_call(runtime, agent, "ats_list_applicants", requisition_id=requisition_id)
    pool = tool_call(
        runtime, agent, "search_talent_pool", requisition_id=requisition_id, k=int(state["params"].get("k", 10))
    )
    return {"result": {"requisition_id": requisition_id, "applicants": applicants, "talent_pool": pool}}


# ---------------------------------------------------------------- resume parsing


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def validate_evidence(
    evidence: list[dict[str, str]], spans: dict[str, str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Keep citations whose span exists and whose quote is exactly in that span's text."""
    valid, rejected = [], []
    for item in evidence:
        span_id, quote = item.get("span_id", ""), item.get("quote", "")
        text = spans.get(span_id)
        if text is None or parse_span_id(span_id) is None:
            rejected.append({**item, "reason": "span does not exist"})
        elif not quote.strip() or _norm(quote) not in _norm(text):
            rejected.append({**item, "reason": "quote is not in the span"})
        else:
            valid.append({"span_id": span_id, "quote": quote})
    return valid, rejected


_DATE = re.compile(r"^(19|20)\d{2}(-(0[1-9]|1[0-2]))?$")


def check_extraction(extraction: ResumeExtraction, spans: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Step 9: schema is already valid; now check citations and date logic. Bad facts are dropped or flagged."""
    notes: list[str] = []
    out: dict[str, Any] = {
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "missing_sections": [s for s in extraction.missing_sections if s in ("experience", "education", "skills")],
    }
    for key in ("skills", "experience", "education", "certifications"):
        seen: set[str] = set()
        for item in getattr(extraction, key):
            data = item.model_dump()
            valid, rejected = validate_evidence(data["evidence"], spans)
            label = data.get("name") or data.get("title") or data.get("degree") or "?"
            if rejected:
                notes.append(f"{key}: dropped {len(rejected)} citation(s) for {label!r}")
            if not valid:
                continue
            data["evidence"] = valid
            if key == "skills":
                if label.lower() in seen:
                    continue
                seen.add(label.lower())
                if data.get("years") is not None and not 0 <= data["years"] <= 50:
                    data["years"], data["confidence"] = None, min(data["confidence"], 0.5)
            if key == "experience":
                start, end = data.get("start", ""), data.get("end", "")
                for field in ("start", "end"):
                    if data.get(field) and not _DATE.match(data[field]):
                        data[field], data["confidence"] = "", min(data["confidence"], 0.5)
                if start and end and _DATE.match(start) and _DATE.match(end) and end < start:
                    data["needs_review"], data["confidence"] = True, min(data["confidence"], 0.4)
                    notes.append(f"experience: end before start for {label!r}")
            out[key].append(data)
    return out, notes


def resume_parsing(
    state: RecruitingState, runtime: Runtime[ExecutionContext], config: RunnableConfig
) -> dict[str, Any]:
    agent = "resume_parsing"
    document = tool_call(runtime, agent, "get_document_text", document_id=state["params"]["document_id"])
    spans = {span["id"]: span["text"] for span in document["spans"]}
    extraction = llm_structured("resume_parsing", {"spans": document["spans"]}, ResumeExtraction, config)
    checked, notes = check_extraction(extraction, spans)
    saved = tool_call(
        runtime,
        agent,
        "save_extraction",
        candidate_id=document["candidate_id"],
        document_id=document["document_id"],
        extraction=checked,
    )
    low_confidence = sum(
        1
        for key in ("skills", "experience", "education", "certifications")
        for item in checked[key]
        if item["confidence"] < 0.6 or item.get("needs_review")
    )
    return {
        "extractions": [
            {
                "document_id": document["document_id"],
                "counts": {k: len(checked[k]) for k in ("skills", "experience", "education", "certifications")},
            }
        ],
        "result": {
            **saved,
            "document_id": document["document_id"],
            "validation_notes": notes,
            "needs_review": low_confidence,
            "injection_suspected": document["injection_suspected"],
        },
    }


# ---------------------------------------------------------------- matching (fan-out) and validation


def match_prepare(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    """Main thread: gather requirements and evidence with tools. Branches then only call the model."""
    from apps.applications.selectors import applications_for_requisition
    from apps.applications.services import OPEN_STAGES
    from apps.candidates.models import CandidateConsent
    from apps.candidates.selectors import has_active_consent
    from apps.core.tenancy import tenant_scope

    agent = "matching"
    ctx = runtime.context
    requisition_id = state["params"]["requisition_id"]
    requirements = tool_call(runtime, agent, "get_job_requirements", requisition_id=requisition_id)
    wanted = set(state["params"].get("application_ids") or [])
    with tenant_scope(ctx.tenant_id):
        applications = [
            (str(a.id), str(a.candidate_id))
            for a in applications_for_requisition(ctx, requisition_id).filter(stage__in=OPEN_STAGES)
            if (not wanted or str(a.id) in wanted)
            and has_active_consent(a.candidate_id, CandidateConsent.Purpose.APPLICATION)
        ]
    tasks, skipped = [], []
    for application_id, candidate_id in applications:
        evidence = tool_call(runtime, agent, "get_candidate_evidence", candidate_id=candidate_id)
        if not evidence["spans"]:
            skipped.append({"application_id": application_id, "reason": "no processed resume"})
            continue
        criteria = []
        for requirement in requirements["requirements"]:
            hits = tool_call(
                runtime,
                agent,
                "search_resume_chunks",
                candidate_id=candidate_id,
                query=requirement["name"],
                terms=requirement["aliases"],
                k=3,
            )
            lines = [line for hit in hits for line in hit["lines"]][:12]
            criteria.append({"requirement": requirement, "evidence": lines})
        tasks.append(
            {
                "application_id": application_id,
                "candidate_id": candidate_id,
                "criteria": criteria,
                "spans": evidence["spans"],
            }
        )
    return {
        "context": {"match_tasks": tasks, "skipped": skipped, "job_description_id": requirements["job_description_id"]}
    }


def fan_out(state: RecruitingState) -> list[Send] | str:
    tasks = (state.get("context") or {}).get("match_tasks", [])
    if not tasks:
        return "match_save"
    return [Send("assess_application", {"assess_task": task}) for task in tasks]


def assess_application(state: RecruitingState, config: RunnableConfig) -> dict[str, Any]:
    """One branch per application. LLM calls and pure validation only: no ORM on worker threads."""
    task = state["assess_task"]
    results = []
    for item in task["criteria"]:
        requirement = item["requirement"]
        data = {
            "criterion": {
                "name": requirement["name"],
                "level": requirement["level"],
                "aliases": requirement["aliases"],
            },
            "evidence": item["evidence"],
        }
        try:
            answer = llm_structured("candidate_matching", data, CriterionAssessment, config)
            model_status, evidence, question = answer.status, [e.model_dump() for e in answer.evidence], answer.question
        except Exception as exc:  # noqa: BLE001 - one bad answer must not sink the whole matrix
            model_status, evidence, question = "unclear", [], f"Could not assess automatically ({type(exc).__name__})."
        results.append(validate_criterion(requirement, model_status, evidence, question, task["spans"]))
    return {
        "assessments": [
            {"application_id": task["application_id"], "candidate_id": task["candidate_id"], "criteria": results}
        ]
    }


def _supports(quote: str, requirement: dict[str, Any]) -> bool:
    terms = [requirement["name"], *requirement.get("aliases", [])]
    return any(re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", quote.lower()) for t in terms if t)


def validate_criterion(
    requirement: dict[str, Any], model_status: str, evidence: list[dict[str, str]], question: str, spans: dict[str, str]
) -> dict[str, Any]:
    """The Candidate Validation Agent: every quote must exist at its span (exact match) and
    mention the criterion. Unsupported 'documented' claims become 'not documented' and are logged."""
    valid, rejected = validate_evidence(evidence, spans)
    supporting = [e for e in valid if _supports(e["quote"], requirement)]
    rejected += [{**e, "reason": "quote does not mention the criterion"} for e in valid if e not in supporting]
    status, note = model_status, ""
    if model_status == "documented" and not supporting:
        status = "not_documented"
        note = "The model's evidence did not hold up, so the claim was dropped."
    elif model_status == "unclear" and not valid:
        note = "No usable evidence was cited."
    if status != "documented" and not question:
        question = f"Ask the candidate about their experience with {requirement['name']}."
    return {
        "requirement_id": requirement["id"],
        "criterion": requirement["name"],
        "level": requirement["level"],
        "model_status": model_status,
        "status": status,
        "evidence": supporting if status == "documented" else valid,
        "rejected_evidence": rejected,
        "validation_note": note,
        "question": question if status != "documented" else "",
    }


def match_save(state: RecruitingState, runtime: Runtime[ExecutionContext]) -> dict[str, Any]:
    from agent_engine.prompts import get_prompt

    agent = "matching"
    saved = []
    done = {a["application_id"] for a in state.get("assessments", [])}
    for assessment in state.get("assessments", []):
        saved.append(
            tool_call(
                runtime,
                agent,
                "save_assessment",
                application_id=assessment["application_id"],
                criteria=assessment["criteria"],
                prompt_version=get_prompt("candidate_matching").label,
                model_name=current_model_label(),
            )
        )
    context = state.get("context") or {}
    result = {
        "requisition_id": state["params"]["requisition_id"],
        "assessments": saved,
        "skipped": context.get("skipped", []),
        "assessed": len(done),
    }
    if not saved:
        return {"result": result}
    review = {
        "type": "review_shortlist",
        "kind": "shortlist_review",
        "target_id": state["params"]["requisition_id"],
        "title": f"Review {len(saved)} criteria matrices",
        "payload": {
            "requisition_id": state["params"]["requisition_id"],
            "assessments": [
                {"application_id": s["application_id"], "assessment_id": s["assessment_id"], "summary": s["summary"]}
                for s in saved
            ],
        },
    }
    return {"result": result, "review": review, "drafts": [{"type": "assessment", **s} for s in saved]}
