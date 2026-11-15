"""End-to-end agent workflows on the offline model: run, pause at the human gate, decide, resume."""

from uuid import UUID

import pytest
from django.core import mail

from agent_engine.llm import fake
from agent_engine.runtime import StaleResume, enqueue_resume, start_run
from apps.agents.models import AgentRun, ToolCall
from apps.applications.models import JobApplication
from apps.approvals.models import ApprovalRequest
from apps.candidates.models import CandidateSkill
from apps.communications.models import EmailDraft, EmailMessage
from apps.core.tenancy import tenant_scope
from apps.core.tests.scenario import (
    add_candidate,
    approved_requisition,
    ctx_for,
    decide_and_resume,
    run_queued,
    staff,
)
from apps.documents.models import DocumentSpan
from apps.jobs.models import JobDescription, JobRequirement
from apps.matching.models import CriterionResult, MatchingAssessment, RecruiterDecision

pytestmark = pytest.mark.django_db


@pytest.fixture
def acme(tenant_a, make_member):
    people = staff(tenant_a, make_member)
    requisition = approved_requisition(tenant_a, people)
    return {"tenant": tenant_a, "people": people, "requisition": requisition}


def _run(tenant, run_id) -> AgentRun:
    with tenant_scope(tenant.id):
        return AgentRun.objects.get(pk=run_id)


def test_resume_pipeline_masks_identity_and_parsing_cites_spans(acme) -> None:
    tenant, people = acme["tenant"], acme["people"]
    candidate, _, document = add_candidate(
        tenant, people, acme["requisition"], name="Priya Raman", email="priya@example.com"
    )
    assert document.status == "processed"
    with tenant_scope(tenant.id):
        spans = list(DocumentSpan.objects.filter(document=document))
        masked = " ".join(s.text_masked for s in spans)
        assert "Priya" not in masked and "priya@example.com" not in masked and "98765" not in masked
        assert "[NAME]" in masked and "[EMAIL]" in masked
        run = AgentRun.objects.get(kind="resume_parsing")
    assert run_queued(tenant) == ["completed"]
    with tenant_scope(tenant.id):
        skills = {s.name: s for s in CandidateSkill.objects.filter(candidate=candidate)}
        span_text = {s.span_id: s.text_masked for s in spans}
    assert {"Python", "FastAPI", "LangGraph"} <= set(skills)
    for skill in skills.values():
        for evidence in skill.evidence:
            assert evidence["quote"].lower() in span_text[evidence["span_id"]].lower()
    run = _run(tenant, run.id)
    assert run.prompt_versions.get("resume_parsing", "").startswith("resume_parsing@")
    assert run.tool_call_count >= 2


def test_jd_generation_pauses_for_review_then_approval_builds_requirements(acme) -> None:
    tenant, people = acme["tenant"], acme["people"]
    with tenant_scope(tenant.id):
        from apps.requisitions.services import create_requisition

        requisition = create_requisition(
            ctx_for(people["recruiter"], tenant),
            title="Data Engineer",
            department="Engineering",
            summary="Build the data platform that feeds recruiting analytics.",
            must_have_skills=["Python", "SQL"],
            hiring_manager_id=people["manager"].pk,
        )
        run = start_run(
            ctx_for(people["recruiter"], tenant), kind="jd_generation", params={"requisition_id": requisition.id}
        )
    assert run_queued(tenant) == ["awaiting_review"]
    run = _run(tenant, run.id)
    assert run.pending_interrupt["type"] == "review_jd"
    request_id = UUID(run.pending_interrupt["approval_request_id"])

    # The reviewer asks for changes; the graph redrafts and pauses again (round 2).
    assert (
        decide_and_resume(
            tenant, people["recruiter"], request_id, "request_changes", reason="Mention the on-call rota."
        )
        == "awaiting_review"
    )
    run = _run(tenant, run.id)
    assert run.pending_interrupt["round"] == 2
    second = UUID(run.pending_interrupt["approval_request_id"])
    assert second != request_id

    assert (
        decide_and_resume(tenant, people["recruiter"], second, "approve", edits={"summary": "Edited by a person."})
        == "completed"
    )
    with tenant_scope(tenant.id):
        jds = list(JobDescription.objects.filter(requisition=requisition).order_by("version"))
        assert [jd.status for jd in jds] == ["rejected", "approved"]
        assert jds[1].summary == "Edited by a person."
        requirements = {r.name: r.level for r in JobRequirement.objects.filter(job_description=jds[1])}
    assert requirements["Python"] == "mandatory" and requirements["SQL"] == "mandatory"
    assert _run(tenant, run.id).output["result"]["review_outcome"] == "approve"


