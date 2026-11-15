"""Pydantic schemas for every structured LLM output.

Models return these through structured output (JSON schema). Code validates
them again before anything is stored: a schema-valid answer is not yet a
trusted one.
"""

from typing import Literal

from pydantic import BaseModel, Field

CriterionStatus = Literal["documented", "not_documented", "unclear"]
RequirementLevel = Literal["mandatory", "required", "preferred"]


class RouteDecision(BaseModel):
    """Supervisor classification for free-text assistant messages."""

    intent: Literal["assistant", "analytics", "unclear"]
    clarifying_question: str = Field(default="", description="Only when intent is unclear.")


class Suggestion(BaseModel):
    field: str
    issue: str
    suggestion: str


class RequisitionSuggestions(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)


class RequirementOut(BaseModel):
    name: str = Field(description="A skill or qualification, e.g. 'Python'.")
    level: RequirementLevel
    aliases: list[str] = Field(default_factory=list)


class JDDraftOut(BaseModel):
    title: str
    summary: str
    responsibilities: list[str] = Field(min_length=1)
    requirements: list[RequirementOut] = Field(min_length=1)
    body: str = Field(description="The full JD in Markdown.")


class Evidence(BaseModel):
    span_id: str = Field(description="Exactly as given, e.g. doc_8f2a1b3c:p2:1840-1912")
    quote: str = Field(description="Exact text copied from that span.")


class SkillClaim(BaseModel):
    name: str
    years: float | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ExperienceItem(BaseModel):
    title: str
    organization: str = ""
    start: str = Field(default="", description="YYYY or YYYY-MM")
    end: str = Field(default="", description="YYYY or YYYY-MM; empty if current")
    summary: str = ""
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class EducationItem(BaseModel):
    degree: str
    institution: str = ""
    field_of_study: str = ""
    year: str = ""
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class CertificationItem(BaseModel):
    name: str
    issuer: str = ""
    year: str = ""
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ResumeExtraction(BaseModel):
    skills: list[SkillClaim] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)


class CriterionAssessment(BaseModel):
    status: CriterionStatus
    evidence: list[Evidence] = Field(default_factory=list)
    question: str = Field(default="", description="What to ask the candidate if not documented or unclear.")


class EmailDraftOut(BaseModel):
    subject: str
    body: str = Field(description="Plain text. Keep every {{ placeholder }} exactly as given.")


class FeedbackPoint(BaseModel):
    scorecard_ref: str = Field(description="The S-number of the scorecard this point comes from, e.g. S1.")
    point: str


class FeedbackSummary(BaseModel):
    summary: str
    points: list[FeedbackPoint] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)


class OfferProposal(BaseModel):
    base_salary: float = Field(gt=0)
    bonus_percent: float | None = Field(default=None, ge=0, le=100)
    rationale: str


class ReportChoice(BaseModel):
    report: Literal[
        "pipeline_funnel", "time_in_stage", "source_breakdown", "override_rate", "requisition_status", "agent_health"
    ]


class ComplianceFinding(BaseModel):
    category: str
    excerpt: str
    explanation: str


class ComplianceFindings(BaseModel):
    findings: list[ComplianceFinding] = Field(default_factory=list)
