"""Deterministic policy rules, written as data where possible.

Every decision takes the same input an OPA policy would:

    {"action": "tool:create_email_draft",
     "subject": {"user_id": ..., "tenant_id": ..., "roles": [...]},
     "resource": {...}}

and returns allow/deny with a reason. The LLM never sees or influences these inputs:
subject comes from the server-side ExecutionContext, resource from the database.
"""

import json
import logging
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings

from apps.accounts.roles import Role
from apps.core.context import ExecutionContext

logger = logging.getLogger(__name__)

STAFF = frozenset({Role.HR_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER, Role.INTERVIEWER, Role.FINANCE_APPROVER})
RECRUITING = frozenset({Role.HR_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER})
RECRUITERS = frozenset({Role.HR_ADMIN, Role.RECRUITER})

# Which roles may start each kind of agent run.
RUN_ROLES: dict[str, frozenset[str]] = {
    "requisition_review": RECRUITING,
    "jd_generation": RECRUITERS,
    "sourcing": RECRUITERS,
    "resume_parsing": RECRUITERS,
    "matching": RECRUITERS,
    "communication": RECRUITERS,
    "scheduling": RECRUITERS,
    "feedback_summary": RECRUITING,
    "offer": RECRUITERS,
    "assistant": RECRUITING,
    "analytics": RECRUITING | {Role.AUDITOR},
    "compliance": STAFF,
}

# Which roles may have a tool called on their behalf. The tool registry also
# limits each tool to the agents that need it.
TOOL_ROLES: dict[str, frozenset[str]] = {
    "get_requisition": RECRUITING,
    "get_comp_band": RECRUITING,
    "list_departments": STAFF,
    "get_jd_templates": RECRUITERS,
    "check_inclusive_language": STAFF,
    "create_jd_draft": RECRUITERS,
    "ats_list_applicants": RECRUITERS,
    "search_talent_pool": RECRUITERS,
    "get_document_text": RECRUITERS,
    "save_extraction": RECRUITERS,
    "get_job_requirements": RECRUITERS,
    "get_candidate_evidence": RECRUITERS,
    "search_resume_chunks": RECRUITERS,
    "get_document_span": RECRUITERS,
    "save_assessment": RECRUITERS,
    "search_candidates": RECRUITING,
    "pipeline_stats": RECRUITING | {Role.AUDITOR},
    "search_policy_docs": STAFF,
    "get_template": RECRUITERS,
    "create_email_draft": RECRUITERS,
    "calendar_free_busy": RECRUITERS,
    "propose_interview_slots": RECRUITERS,
    "create_invite_draft": RECRUITERS,
    "get_scorecards": RECRUITING,
    "create_offer_draft": RECRUITERS,
    "start_approval": RECRUITERS,
    "run_report": RECRUITING | {Role.AUDITOR},
    "get_policy_rules": STAFF,
}

# Business rules shown to people and to the Compliance Assistant.
POLICY_RULES: list[dict[str, str]] = [
    {"id": "offer-approvals", "rule": "Offers need HR admin approval, then finance approval, by two other people."},
    {"id": "offer-band", "rule": "An offer's base salary must fall inside the requisition's approved comp band."},
    {"id": "email-recipients", "rule": "Emails go only to candidates who applied to a requisition you can see."},
    {"id": "draft-first", "rule": "Agents create drafts. Nothing is sent or changed until a person approves it."},
    {
        "id": "no-protected-attributes",
        "rule": "Age, gender, marital status, religion, race, caste, disability, "
        "nationality and photos are never used as candidate signals.",
    },
    {"id": "evidence", "rule": "Every match claim cites a resume span. Unsupported claims are dropped."},
    {"id": "decisions", "rule": "Every stage change, rejection and offer is made by a named person with a reason."},
    {"id": "consent", "rule": "Talent-pool search only covers candidates with active talent-pool consent."},
]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


ALLOW = PolicyDecision(True)


def _deny(reason: str) -> PolicyDecision:
    return PolicyDecision(False, reason)


def _subject(ctx: ExecutionContext) -> dict[str, Any]:
    return {"user_id": str(ctx.user_id), "tenant_id": str(ctx.tenant_id), "roles": sorted(ctx.roles)}


def evaluate_local(action: str, subject: Mapping[str, Any], resource: Mapping[str, Any]) -> PolicyDecision:
    roles = frozenset(subject.get("roles", []))
    kind, _, name = action.partition(":")

    if kind == "run":
        allowed = RUN_ROLES.get(name)
        if allowed is None:
            return _deny(f"Unknown agent run kind {name!r}.")
        return ALLOW if roles & allowed else _deny(f"Your roles cannot start a {name} run.")

    if kind == "tool":
        allowed = TOOL_ROLES.get(name)
        if allowed is None:
            return _deny(f"Tool {name!r} is not registered with the policy engine.")
        if not roles & allowed:
            return _deny(f"Your roles cannot use {name}.")
        if name == "create_email_draft" and not resource.get("candidate_on_visible_requisition", False):
            return _deny("Emails go only to candidates on a requisition you can see.")
        if name == "create_offer_draft":
            return _offer_within_band(resource)
        if name == "search_talent_pool" and resource.get("include_unconsented"):
            return _deny("Talent-pool search covers consented candidates only.")
        return ALLOW

    if action == "offer.within_band":
        return _offer_within_band(resource)

    if action == "approval.decide":
        required = frozenset(resource.get("required_roles", []))
        if not roles & required:
            return _deny("Your roles cannot decide this approval.")
        assignee = resource.get("assignee_id")
        if assignee and assignee != subject.get("user_id"):
            return _deny("This approval is assigned to someone else.")
        if resource.get("kind") == "offer" and resource.get("requested_by_id") == subject.get("user_id"):
            return _deny("You cannot approve an offer you requested.")
        if resource.get("kind") == "offer" and subject.get("user_id") in resource.get("previous_approver_ids", []):
            return _deny("Each offer approval step needs a different person.")
        return ALLOW

    return _deny(f"No policy for action {action!r}.")


def _offer_within_band(resource: Mapping[str, Any]) -> PolicyDecision:
    try:
        salary = Decimal(str(resource["base_salary"]))
        low = Decimal(str(resource["band_min"]))
        high = Decimal(str(resource["band_max"]))
    except (KeyError, InvalidOperation):
        return _deny("An offer needs a salary and an approved comp band.")
    if not low <= salary <= high:
        return _deny(f"Base salary {salary} is outside the approved band {low}-{high}.")
    return ALLOW


def _evaluate_opa(action: str, subject: Mapping[str, Any], resource: Mapping[str, Any]) -> PolicyDecision:
    body = json.dumps({"input": {"action": action, "subject": subject, "resource": resource}}, default=str).encode()
    request = urllib.request.Request(  # noqa: S310 - URL comes from settings, not user input
        f"{settings.OPA_URL.rstrip('/')}/v1/data/hr/decision",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            result = json.load(response).get("result") or {}
    except OSError:
        logger.exception("OPA unreachable; denying")
        return _deny("Policy service unavailable.")
    return PolicyDecision(bool(result.get("allow")), str(result.get("reason", "")))


def decide(action: str, ctx: ExecutionContext, resource: Mapping[str, Any] | None = None) -> PolicyDecision:
    """The single entry point. Fails closed when OPA is configured but unreachable."""
    subject = _subject(ctx)
    resource = resource or {}
    if settings.OPA_URL:
        return _evaluate_opa(action, subject, resource)
    return evaluate_local(action, subject, resource)
