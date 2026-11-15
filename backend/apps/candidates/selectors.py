from uuid import UUID

from django.db.models import Q, QuerySet

from apps.accounts.roles import Role
from apps.candidates.models import Candidate, CandidateConsent
from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound


def visible_candidates(ctx: ExecutionContext) -> QuerySet[Candidate]:
    """HR admins see everyone. Others see candidates on applications they can see;
    recruiters also see consented talent-pool profiles and candidates they added."""
    from apps.applications.selectors import visible_applications

    queryset = Candidate.objects.filter(tenant_id=ctx.tenant_id)
    if ctx.has_role(Role.HR_ADMIN):
        return queryset
    condition = Q(pk__in=visible_applications(ctx).values("candidate_id"))
    if ctx.has_role(Role.RECRUITER):
        condition |= Q(in_talent_pool=True) | Q(created_by_id=ctx.user_id)
    return queryset.filter(condition)


def get_visible_candidate(ctx: ExecutionContext, candidate_id: UUID, *, for_update: bool = False) -> Candidate:
    queryset = visible_candidates(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    candidate = queryset.filter(pk=candidate_id).first()
    if candidate is None:
        raise NotFound("Candidate not found.")
    return candidate


def has_active_consent(candidate_id: UUID, purpose: str) -> bool:
    return CandidateConsent.objects.filter(
        candidate_id=candidate_id, purpose=purpose, granted=True, withdrawn_at__isnull=True
    ).exists()


def talent_pool(ctx: ExecutionContext) -> QuerySet[Candidate]:
    """Consented talent-pool candidates only. Withdrawn consent removes them at once."""
    consented = CandidateConsent.objects.filter(
        purpose=CandidateConsent.Purpose.TALENT_POOL, granted=True, withdrawn_at__isnull=True
    ).values("candidate_id")
    return Candidate.objects.filter(tenant_id=ctx.tenant_id, in_talent_pool=True, is_anonymized=False, pk__in=consented)


def review_queue(ctx: ExecutionContext) -> dict[str, list[object]]:
    """Low-confidence extracted facts waiting for a recruiter to confirm or fix."""
    from apps.candidates.models import (
        CandidateCertification,
        CandidateEducation,
        CandidateExperience,
        CandidateSkill,
    )

    visible = visible_candidates(ctx).values("pk")
    queue: dict[str, list[object]] = {}
    for key, model in (
        ("skills", CandidateSkill),
        ("experience", CandidateExperience),
        ("education", CandidateEducation),
        ("certifications", CandidateCertification),
    ):
        queue[key] = list(model.objects.filter(candidate__in=visible, needs_review=True)[:200])
    return queue
