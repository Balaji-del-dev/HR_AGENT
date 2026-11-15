from uuid import UUID

from django.db.models import Exists, OuterRef, Q, QuerySet

from apps.accounts.roles import Role
from apps.applications.models import JobApplication
from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound
from apps.interviews.models import InterviewPanelist
from apps.requisitions.selectors import visible_requisitions


def visible_applications(ctx: ExecutionContext) -> QuerySet[JobApplication]:
    """Applications on requisitions the caller can see, plus interviews they sit on."""
    queryset = JobApplication.objects.filter(tenant_id=ctx.tenant_id)
    if ctx.has_role(Role.HR_ADMIN):
        return queryset
    on_panel = InterviewPanelist.objects.filter(interview__application_id=OuterRef("pk"), user_id=ctx.user_id)
    condition = Q(Exists(on_panel))
    if ctx.has_role(Role.RECRUITER, Role.HIRING_MANAGER):
        condition |= Q(requisition__in=visible_requisitions(ctx).values("pk"))
    return queryset.filter(condition)


def get_visible_application(ctx: ExecutionContext, application_id: UUID, *, for_update: bool = False) -> JobApplication:
    queryset = visible_applications(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    application = queryset.select_related("candidate", "requisition").filter(pk=application_id).first()
    if application is None:
        raise NotFound("Application not found.")
    return application


def applications_for_requisition(ctx: ExecutionContext, requisition_id: UUID) -> QuerySet[JobApplication]:
    return visible_applications(ctx).filter(requisition_id=requisition_id).select_related("candidate")
