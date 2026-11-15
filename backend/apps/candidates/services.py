"""Candidates, consent, extracted facts and erasure."""

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.candidates.models import (
    Candidate,
    CandidateCertification,
    CandidateConsent,
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateSkill,
)
from apps.candidates.selectors import get_visible_candidate
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import candidate_reference, record_audit

FACT_MODELS: dict[str, type[Any]] = {
    "skill": CandidateSkill,
    "experience": CandidateExperience,
    "education": CandidateEducation,
    "certification": CandidateCertification,
}
FACT_FIELDS: dict[str, tuple[str, ...]] = {
    "skill": ("name", "years"),
    "experience": ("title", "organization", "start", "end", "summary"),
    "education": ("degree", "institution", "field_of_study", "year"),
    "certification": ("name", "issuer", "year"),
}
LOW_CONFIDENCE = 0.6


def _require_recruiter(ctx: ExecutionContext) -> None:
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins manage candidates.")


def create_candidate(
    ctx: ExecutionContext,
    *,
    full_name: str,
    email: str = "",
    phone: str = "",
    location: str = "",
    source: str = Candidate.Source.APPLIED,
    external_id: str = "",
    application_consent: bool = True,
    talent_pool_consent: bool = False,
    consent_source: str = "recorded by recruiter",
) -> Candidate:
    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    if not application_consent and not talent_pool_consent:
        raise ApplicationError("A candidate needs consent for at least one purpose before we store their data.")
    try:
        with transaction.atomic():
            candidate = Candidate.objects.create(
                full_name=full_name.strip(),
                email=email.strip().lower(),
                phone=phone.strip(),
                location=location.strip(),
                source=source,
                external_id=external_id,
                in_talent_pool=talent_pool_consent,
                created_by_id=ctx.user_id,
            )
    except IntegrityError as exc:
        raise ApplicationError(
            "A candidate with this email already exists.", details={"email": ["Already in use."]}
        ) from exc
    now = timezone.now()
    for purpose, granted in (
        (CandidateConsent.Purpose.APPLICATION, application_consent),
        (CandidateConsent.Purpose.TALENT_POOL, talent_pool_consent),
    ):
        if granted:
            CandidateConsent.objects.create(
                candidate=candidate,
                purpose=purpose,
                granted=True,
                granted_at=now,
                source=consent_source,
                recorded_by_id=ctx.user_id,
            )
    record_audit(
        ctx, action="candidate.created", target_type="candidate", target_id=candidate.id, details={"source": source}
    )
    return candidate


def set_consent(
    ctx: ExecutionContext, *, candidate_id: UUID, purpose: str, granted: bool, source: str = ""
) -> CandidateConsent:
    """Grant or withdraw consent. Withdrawal stops processing for that purpose immediately."""
    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    if purpose not in CandidateConsent.Purpose.values:
        raise ApplicationError("Unknown consent purpose.")
    with transaction.atomic():
        candidate = get_visible_candidate(ctx, candidate_id, for_update=True)
        consent, _ = CandidateConsent.objects.get_or_create(
            candidate=candidate,
            purpose=purpose,
            defaults={
                "granted": granted,
                "granted_at": timezone.now(),
                "source": source,
                "recorded_by_id": ctx.user_id,
            },
        )
        if granted:
            consent.granted, consent.withdrawn_at = True, None
            consent.granted_at = timezone.now()
        else:
            consent.withdrawn_at = timezone.now()
        consent.source = source or consent.source
        consent.recorded_by_id = ctx.user_id
        consent.save()
        if purpose == CandidateConsent.Purpose.TALENT_POOL:
            candidate.in_talent_pool = granted
            candidate.save(update_fields=["in_talent_pool", "updated_at"])
        record_audit(
            ctx,
            action="consent.granted" if granted else "consent.withdrawn",
            target_type="candidate",
            target_id=candidate.id,
            details={"purpose": purpose},
        )
    return consent


