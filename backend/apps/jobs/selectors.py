from uuid import UUID

from django.db.models import Q, QuerySet

from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound
from apps.jobs.models import JDTemplate, JobDescription, JobRequirement
from apps.requisitions.selectors import visible_requisitions


def visible_jds(ctx: ExecutionContext) -> QuerySet[JobDescription]:
    return JobDescription.objects.filter(
        tenant_id=ctx.tenant_id, requisition__in=visible_requisitions(ctx).values("pk")
    )


def get_visible_jd(ctx: ExecutionContext, jd_id: UUID, *, for_update: bool = False) -> JobDescription:
    queryset = visible_jds(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    jd = queryset.filter(pk=jd_id).first()
    if jd is None:
        raise NotFound("Job description not found.")
    return jd


def approved_jd(requisition_id: UUID) -> JobDescription | None:
    return (
        JobDescription.objects.filter(requisition_id=requisition_id, status=JobDescription.Status.APPROVED)
        .order_by("-version")
        .first()
    )


def requirements_for(requisition_id: UUID) -> list[JobRequirement]:
    jd = approved_jd(requisition_id)
    return list(jd.requirement_rows.all()) if jd else []


def templates_for(ctx: ExecutionContext, department: str = "") -> QuerySet[JDTemplate]:
    queryset = JDTemplate.objects.filter(tenant_id=ctx.tenant_id, is_active=True)
    if department:
        queryset = queryset.filter(Q(department="") | Q(department__iexact=department))
    return queryset
