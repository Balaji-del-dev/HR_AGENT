"""Every agent tool. Each wraps a selector or service; none touches the ORM directly for writes.

Read tools return masked text and ids, never names or contact details, so
nothing identifying reaches a prompt. Side-effect tools create drafts only.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.utils import timezone
from pydantic import BaseModel, Field

from agent_engine.tools.registry import tool
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError

# ---------------------------------------------------------------- argument schemas


class RequisitionArgs(BaseModel):
    requisition_id: UUID


class NoArgs(BaseModel):
    pass


class DepartmentArgs(BaseModel):
    department: str = ""


class TextArgs(BaseModel):
    text: str = Field(max_length=50_000)


class JDDraftArgs(BaseModel):
    requisition_id: UUID
    title: str = Field(max_length=200)
    summary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    body: str = ""
    prompt_version: str = ""


class TalentPoolArgs(BaseModel):
    requisition_id: UUID
    k: int = Field(default=10, ge=1, le=50)


class DocumentArgs(BaseModel):
    document_id: UUID


class SaveExtractionArgs(BaseModel):
    candidate_id: UUID
    document_id: UUID
    extraction: dict[str, Any]


class CandidateArgs(BaseModel):
    candidate_id: UUID


class ChunkSearchArgs(BaseModel):
    candidate_id: UUID
    query: str = Field(max_length=200)
    terms: list[str] = Field(default_factory=list)
    k: int = Field(default=3, ge=1, le=10)


class SpanArgs(BaseModel):
    candidate_id: UUID
    span_id: str = Field(max_length=80)


class SaveAssessmentArgs(BaseModel):
    application_id: UUID
    criteria: list[dict[str, Any]]
    prompt_version: str
    model_name: str


class SearchArgs(BaseModel):
    query: str = Field(max_length=300)
    k: int = Field(default=8, ge=1, le=25)


class OptionalRequisitionArgs(BaseModel):
    requisition_id: UUID | None = None


class TemplateArgs(BaseModel):
    kind: str
    key: str = ""


class EmailDraftArgs(BaseModel):
    application_id: UUID
    kind: str
    subject: str = Field(max_length=200)
    body: str = Field(max_length=10_000)
    idempotency_key: str = Field(max_length=80)


class FreeBusyArgs(BaseModel):
    interview_id: UUID
    days: int = Field(default=7, ge=1, le=21)


class ProposeSlotsArgs(BaseModel):
    interview_id: UUID
    slots: list[dict[str, str]]


class InviteArgs(BaseModel):
    interview_id: UUID
    subject: str = Field(max_length=200)
    body: str = Field(max_length=10_000)
    idempotency_key: str = Field(max_length=80)


class ApplicationArgs(BaseModel):
    application_id: UUID


class OfferDraftArgs(BaseModel):
    application_id: UUID
    base_salary: Decimal = Field(gt=0)
    bonus_percent: Decimal | None = None
    rationale: str = ""


class ApprovalArgs(BaseModel):
    kind: str
    target_id: UUID
    review_round: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportArgs(BaseModel):
    report: str
    requisition_id: UUID | None = None


# ---------------------------------------------------------------- requisitions and JDs


def _requisition_dict(requisition: Any) -> dict[str, Any]:
    band = requisition.comp_band
    return {
        "id": str(requisition.id),
        "title": requisition.title,
        "department": requisition.department,
        "location": requisition.location,
        "level": requisition.level,
        "employment_type": requisition.employment_type,
        "headcount": requisition.headcount,
        "summary": requisition.summary,
        "must_have_skills": requisition.must_have_skills,
        "nice_to_have_skills": requisition.nice_to_have_skills,
        "status": requisition.status,
        "comp_band": None
        if band is None
        else {"level": band.level, "currency": band.currency, "min": str(band.min_salary), "max": str(band.max_salary)},
    }


@tool(
    "get_requisition",
    description="Read a requisition's fields.",
    args=RequisitionArgs,
    agents={"requisition_review", "jd_generation", "sourcing", "offer", "compliance", "matching"},
)
def get_requisition(ctx: ExecutionContext, args: RequisitionArgs) -> dict[str, Any]:
    from apps.requisitions.selectors import get_visible_requisition

    return _requisition_dict(get_visible_requisition(ctx, args.requisition_id))


@tool(
    "get_comp_band",
    description="The approved comp band for a requisition.",
    args=RequisitionArgs,
    agents={"requisition_review", "offer"},
)
def get_comp_band(ctx: ExecutionContext, args: RequisitionArgs) -> dict[str, Any] | None:
    from apps.requisitions.selectors import get_visible_requisition

    band: dict[str, Any] | None = _requisition_dict(get_visible_requisition(ctx, args.requisition_id))["comp_band"]
    return band


@tool(
    "list_departments", description="Department names used in this tenant.", args=NoArgs, agents={"requisition_review"}
)
def list_departments(ctx: ExecutionContext, args: NoArgs) -> list[str]:
    from apps.requisitions.selectors import departments

    return departments(ctx)


@tool(
    "get_jd_templates",
    description="Reviewed JD templates for a department.",
    args=DepartmentArgs,
    agents={"jd_generation"},
)
def get_jd_templates(ctx: ExecutionContext, args: DepartmentArgs) -> list[dict[str, str]]:
    from apps.jobs.selectors import templates_for

    return [{"name": t.name, "body": t.body} for t in templates_for(ctx, args.department)[:3]]


@tool(
    "check_inclusive_language",
    description="Flag biased or exclusionary wording.",
    args=TextArgs,
    agents={"jd_generation", "communication", "compliance"},
)
def check_inclusive_language(ctx: ExecutionContext, args: TextArgs) -> list[dict[str, Any]]:
    from apps.jobs.inclusive import check_inclusive_language as check

    return [flag.as_dict() for flag in check(args.text)]


@tool(
    "create_jd_draft",
    description="Save a JD draft for review. Does not approve it.",
    args=JDDraftArgs,
    agents={"jd_generation"},
    side_effect=True,
)
def create_jd_draft(ctx: ExecutionContext, args: JDDraftArgs) -> dict[str, Any]:
    from apps.jobs.services import create_jd_draft as create

    jd = create(
        ctx,
        requisition_id=args.requisition_id,
        title=args.title,
        summary=args.summary,
        responsibilities=args.responsibilities,
        requirements=args.requirements,
        body=args.body,
        agent_run_id=ctx.run_id,
        prompt_version=args.prompt_version,
    )
    return {
        "id": str(jd.id),
        "version": jd.version,
        "compliance_flags": jd.compliance_flags,
        "requirements": jd.requirements,
    }


# ---------------------------------------------------------------- sourcing


@tool(
    "ats_list_applicants",
    description="Applicants on a requisition, with source and stage.",
    args=RequisitionArgs,
    agents={"sourcing"},
)
def ats_list_applicants(ctx: ExecutionContext, args: RequisitionArgs) -> list[dict[str, Any]]:
    from apps.applications.selectors import applications_for_requisition

    return [
        {
            "application_id": str(a.id),
            "candidate_id": str(a.candidate_id),
            "source": a.source,
            "stage": a.stage,
            "consent": "application",
        }
        for a in applications_for_requisition(ctx, args.requisition_id)
    ]


@tool(
    "search_talent_pool",
    description="Consented talent-pool candidates ranked against the requisition.",
    args=TalentPoolArgs,
    agents={"sourcing"},
    resource=lambda ctx, args: {"include_unconsented": False},
)
def search_talent_pool(ctx: ExecutionContext, args: TalentPoolArgs) -> list[dict[str, Any]]:
    from agent_engine.llm.embeddings import embed_query_safely, get_embedder
    from apps.candidates.selectors import talent_pool
    from apps.documents.vector import rank_candidates
    from apps.requisitions.selectors import get_visible_requisition

    requisition = get_visible_requisition(ctx, args.requisition_id)
    already = set(requisition.applications.values_list("candidate_id", flat=True))
    pool = [c for c in talent_pool(ctx).values_list("id", flat=True) if c not in already]
    query = " ".join([requisition.title, *requisition.must_have_skills, *requisition.nice_to_have_skills])
    ranked = rank_candidates(
        candidate_ids=pool,
        query=query,
        query_embedding=embed_query_safely(query),
        embedding_model=get_embedder().model_name,
        extra_terms=requisition.must_have_skills,
    )
    return [
        {"candidate_id": str(cid), "score": round(score, 3), "source": "talent_pool", "consent": "talent_pool"}
        for cid, score in ranked[: args.k]
    ]


# ---------------------------------------------------------------- resume parsing


@tool(
    "get_document_text",
    description="A processed resume as masked spans with stable ids.",
    args=DocumentArgs,
    agents={"resume_parsing"},
)
def get_document_text(ctx: ExecutionContext, args: DocumentArgs) -> dict[str, Any]:
    from apps.documents.models import CandidateDocument
    from apps.documents.selectors import get_visible_document

    document = get_visible_document(ctx, args.document_id)
    if document.status != CandidateDocument.Status.PROCESSED:
        raise ApplicationError("The document has not finished processing.")
    spans = [
        {"id": s.span_id, "section": s.section, "text": s.text_masked} for s in document.spans.all() if s.text_masked
    ]
    return {
        "document_id": str(document.id),
        "candidate_id": str(document.candidate_id),
        "spans": spans,
        "injection_suspected": document.injection_suspected,
    }


@tool(
    "save_extraction",
    description="Store the validated resume extraction.",
    args=SaveExtractionArgs,
    agents={"resume_parsing"},
    side_effect=True,
    summarize=lambda result: result,
)
def save_extraction(ctx: ExecutionContext, args: SaveExtractionArgs) -> dict[str, Any]:
    from apps.candidates.services import save_extraction as save

    profile = save(
        ctx, candidate_id=args.candidate_id, document_id=args.document_id, extraction=args.extraction, run_id=ctx.run_id
    )
    return {
        "candidate_id": str(profile.candidate_id),
        "missing_sections": profile.missing_sections,
        "skills": len(args.extraction.get("skills", [])),
    }


# ---------------------------------------------------------------- matching and validation


@tool(
    "get_job_requirements",
    description="The approved JD's criteria for a requisition.",
    args=RequisitionArgs,
    agents={"matching"},
)
def get_job_requirements(ctx: ExecutionContext, args: RequisitionArgs) -> dict[str, Any]:
    from apps.jobs.selectors import approved_jd
    from apps.requisitions.selectors import get_visible_requisition

    requisition = get_visible_requisition(ctx, args.requisition_id)
    jd = approved_jd(requisition.id)
    if jd is None:
        raise ApplicationError("This requisition has no approved JD yet.")
    return {
        "job_description_id": str(jd.id),
        "version": jd.version,
        "requirements": [
            {"id": str(r.id), "name": r.name, "level": r.level, "aliases": r.aliases} for r in jd.requirement_rows.all()
        ],
    }


@tool(
    "get_candidate_evidence",
    description="All masked spans of a candidate's latest resume.",
    args=CandidateArgs,
    agents={"matching"},
)
def get_candidate_evidence(ctx: ExecutionContext, args: CandidateArgs) -> dict[str, Any]:
    from apps.candidates.selectors import get_visible_candidate
    from apps.documents.selectors import latest_resume

    candidate = get_visible_candidate(ctx, args.candidate_id)
    document = latest_resume(candidate.id)
    if document is None:
        return {"document_id": None, "spans": {}}
    return {
        "document_id": str(document.id),
        "spans": {s.span_id: s.text_masked for s in document.spans.all() if s.text_masked},
    }


@tool(
    "search_resume_chunks",
    description="The candidate's resume chunks most relevant to a query.",
    args=ChunkSearchArgs,
    agents={"matching"},
)
def search_resume_chunks(ctx: ExecutionContext, args: ChunkSearchArgs) -> list[dict[str, Any]]:
    from agent_engine.llm.embeddings import embed_query_safely, get_embedder
    from apps.candidates.selectors import get_visible_candidate
    from apps.documents.models import DocumentSpan
    from apps.documents.vector import search_candidate_chunks

    candidate = get_visible_candidate(ctx, args.candidate_id)
    results = search_candidate_chunks(
        candidate_id=candidate.id,
        query=args.query,
        query_embedding=embed_query_safely(args.query),
        embedding_model=get_embedder().model_name,
        extra_terms=args.terms,
        k=args.k,
    )
    span_ids = [span_id for chunk, _ in results for span_id in chunk.span_ids]
    texts = dict(
        DocumentSpan.objects.filter(document__candidate=candidate, span_id__in=span_ids).values_list(
            "span_id", "text_masked"
        )
    )
    return [
        {
            "section": chunk.section,
            "score": round(score, 3),
            "lines": [{"span_id": sid, "text": texts.get(sid, "")} for sid in chunk.span_ids if texts.get(sid)],
        }
        for chunk, score in results
    ]


@tool(
    "get_document_span",
    description="One span's masked text, for validating a citation.",
    args=SpanArgs,
    agents={"matching"},
)
def get_document_span(ctx: ExecutionContext, args: SpanArgs) -> dict[str, Any] | None:
    from apps.candidates.selectors import get_visible_candidate
    from apps.documents.models import DocumentSpan

    candidate = get_visible_candidate(ctx, args.candidate_id)
    span = DocumentSpan.objects.filter(document__candidate=candidate, span_id=args.span_id).first()
    return None if span is None else {"span_id": span.span_id, "text": span.text_masked}


@tool(
    "save_assessment",
    description="Store one application's validated criteria matrix.",
    args=SaveAssessmentArgs,
    agents={"matching"},
    side_effect=True,
)
def save_assessment(ctx: ExecutionContext, args: SaveAssessmentArgs) -> dict[str, Any]:
    from agent_engine.version import GRAPH_VERSION
    from apps.matching.services import save_assessment as save

    assessment = save(
        ctx,
        application_id=args.application_id,
        criteria=args.criteria,
        run_id=ctx.run_id,
        prompt_version=args.prompt_version,
        model_name=args.model_name,
        graph_version=GRAPH_VERSION,
    )
    return {
        "assessment_id": str(assessment.id),
        "application_id": str(args.application_id),
        "summary": assessment.summary,
    }


# ---------------------------------------------------------------- recruiter assistant


@tool(
    "search_candidates",
    description="Find candidates you can see whose resumes mention the query terms.",
    args=SearchArgs,
    agents={"assistant"},
)
def search_candidates(ctx: ExecutionContext, args: SearchArgs) -> dict[str, Any]:
    import re

    from apps.candidates.models import CandidateSkill
    from apps.candidates.selectors import visible_candidates

    terms = [t for t in re.findall(r"[A-Za-z0-9+#.]+", args.query) if len(t) > 1][:8]
    visible = visible_candidates(ctx).filter(is_anonymized=False)
    found: dict[UUID, list[str]] = {}
    for skill in CandidateSkill.objects.filter(candidate__in=visible.values("pk")).only("candidate_id", "name"):
        if any(term.lower() == skill.name.lower() for term in terms):
            found.setdefault(skill.candidate_id, []).append(skill.name)
    ranked = sorted(found.items(), key=lambda item: len(item[1]), reverse=True)[: args.k]
    return {
        "candidates": [
            {"id": str(cid), "label": f"Candidate {str(cid)[:8]}", "matched": sorted(set(names))}
            for cid, names in ranked
        ]
    }


@tool(
    "pipeline_stats",
    description="Applications by stage for requisitions you can see.",
    args=OptionalRequisitionArgs,
    agents={"assistant"},
)
def pipeline_stats(ctx: ExecutionContext, args: OptionalRequisitionArgs) -> dict[str, Any]:
    from apps.analytics.reports import pipeline_funnel

    return pipeline_funnel(ctx, args.requisition_id).as_dict()


@tool(
    "search_policy_docs", description="Hiring policies relevant to a question.", args=SearchArgs, agents={"assistant"}
)
def search_policy_docs(ctx: ExecutionContext, args: SearchArgs) -> dict[str, Any]:
    from policies.engine import POLICY_RULES

    words = {w.lower() for w in args.query.split() if len(w) > 3}
    hits = [rule for rule in POLICY_RULES if words & set(rule["rule"].lower().replace(",", " ").split())]
    return {"rules": hits or POLICY_RULES[:4]}


# ---------------------------------------------------------------- communication


@tool(
    "get_template",
    description="The tenant's email template for a kind of message.",
    args=TemplateArgs,
    agents={"communication", "scheduling"},
)
def get_template(ctx: ExecutionContext, args: TemplateArgs) -> dict[str, Any] | None:
    from apps.communications.models import EmailTemplate

    queryset = EmailTemplate.objects.filter(tenant_id=ctx.tenant_id, is_active=True, kind=args.kind)
    if args.key:
        queryset = queryset.filter(key=args.key)
    template = queryset.first()
    return None if template is None else {"id": str(template.id), "subject": template.subject, "body": template.body}


def _placeholders(ctx: ExecutionContext, application: Any) -> dict[str, str]:
    from apps.accounts.models import User
    from apps.core.models import Tenant

    recruiter = User.objects.filter(pk=ctx.user_id).first()
    return {
        "candidate_first_name": application.candidate.full_name.split()[0]
        if application.candidate.full_name
        else "there",
        "job_title": application.requisition.title,
        "company_name": Tenant.objects.get(pk=ctx.tenant_id).name,
        "recruiter_name": (recruiter.get_full_name() or recruiter.username) if recruiter else "The hiring team",
    }


def _email_resource(ctx: ExecutionContext, args: Any) -> dict[str, Any]:
    from apps.applications.selectors import visible_applications

    return {"candidate_on_visible_requisition": visible_applications(ctx).filter(pk=args.application_id).exists()}


@tool(
    "create_email_draft",
    description="Create an email draft to the applicant. It is not sent.",
    args=EmailDraftArgs,
    agents={"communication"},
    side_effect=True,
    resource=_email_resource,
)
def create_email_draft(ctx: ExecutionContext, args: EmailDraftArgs) -> dict[str, Any]:
    from apps.applications.selectors import get_visible_application
    from apps.communications.services import create_email_draft as create
    from apps.communications.services import render

    application = get_visible_application(ctx, args.application_id)
    values = _placeholders(ctx, application)
    # Placeholders are filled here, in code, so the model never sees the candidate's name.
    draft = create(
        ctx,
        candidate_id=application.candidate_id,
        application_id=application.id,
        kind=args.kind,
        subject=render(args.subject, values),
        body=render(args.body, values),
        run_id=ctx.run_id,
        idempotency_key=args.idempotency_key,
    )
    return {"id": str(draft.id), "kind": draft.kind, "subject": draft.subject}


# ---------------------------------------------------------------- scheduling


@tool(
    "calendar_free_busy",
    description="Common free slots for an interview panel.",
    args=FreeBusyArgs,
    agents={"scheduling"},
)
def calendar_free_busy(ctx: ExecutionContext, args: FreeBusyArgs) -> list[dict[str, str]]:
    from apps.interviews.services import free_slots

    return [
        {"start": s.start.isoformat(), "end": s.end.isoformat()}
        for s in free_slots(ctx, interview_id=args.interview_id, days=args.days)
    ]


@tool(
    "propose_interview_slots",
    description="Record proposed slots for the recruiter to confirm.",
    args=ProposeSlotsArgs,
    agents={"scheduling"},
    side_effect=True,
)
def propose_interview_slots(ctx: ExecutionContext, args: ProposeSlotsArgs) -> list[dict[str, str]]:
    from apps.interviews.scheduling import Interval
    from apps.interviews.services import propose_slots

    intervals = [Interval(datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"])) for s in args.slots]
    return [
        {"id": str(s.id), "start": s.start.isoformat(), "end": s.end.isoformat()}
        for s in propose_slots(ctx, interview_id=args.interview_id, slots=intervals, run_id=ctx.run_id)
    ]


@tool(
    "create_invite_draft",
    description="Draft the interview invite email. It is not sent.",
    args=InviteArgs,
    agents={"scheduling"},
    side_effect=True,
    resource=lambda ctx, args: {"candidate_on_visible_requisition": True},
)
def create_invite_draft(ctx: ExecutionContext, args: InviteArgs) -> dict[str, Any]:
    from apps.communications.services import create_email_draft as create
    from apps.communications.services import render
    from apps.interviews.services import get_visible_interview

    interview = get_visible_interview(ctx, args.interview_id)
    application = interview.application
    values = _placeholders(ctx, application) | {"slot_time": "{{ slot_time }}"}
    draft = create(
        ctx,
        candidate_id=application.candidate_id,
        application_id=application.id,
        interview_id=interview.id,
        kind="invite",
        subject=render(args.subject, values),
        body=render(args.body, values),
        run_id=ctx.run_id,
        idempotency_key=args.idempotency_key,
    )
    return {"id": str(draft.id)}


# ---------------------------------------------------------------- feedback and offers


@tool(
    "get_scorecards",
    description="Submitted scorecards for an application, with identity masked.",
    args=ApplicationArgs,
    agents={"feedback", "offer"},
)
def get_scorecards(ctx: ExecutionContext, args: ApplicationArgs) -> list[dict[str, Any]]:
    from apps.applications.selectors import get_visible_application
    from apps.interviews.services import scorecards_for_application
    from document_ai.masking import Identity, make_masker

    application = get_visible_application(ctx, args.application_id)
    candidate = application.candidate
    masker = make_masker(Identity(candidate.full_name, candidate.email, candidate.phone), backend="patterns")
    cards = []
    for index, card in enumerate(scorecards_for_application(ctx, application.id), start=1):
        cards.append(
            {
                "ref": f"S{index}",
                "scorecard_id": str(card.id),
                "interview": card.interview.title,
                "round": card.interview.round,
                "recommendation": card.recommendation,
                "ratings": card.ratings,
                "strengths": masker.mask(card.strengths).text,
                "concerns": masker.mask(card.concerns).text,
            }
        )
    return cards


def _offer_resource(ctx: ExecutionContext, args: OfferDraftArgs) -> dict[str, Any]:
    from apps.applications.selectors import get_visible_application

    band = get_visible_application(ctx, args.application_id).requisition.comp_band
    if band is None:
        return {"base_salary": args.base_salary}
    return {"base_salary": args.base_salary, "band_min": band.min_salary, "band_max": band.max_salary}


@tool(
    "create_offer_draft",
    description="Create an offer draft inside the approved band.",
    args=OfferDraftArgs,
    agents={"offer"},
    side_effect=True,
    resource=_offer_resource,
)
def create_offer_draft(ctx: ExecutionContext, args: OfferDraftArgs) -> dict[str, Any]:
    from apps.offers.services import create_offer_draft as create

    offer = create(
        ctx,
        application_id=args.application_id,
        base_salary=args.base_salary,
        bonus_percent=args.bonus_percent,
        rationale=args.rationale,
        run_id=ctx.run_id,
        start_date=(timezone.now() + timedelta(days=30)).date(),
    )
    return {"id": str(offer.id), "base_salary": str(offer.base_salary), "currency": offer.currency}


@tool(
    "start_approval",
    description="Open the approval request for a draft.",
    args=ApprovalArgs,
    agents={"jd_generation", "communication", "scheduling", "offer", "matching"},
    side_effect=True,
)
def start_approval(ctx: ExecutionContext, args: ApprovalArgs) -> dict[str, Any]:
    from apps.accounts.roles import Role
    from apps.approvals.services import open_request
    from apps.communications.services import submit_draft_for_approval
    from apps.interviews.services import get_visible_interview
    from apps.jobs.services import submit_jd_for_approval
    from apps.offers.services import submit_offer

    if args.kind == "job_description":
        request = submit_jd_for_approval(
            ctx, jd_id=args.target_id, agent_run_id=ctx.run_id, review_round=args.review_round
        )
    elif args.kind == "email":
        request = submit_draft_for_approval(
            ctx, draft_id=args.target_id, run_id=ctx.run_id, review_round=args.review_round
        )
    elif args.kind == "offer":
        request = submit_offer(ctx, offer_id=args.target_id, run_id=ctx.run_id, review_round=args.review_round)
    elif args.kind == "interview_schedule":
        interview = get_visible_interview(ctx, args.target_id)
        request = open_request(
            ctx,
            kind="interview_schedule",
            target_id=interview.id,
            title=f"Confirm interview time: {interview.title}",
            summary=f"{len(args.payload.get('slots', []))} proposed slot(s)",
            payload=args.payload,
            required_roles=[Role.RECRUITER, Role.HR_ADMIN],
            requisition_id=interview.application.requisition_id,
            agent_run_id=ctx.run_id,
            review_round=args.review_round,
        )
    elif args.kind == "shortlist_review":
        request = open_request(
            ctx,
            kind="shortlist_review",
            target_id=args.target_id,
            title="Review the criteria matrices",
            summary=f"{len(args.payload.get('assessments', []))} candidate(s) assessed",
            payload=args.payload,
            required_roles=[Role.RECRUITER, Role.HR_ADMIN],
            requisition_id=args.target_id,
            agent_run_id=ctx.run_id,
            review_round=args.review_round,
        )
    else:
        raise ApplicationError(f"Unknown approval kind {args.kind}.")
    return {"approval_request_id": str(request.id), "kind": request.kind, "title": request.title}


# ---------------------------------------------------------------- analytics and compliance


@tool("run_report", description="Run one whitelisted read-only report.", args=ReportArgs, agents={"analytics"})
def run_report(ctx: ExecutionContext, args: ReportArgs) -> dict[str, Any]:
    from apps.analytics.reports import run_report as run

    return run(ctx, args.report, requisition_id=args.requisition_id).as_dict()


@tool("get_policy_rules", description="The platform's hiring policy rules.", args=NoArgs, agents={"compliance"})
def get_policy_rules(ctx: ExecutionContext, args: NoArgs) -> list[dict[str, str]]:
    from policies.engine import POLICY_RULES

    return POLICY_RULES