def test_stale_resume_is_refused(acme) -> None:
    tenant, people = acme["tenant"], acme["people"]
    with tenant_scope(tenant.id):
        run = start_run(
            ctx_for(people["recruiter"], tenant),
            kind="jd_generation",
            params={"requisition_id": acme["requisition"].id},
        )
    run_queued(tenant)
    with tenant_scope(tenant.id), pytest.raises(StaleResume):
        enqueue_resume(
            ctx_for(people["recruiter"], tenant),
            run_id=run.id,
            decision={"approval_request_id": "00000000-0000-0000-0000-000000000000", "decision": "approve"},
        )


def test_matching_fans_out_validates_evidence_and_records_human_decisions(acme) -> None:
    tenant, people, requisition = acme["tenant"], acme["people"], acme["requisition"]
    _, app_a, _ = add_candidate(tenant, people, requisition, name="Asha Kumar", email="asha@example.com")
    _, app_b, _ = add_candidate(tenant, people, requisition, name="Ben Ortiz", email="ben@example.com", pdf=None)
    run_queued(tenant)  # the two resume-parsing runs

    def hallucinate_for_langgraph(messages):
        from agent_engine.llm.heuristics import criterion_assessment, data_of

        data = data_of(messages)
        if data["criterion"]["name"] == "LangGraph":
            return {
                "status": "documented",
                "evidence": [{"span_id": "doc_deadbeef:p1:0-10", "quote": "LangGraph"}],
                "question": "",
            }
        return criterion_assessment(data)

    fake.script("CriterionAssessment", hallucinate_for_langgraph)
    with tenant_scope(tenant.id):
        run = start_run(
            ctx_for(people["recruiter"], tenant), kind="matching", params={"requisition_id": requisition.id}
        )
    assert run_queued(tenant) == ["awaiting_review"]

    with tenant_scope(tenant.id):
        assessments = list(MatchingAssessment.objects.filter(agent_run_id=run.id))
        assert {a.application_id for a in assessments} == {app_a.id, app_b.id}
        langgraph = CriterionResult.objects.filter(assessment__in=assessments, criterion="LangGraph")
        assert all(r.model_status == "documented" and r.status == "not_documented" for r in langgraph)
        assert all(r.rejected_evidence and r.question for r in langgraph)
        rag = CriterionResult.objects.filter(assessment__in=assessments, criterion="RAG")
        assert all(r.status == "not_documented" for r in rag)  # RAG is not in either resume
        python = CriterionResult.objects.filter(assessment__in=assessments, criterion="Python")
        assert all(r.status == "documented" and r.evidence for r in python)
        assert not hasattr(assessments[0], "score")
        run_row = AgentRun.objects.get(pk=run.id)

    request_id = UUID(run_row.pending_interrupt["approval_request_id"])
    decisions = [
        {
            "application_id": str(app_a.id),
            "decision": "advance",
            "to_stage": "shortlisted",
            "reason": "Strong API and agent experience.",
        },
        {"application_id": str(app_b.id), "decision": "hold", "reason": "Ask about RAG first."},
    ]
    assert (
        decide_and_resume(tenant, people["recruiter"], request_id, "approve", edits={"decisions": decisions})
        == "completed"
    )
    with tenant_scope(tenant.id):
        assert JobApplication.objects.get(pk=app_a.id).stage == "shortlisted"
        assert JobApplication.objects.get(pk=app_b.id).stage == "applied"
        recorded = RecruiterDecision.objects.filter(agent_run_id=run.id)
        assert {d.actor_id for d in recorded} == {people["recruiter"].pk}
        assert all(d.assessment_id for d in recorded)


