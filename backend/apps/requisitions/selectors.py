"""Tenant-scoped reads. The explicit tenant filter is the first fence; RLS is the second."""

from uuid import UUID

from django.db.models import QuerySet

from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound
from apps.requisitions import policies
from apps.requisitions.models import CompBand, JobRequisition


def visible_requisitions(ctx: ExecutionContext) -> QuerySet[JobRequisition]:
    queryset = JobRequisition.objects.filter(tenant_id=ctx.tenant_id)
    visible = policies.visibility_filter(ctx)
    if visible is not None:
        queryset = queryset.filter(visible)
    return queryset.prefetch_related("assignments")


def get_visible_requisition(ctx: ExecutionContext, requisition_id: UUID, *, for_update: bool = False) -> JobRequisition:
    """One requisition the caller may see. Missing and hidden look the same (404)."""
    queryset = visible_requisitions(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    requisition = queryset.filter(pk=requisition_id).first()
    if requisition is None:
        raise NotFound("Requisition not found.")
    return requisition


def comp_bands(ctx: ExecutionContext) -> QuerySet[CompBand]:
    return CompBand.objects.filter(tenant_id=ctx.tenant_id, is_active=True)


def departments(ctx: ExecutionContext) -> list[str]:
    from_bands = comp_bands(ctx).values_list("department", flat=True)
    from_requisitions = JobRequisition.objects.filter(tenant_id=ctx.tenant_id).values_list("department", flat=True)
    return sorted(set(from_bands) | set(from_requisitions))
