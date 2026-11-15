from uuid import uuid4

import pytest

from apps.core.context import ExecutionContext
from policies.engine import TOOL_ROLES, decide, evaluate_local


def ctx(*roles: str) -> ExecutionContext:
    return ExecutionContext(user_id=uuid4(), tenant_id=uuid4(), roles=frozenset(roles))


@pytest.mark.parametrize(
    ("roles", "kind", "allowed"),
    [
        (("recruiter",), "matching", True),
        (("interviewer",), "matching", False),
        (("hiring_manager",), "jd_generation", False),
        (("auditor",), "analytics", True),
        (("finance_approver",), "offer", False),
        (("recruiter",), "made_up_kind", False),
    ],
)
def test_run_permissions(roles, kind, allowed) -> None:
    assert decide(f"run:{kind}", ctx(*roles)).allowed is allowed


def test_every_tool_has_roles_and_unknown_tools_are_denied() -> None:
    assert all(TOOL_ROLES.values())
    assert not decide("tool:drop_database", ctx("hr_admin")).allowed


def test_email_only_to_candidates_on_visible_requisitions() -> None:
    assert not decide("tool:create_email_draft", ctx("recruiter"), {"candidate_on_visible_requisition": False}).allowed
    assert decide("tool:create_email_draft", ctx("recruiter"), {"candidate_on_visible_requisition": True}).allowed


@pytest.mark.parametrize(
    ("salary", "allowed"), [(1_999_999, False), (2_000_000, True), (3_000_000, True), (3_000_001, False)]
)
def test_offer_must_be_inside_the_band(salary, allowed) -> None:
    resource = {"base_salary": salary, "band_min": 2_000_000, "band_max": 3_000_000}
    assert decide("offer.within_band", ctx("recruiter"), resource).allowed is allowed


def test_approval_rules() -> None:
    me = ctx("hr_admin")
    base = {"kind": "offer", "required_roles": ["hr_admin"], "assignee_id": None, "requested_by_id": str(uuid4())}
    assert decide("approval.decide", me, base).allowed
    assert not decide("approval.decide", me, {**base, "requested_by_id": str(me.user_id)}).allowed
    assert not decide("approval.decide", me, {**base, "previous_approver_ids": [str(me.user_id)]}).allowed
    assert not decide("approval.decide", me, {**base, "assignee_id": str(uuid4())}).allowed
    assert not decide("approval.decide", ctx("recruiter"), base).allowed


def test_unknown_actions_fail_closed() -> None:
    assert not evaluate_local("delete:everything", {"roles": ["hr_admin"]}, {}).allowed


def test_opa_unreachable_fails_closed(settings) -> None:
    settings.OPA_URL = "http://127.0.0.1:9"  # nothing listens here
    assert not decide("run:matching", ctx("recruiter")).allowed