def test_communication_email_is_sent_once_after_approval(acme, settings) -> None:
    tenant, people, requisition = acme["tenant"], acme["people"], acme["requisition"]
    _, application, _ = add_candidate(tenant, people, requisition, name="Chen Li", email="chen@example.com")
    run_queued(tenant)
    with tenant_scope(tenant.id):
        run = start_run(
            ctx_for(people["recruiter"], tenant),
            kind="communication",
            params={"application_id": application.id, "kind": "update"},
        )
    assert run_queued(tenant) == ["awaiting_review"]
    with tenant_scope(tenant.id):
        draft = EmailDraft.objects.get(agent_run_id=run.id)
        assert draft.to_email == "chen@example.com"  # from the database, never from the model
        assert "Chen" in draft.body and "{{" not in draft.body
        assert draft.status == "pending_approval"
        request_id = AgentRun.objects.get(pk=run.id).pending_interrupt["approval_request_id"]
    assert len(mail.outbox) == 0
    from apps.communications.tasks import send_approved_email

    decide_and_resume(tenant, people["recruiter"], UUID(request_id), "approve")
    send_approved_email(draft_id=str(draft.id), tenant_id=str(tenant.id))
    send_approved_email(draft_id=str(draft.id), tenant_id=str(tenant.id))  # a retry must not send twice
    assert len(mail.outbox) == 1
    with tenant_scope(tenant.id):
        assert EmailMessage.objects.filter(draft=draft).count() == 1
        assert EmailDraft.objects.get(pk=draft.id).status == "sent"


def test_offer_needs_hr_then_finance_by_different_people(acme) -> None:
    from apps.applications.services import record_decision
    from apps.core.exceptions import PolicyDenied
    from apps.offers.models import Offer

    tenant, people, requisition = acme["tenant"], acme["people"], acme["requisition"]
    _, application, _ = add_candidate(tenant, people, requisition, name="Dev Patel", email="dev@example.com")
    run_queued(tenant)
    ctx = ctx_for(people["recruiter"], tenant)
    with tenant_scope(tenant.id):
        record_decision(ctx, application_id=application.id, decision="advance", to_stage="shortlisted", reason="Good")
        record_decision(ctx, application_id=application.id, decision="advance", to_stage="interview", reason="Good")
    fake.script("OfferProposal", lambda m: {"base_salary": 9_999_999, "bonus_percent": 5, "rationale": "High."})
    with tenant_scope(tenant.id):
        run = start_run(ctx_for(people["admin"], tenant), kind="offer", params={"application_id": application.id})
    assert run_queued(tenant) == ["awaiting_review"]
    with tenant_scope(tenant.id):
        offer = Offer.objects.get(agent_run_id=run.id)
        assert offer.base_salary == offer.comp_band.max_salary  # code clamped the model's number into the band
        step1 = ApprovalRequest.objects.get(kind="offer", target_id=offer.id, step=1)

    with pytest.raises(PolicyDenied):  # the requester cannot approve their own offer
        decide_and_resume(tenant, people["admin"], step1.id, "approve")
    assert decide_and_resume(tenant, people["admin2"], step1.id, "approve") is None  # run stays paused for finance
    with tenant_scope(tenant.id):
        step2 = ApprovalRequest.objects.get(kind="offer", target_id=offer.id, step=2)
        assert step2.required_roles == ["finance_approver"]
    assert decide_and_resume(tenant, people["finance"], step2.id, "approve") == "completed"
    with tenant_scope(tenant.id):
        assert Offer.objects.get(pk=offer.id).status == "approved"
        assert JobApplication.objects.get(pk=application.id).stage == "offer"