def save_extraction(
    ctx: ExecutionContext,
    *,
    candidate_id: UUID,
    document_id: UUID,
    extraction: dict[str, Any],
    run_id: UUID | None = None,
) -> CandidateProfile:
    """Replace the facts extracted from one document. Each fact keeps its evidence spans."""
    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    with transaction.atomic():
        candidate = get_visible_candidate(ctx, candidate_id, for_update=True)
        if not candidate.documents.filter(pk=document_id).exists():
            raise NotFound("Document not found for this candidate.")
        for model in FACT_MODELS.values():
            model.objects.filter(candidate=candidate, document_id=document_id).delete()

        def common(item: dict[str, Any]) -> dict[str, Any]:
            confidence = float(item.get("confidence", 1.0))
            return {
                "candidate": candidate,
                "document_id": document_id,
                "evidence": item.get("evidence", []),
                "confidence": confidence,
                "needs_review": confidence < LOW_CONFIDENCE or bool(item.get("needs_review")),
                "extraction_run_id": run_id,
            }

        CandidateSkill.objects.bulk_create(
            [
                CandidateSkill(
                    tenant_id=ctx.tenant_id, name=item["name"][:120], years=item.get("years"), **common(item)
                )
                for item in extraction.get("skills", [])
            ]
        )
        CandidateExperience.objects.bulk_create(
            [
                CandidateExperience(
                    tenant_id=ctx.tenant_id,
                    title=item.get("title", "")[:200],
                    organization=item.get("organization", "")[:200],
                    start=item.get("start") or "",
                    end=item.get("end") or "",
                    summary=item.get("summary", ""),
                    **common(item),
                )
                for item in extraction.get("experience", [])
            ]
        )
        CandidateEducation.objects.bulk_create(
            [
                CandidateEducation(
                    tenant_id=ctx.tenant_id,
                    degree=item.get("degree", "")[:200],
                    institution=item.get("institution", "")[:200],
                    field_of_study=item.get("field_of_study", "")[:200],
                    year=item.get("year") or "",
                    **common(item),
                )
                for item in extraction.get("education", [])
            ]
        )
        CandidateCertification.objects.bulk_create(
            [
                CandidateCertification(
                    tenant_id=ctx.tenant_id,
                    name=item.get("name", "")[:200],
                    issuer=item.get("issuer", "")[:200],
                    year=item.get("year") or "",
                    **common(item),
                )
                for item in extraction.get("certifications", [])
            ]
        )
        profile, _ = CandidateProfile.objects.get_or_create(candidate=candidate)
        profile.missing_sections = list(extraction.get("missing_sections", []))
        profile.extracted_at = timezone.now()
        profile.extraction_run_id = run_id
        profile.source_document_id = document_id
        profile.save()
        record_audit(
            ctx,
            action="extraction.saved",
            target_type="candidate",
            target_id=candidate.id,
            run_id=run_id,
            details={"document_id": str(document_id), "skills": len(extraction.get("skills", []))},
        )
    return profile


def correct_fact(ctx: ExecutionContext, *, fact_type: str, fact_id: UUID, changes: dict[str, Any]) -> Any:
    """A recruiter confirms or fixes an extracted fact from the correction queue."""
    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    model = FACT_MODELS.get(fact_type)
    if model is None:
        raise ApplicationError("Unknown fact type.")
    unknown = set(changes) - set(FACT_FIELDS[fact_type])
    if unknown:
        raise ApplicationError(f"Cannot edit {sorted(unknown)}.")
    from apps.candidates.selectors import visible_candidates

    with transaction.atomic():
        fact = (
            model.objects.select_for_update()
            .filter(pk=fact_id, candidate__in=visible_candidates(ctx).values("pk"))
            .first()
        )
        if fact is None:
            raise NotFound("Fact not found.")
        for field, value in changes.items():
            setattr(fact, field, value)
        fact.needs_review = False
        fact.reviewed_by_id = ctx.user_id
        fact.reviewed_at = timezone.now()
        fact.save()
        record_audit(
            ctx,
            action="extraction.corrected",
            target_type=f"candidate_{fact_type}",
            target_id=fact.id,
            details={"fields": sorted(changes)},
        )
    return fact


def _erase(candidate: Candidate) -> None:
    from apps.documents.services import delete_document_system

    for document in list(candidate.documents.all()):
        delete_document_system(document_id=document.id)
    for model in FACT_MODELS.values():
        model.objects.filter(candidate=candidate).delete()
    CandidateProfile.objects.filter(candidate=candidate).delete()
    candidate.email_drafts.exclude(status="sent").update(status="cancelled", body="", subject="[erased]")
    ref = candidate_reference(candidate.id)
    candidate.full_name = f"Erased candidate {ref[:8]}"
    candidate.email = ""
    candidate.phone = ""
    candidate.location = ""
    candidate.external_id = ""
    candidate.in_talent_pool = False
    candidate.is_anonymized = True
    candidate.save()
    candidate.consents.update(withdrawn_at=timezone.now())


def erase_candidate(ctx: ExecutionContext, *, candidate_id: UUID) -> None:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN):
        raise PolicyDenied("Only HR admins erase candidate data.")
    candidate = get_visible_candidate(ctx, candidate_id, for_update=True)
    _erase(candidate)
    record_audit(ctx, action="candidate.erased", target_type="candidate", target_id=candidate_id)


def erase_candidate_system(*, candidate_id: UUID) -> None:
    """Retention purge: runs inside tenant_scope with no user."""
    candidate = Candidate.objects.select_for_update().filter(pk=candidate_id).first()
    if candidate is not None:
        _erase(candidate)
        record_audit(None, action="candidate.erased_by_retention", target_type="candidate", target_id=candidate_id)
