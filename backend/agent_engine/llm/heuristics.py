"""Deterministic stand-ins for each structured LLM call (LLM_PROVIDER=offline).

They read only what a real model would see: the masked data block in the
prompt. They make the whole platform usable, and its tests repeatable, on a
machine with no model. Quality is basic by design; real deployments use
Claude or a local model.
"""

import json
import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from document_ai.vocabulary import TECH_TERMS

_DATA = re.compile(r"<data>\s*(\{.*\})\s*</data>", re.DOTALL)


def data_of(messages: list[BaseMessage]) -> dict[str, Any]:
    for message in reversed(messages):
        match = _DATA.search(str(message.content))
        if match:
            data: dict[str, Any] = json.loads(match.group(1))
            return data
    return {}


def respond(name: str, messages: list[BaseMessage], tools: list[dict[str, Any]]) -> Any:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"No offline heuristic for {name}")
    if name == "chat":
        return handler(messages, tools)
    return handler(data_of(messages))


ANALYTICS_WORDS = re.compile(
    r"\b(how many|funnel|pipeline|time in stage|source|sources|override|report|metrics?|stats|statistics|count)\b",
    re.IGNORECASE,
)


def route(data: dict[str, Any]) -> dict[str, Any]:
    message = data.get("message", "")
    if len(message.split()) < 2:
        return {"intent": "unclear", "clarifying_question": "Could you say a bit more about what you need?"}
    return {"intent": "analytics" if ANALYTICS_WORDS.search(message) else "assistant", "clarifying_question": ""}


def requisition_suggestions(data: dict[str, Any]) -> dict[str, Any]:
    advice = {
        "summary": "Add two or three sentences on why the role exists and what success looks like in a year.",
        "level": "Set the level so the comp band and interview loop can be chosen.",
        "must_have_skills": "List the few skills a person cannot do the job without; keep the rest as nice-to-have.",
        "comp_band": "Pick the approved comp band for this department and level before submitting.",
        "location": "Say where the person will work, or that the role is remote.",
        "headcount": "Check the headcount; large numbers usually need several requisitions.",
        "department": "Use one of the tenant's existing department names.",
    }
    return {
        "suggestions": [
            {
                "field": issue["field"],
                "issue": issue["issue"],
                "suggestion": advice.get(issue["field"], "Review this field."),
            }
            for issue in data.get("issues", [])
        ]
    }


def jd_draft(data: dict[str, Any]) -> dict[str, Any]:
    req = data.get("requisition", {})
    title = req.get("title", "Role")
    must = req.get("must_have_skills", []) or ["Relevant experience"]
    nice = req.get("nice_to_have_skills", [])
    summary = req.get("summary") or f"Join the {req.get('department', '')} team as a {title}."
    responsibilities = [f"Design, build and maintain systems using {skill}." for skill in must[:3]]
    responsibilities += [
        "Work with product, design and other engineers to ship reliable features.",
        "Review code, share knowledge and improve how the team works.",
    ]
    requirements = [{"name": s, "level": "mandatory", "aliases": []} for s in must]
    requirements += [{"name": s, "level": "preferred", "aliases": []} for s in nice]
    lines = [
        f"# {title}",
        "",
        f"**Department:** {req.get('department', '')}  ",
        f"**Location:** {req.get('location') or 'To be confirmed'}  ",
        f"**Level:** {req.get('level') or '-'}",
        "",
        "## About the role",
        summary,
        "",
        "## What you will do",
        *[f"- {r}" for r in responsibilities],
        "",
        "## What you need",
        *[f"- {s}" for s in must],
    ]
    if nice:
        lines += ["", "## Nice to have", *[f"- {s}" for s in nice]]
    lines += [
        "",
        "## How we hire",
        "Every application is reviewed by a person against the criteria above. "
        "We welcome applicants of every background and will provide accommodations on request.",
    ]
    if data.get("feedback"):
        lines += ["", f"_Revised after reviewer feedback: {data['feedback']}_"]
    return {
        "title": title,
        "summary": summary,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "body": "\n".join(lines),
    }


_DEGREE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\.?|b\.?\s?sc|bachelor'?s?|m\.?\s?tech|m\.?\s?s\.?|m\.?\s?sc|master'?s?|"
    r"mba|ph\.?\s?d|diploma)\b",
    re.IGNORECASE,
)
_YEARS = re.compile(r"\b((?:19|20)\d{2})(?:\s*[-\u2013to]+\s*((?:19|20)\d{2}|present|current|now))?", re.IGNORECASE)


def _ev(span: dict[str, Any], quote: str | None = None) -> list[dict[str, str]]:
    return [{"span_id": span["id"], "quote": quote if quote is not None else span["text"]}]