def test_scheduling_avoids_busy_time_and_confirms_one_slot(acme) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from apps.applications.services import record_decision
    from apps.integrations.models import CalendarBusyBlock
    from apps.interviews.models import Interview
    from apps.interviews.services import create_interview

    tenant, people, requisition = acme["tenant"], acme["people"], acme["requisition"]
    _, application, _ = add_candidate(tenant, people, requisition, name="Eva Gomez", email="eva@example.com")
    run_queued(tenant)
    ctx = ctx_for(people["recruiter"], tenant)
    with tenant_scope(tenant.id):
        record_decision(ctx, application_id=application.id, decision="advance", to_stage="shortlisted", reason="ok")
        interview = create_interview(
            ctx,
            application_id=application.id,
            title="Technical",
            panel_user_ids=[people["interviewer"].pk, people["manager"].pk],
        )
        # The interviewer is away for the next three days.
        busy_start = timezone.now()
        busy_end = busy_start + timedelta(days=3)
        CalendarBusyBlock.objects.create(user=people["interviewer"], start=busy_start, end=busy_end, title="Leave")
        run = start_run(ctx, kind="scheduling", params={"interview_id": interview.id, "days": 10})
    assert run_queued(tenant) == ["awaiting_review"]
    with tenant_scope(tenant.id):
        row = AgentRun.objects.get(pk=run.id)
        slots = row.output["result"]["slots"]
        assert len(slots) == 3
        from datetime import datetime

        assert all(datetime.fromisoformat(s["start"]) >= busy_end for s in slots)
    decide_and_resume(
        tenant,
        people["recruiter"],
        UUID(row.pending_interrupt["approval_request_id"]),
        "approve",
        edits={"slot_id": slots[-1]["id"]},
    )
    with tenant_scope(tenant.id):
        interview = Interview.objects.get(pk=interview.id)
        assert interview.status == "scheduled"
        assert interview.slots.filter(status="confirmed").count() == 1
        assert CalendarBusyBlock.objects.filter(interview=interview).count() == 2
        invite = EmailDraft.objects.get(interview=interview)
        assert invite.status == "approved" and "{{" not in invite.body


def test_tool_outside_the_agents_set_is_denied_and_logged(acme) -> None:
    from agent_engine.tools import ToolDenied, call_tool

    tenant, people = acme["tenant"], acme["people"]
    with tenant_scope(tenant.id):
        run = AgentRun.objects.create(kind="assistant", requested_by=people["recruiter"], graph_version="t")
    from dataclasses import replace

    ctx = replace(ctx_for(people["recruiter"], tenant), run_id=run.id)
    with pytest.raises(ToolDenied):
        call_tool(
            ctx,
            agent="assistant",
            name="create_email_draft",
            application_id=run.id,
            kind="update",
            subject="x",
            body="y",
            idempotency_key="k",
        )
    with tenant_scope(tenant.id):
        call = ToolCall.objects.get(run=run)
    assert call.status == "denied" and "may not use" in call.policy_reason


def test_budget_exceeded_ends_the_run(acme, settings) -> None:
    settings.AGENT_MAX_TOOL_CALLS = 1
    tenant, people = acme["tenant"], acme["people"]
    with tenant_scope(tenant.id):
        run = start_run(
            ctx_for(people["recruiter"], tenant), kind="sourcing", params={"requisition_id": acme["requisition"].id}
        )
    assert run_queued(tenant) == ["budget_exceeded"]
    assert "budget" in _run(tenant, run.id).error.lower()


def test_assistant_answers_with_citations_and_no_contact_details(acme) -> None:
    from apps.agents.services import ask_assistant

    tenant, people, requisition = acme["tenant"], acme["people"], acme["requisition"]
    candidate, _, _ = add_candidate(tenant, people, requisition, name="Farah Khan", email="farah@example.com")
    run_queued(tenant)
    with tenant_scope(tenant.id):
        run = ask_assistant(ctx_for(people["recruiter"], tenant), message="Who knows FastAPI and LangGraph?")
    assert run_queued(tenant) == ["completed"]
    answer = _run(tenant, run.id).output["result"]["answer"]
    assert f"[candidate:{candidate.id}]" in answer
    assert "farah@example.com" not in answer and "Farah" not in answer


def test_analytics_question_is_routed_to_a_whitelisted_report(acme) -> None:
    from apps.agents.services import ask_assistant

    tenant, people = acme["tenant"], acme["people"]
    with tenant_scope(tenant.id):
        run = ask_assistant(ctx_for(people["recruiter"], tenant), message="How many applications per stage?")
    assert run_queued(tenant) == ["completed"]
    result = _run(tenant, run.id).output["result"]
    assert result["report"]["name"] == "pipeline_funnel"
    assert "SELECT" in result["report"]["query"]


def test_phone_redaction_leaves_ids_intact() -> None:
    import re

    from agent_engine.nodes.insight import PHONE_PATTERN

    uuid = "2016dbdc-1699-4407-96a7-f06b8bd68be7"
    assert not re.search(PHONE_PATTERN, f"[candidate:{uuid}]")
    assert re.search(PHONE_PATTERN, "call +91 98765 43210 today")