def resume_extraction(data: dict[str, Any]) -> dict[str, Any]:
    spans = data.get("spans", [])
    skills: dict[str, dict[str, Any]] = {}
    experience, education, certifications = [], [], []
    sections = {span.get("section") for span in spans}
    for span in spans:
        text, section = span["text"], span.get("section", "")
        if section == "heading":
            continue
        for token in re.split(r"[,;|/•·]+|\s+-\s+|\s+and\s+", text):
            clean = token.strip(" .:()[]")
            if clean.lower() in TECH_TERMS and clean.lower() not in skills:
                start = text.find(clean)
                skills[clean.lower()] = {
                    "name": clean,
                    "years": None,
                    "evidence": _ev(span, text[start : start + len(clean)]),
                    "confidence": 0.9 if section == "skills" else 0.7,
                }
        if section == "experience" and _YEARS.search(text):
            years = _YEARS.search(text)
            assert years is not None
            head = text[: years.start()].strip(" ,-\u2013|()")
            title, _, org = head.partition(",") if "," in head else head.partition(" at ")
            end = years.group(2) or ""
            experience.append(
                {
                    "title": title.strip() or head,
                    "organization": org.strip(),
                    "start": years.group(1),
                    "end": "" if end.lower() in ("present", "current", "now") else end,
                    "summary": "",
                    "evidence": _ev(span),
                    "confidence": 0.75,
                }
            )
        elif section == "education" and _DEGREE.search(text):
            year = _YEARS.search(text)
            degree, _, institution = text.partition(",")
            education.append(
                {
                    "degree": degree.strip(),
                    "institution": institution.strip(" ,"),
                    "field_of_study": "",
                    "year": year.group(1) if year else "",
                    "evidence": _ev(span),
                    "confidence": 0.8,
                }
            )
        elif section == "certifications":
            year = _YEARS.search(text)
            certifications.append(
                {
                    "name": text.split(",")[0].strip(),
                    "issuer": "",
                    "year": year.group(1) if year else "",
                    "evidence": _ev(span),
                    "confidence": 0.7,
                }
            )
    missing = [s for s in ("experience", "education", "skills") if s not in sections]
    return {
        "skills": list(skills.values()),
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "missing_sections": missing,
    }


def criterion_assessment(data: dict[str, Any]) -> dict[str, Any]:
    criterion = data.get("criterion", {})
    terms = [criterion.get("name", ""), *criterion.get("aliases", [])]
    for item in data.get("evidence", []):
        text = item.get("text", "")
        for term in terms:
            if term and re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE):
                return {
                    "status": "documented",
                    "evidence": [{"span_id": item["span_id"], "quote": text}],
                    "question": "",
                }
    return {
        "status": "not_documented",
        "evidence": [],
        "question": f"Ask the candidate about their experience with {criterion.get('name', 'this requirement')}.",
    }


def email_draft(data: dict[str, Any]) -> dict[str, Any]:
    template = data.get("template") or {}
    if template.get("body"):
        return {"subject": template.get("subject", ""), "body": template["body"]}
    kind = data.get("kind", "update")
    subjects = {
        "outreach": "An opportunity at {{ company_name }}: {{ job_title }}",
        "update": "Your application for {{ job_title }}",
        "decline": "Your application for {{ job_title }}",
        "invite": "Interview for {{ job_title }}",
        "offer": "Your offer for {{ job_title }}",
    }
    bodies = {
        "outreach": "Hi {{ candidate_first_name }},\n\nWe think your background could be a strong fit for our "
        "{{ job_title }} role. Would you be open to a short conversation?\n\nBest,\n{{ recruiter_name }}",
        "update": "Hi {{ candidate_first_name }},\n\nThank you for your patience. Your application for "
        "{{ job_title }} has moved forward, and we will be in touch about next steps soon.\n\n"
        "Best,\n{{ recruiter_name }}",
        "decline": "Hi {{ candidate_first_name }},\n\nThank you for your interest in the {{ job_title }} role and "
        "for the time you spent with us. We have decided not to move forward with your application. "
        "We wish you the very best.\n\nKind regards,\n{{ recruiter_name }}",
        "invite": "Hi {{ candidate_first_name }},\n\nWe would like to invite you to interview for {{ job_title }} "
        "on {{ slot_time }}. Please reply to confirm.\n\nBest,\n{{ recruiter_name }}",
        "offer": "Hi {{ candidate_first_name }},\n\nWe are delighted to share an offer for {{ job_title }}. "
        "The details are attached.\n\nBest,\n{{ recruiter_name }}",
    }
    return {"subject": subjects.get(kind, subjects["update"]), "body": bodies.get(kind, bodies["update"])}


def feedback_summary(data: dict[str, Any]) -> dict[str, Any]:
    cards = data.get("scorecards", [])
    points = []
    for card in cards:
        if card.get("strengths"):
            points.append({"scorecard_ref": card["ref"], "point": f"Strengths: {card['strengths']}"})
        if card.get("concerns"):
            points.append({"scorecard_ref": card["ref"], "point": f"Concerns: {card['concerns']}"})
    recs = [card.get("recommendation", "") for card in cards]
    positive = sum(r in ("yes", "strong_yes") for r in recs)
    negative = sum(r in ("no", "strong_no") for r in recs)
    disagreements = []
    if positive and negative:
        disagreements.append(f"{positive} interviewer(s) recommend hiring and {negative} do not.")
    return {
        "summary": f"{len(cards)} scorecard(s): {positive} in favour, {negative} against.",
        "points": points,
        "disagreements": disagreements,
    }


def offer_proposal(data: dict[str, Any]) -> dict[str, Any]:
    band = data.get("band", {})
    low, high = float(band.get("min", 0)), float(band.get("max", 0))
    salary = round((low + high) / 2, -3) if high else low
    return {
        "base_salary": salary,
        "bonus_percent": 10.0,
        "rationale": "Midpoint of the approved band; adjust with the hiring manager's input on scope and experience.",
    }


def report_choice(data: dict[str, Any]) -> dict[str, Any]:
    question = data.get("question", "").lower()
    for words, report in (
        (("time", "how long", "days", "hours"), "time_in_stage"),
        (("source", "where"), "source_breakdown"),
        (("override", "against"), "override_rate"),
        (("requisition", "open roles", "status"), "requisition_status"),
        (("agent", "run", "denied", "token"), "agent_health"),
    ):
        if any(word in question for word in words):
            return {"report": report}
    return {"report": "pipeline_funnel"}


def compliance_findings(data: dict[str, Any]) -> dict[str, Any]:
    return {"findings": []}  # the deterministic checks already cover the offline case


def chat(messages: list[BaseMessage], tools: list[dict[str, Any]]) -> AIMessage:
    """A two-step tool loop for the Recruiter Assistant."""
    tool_names = {tool["function"]["name"] for tool in tools}
    last = messages[-1]
    if isinstance(last, ToolMessage):
        return AIMessage(content=_answer_from_tool(str(last.content)))
    question = str(last.content) if isinstance(last, HumanMessage) else ""
    lowered = question.lower()
    if "pipeline_stats" in tool_names and ANALYTICS_WORDS.search(lowered):
        call = {"name": "pipeline_stats", "args": {}}
    elif "search_policy_docs" in tool_names and re.search(
        r"\b(policy|policies|rule|allowed|consent|gdpr|dpdp)\b", lowered
    ):
        call = {"name": "search_policy_docs", "args": {"query": question}}
    elif "search_candidates" in tool_names:
        words = [w for w in re.findall(r"[A-Za-z+#.]+", question) if w.lower() in TECH_TERMS]
        call = {"name": "search_candidates", "args": {"query": " ".join(words) or question}}
    else:
        return AIMessage(
            content="I can search candidates, pipeline numbers and hiring policies. What would you like to know?"
        )
    return AIMessage(content="", tool_calls=[{"id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call", **call}])


def _answer_from_tool(content: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(data, dict) and "candidates" in data:
        found = data["candidates"]
        if not found:
            return "I found no matching candidates you can see."
        lines = [
            f"- {c['label']} [candidate:{c['id']}] — {', '.join(c.get('matched', [])) or 'profile match'}"
            for c in found
        ]
        return "Candidates you can see that match:\n" + "\n".join(lines)
    if isinstance(data, dict) and "rows" in data:
        lines = [f"- {row[0]}: {row[1]}" for row in data["rows"]]
        return f"{data.get('title', 'Pipeline')}:\n" + "\n".join(lines) + "\n[report:pipeline_funnel]"
    if isinstance(data, dict) and "rules" in data:
        lines = [f"- {rule['rule']} [policy:{rule['id']}]" for rule in data["rules"]]
        return "Relevant policies:\n" + "\n".join(lines)
    return content


_HANDLERS: dict[str, Any] = {
    "RouteDecision": route,
    "RequisitionSuggestions": requisition_suggestions,
    "JDDraftOut": jd_draft,
    "ResumeExtraction": resume_extraction,
    "CriterionAssessment": criterion_assessment,
    "EmailDraftOut": email_draft,
    "FeedbackSummary": feedback_summary,
    "OfferProposal": offer_proposal,
    "ReportChoice": report_choice,
    "ComplianceFindings": compliance_findings,
    "chat": chat,
}
