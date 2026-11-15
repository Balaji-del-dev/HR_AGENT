"""Who may do what with requisitions.

Pure decisions over an ExecutionContext. Services call these and raise
PolicyDenied. When OPA arrives, these functions become the adapter that asks it.
"""

from django.db.models import Exists, OuterRef, Q

from apps.accounts.roles import Role
from apps.core.context import ExecutionContext
from apps.requisitions.models import JobRequisition, RequisitionAssignment

_AUTHORS = (Role.HR_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER)


def visibility_filter(ctx: ExecutionContext) -> Q | None:
    """Rows the caller may see within the tenant. None means all of them.

    HR admins see every requisition; anyone else sees those they manage,
    created, or are assigned to.
    """
    if ctx.has_role(Role.HR_ADMIN):
        return None
    assigned = RequisitionAssignment.objects.filter(requisition_id=OuterRef("pk"), user_id=ctx.user_id)
    return Q(hiring_manager_id=ctx.user_id) | Q(created_by_id=ctx.user_id) | Q(Exists(assigned))


def can_create(ctx: ExecutionContext) -> bool:
    return ctx.has_role(*_AUTHORS)


def can_submit(ctx: ExecutionContext, requisition: JobRequisition) -> bool:
    if ctx.has_role(Role.HR_ADMIN):
        return True
    if not ctx.has_role(*_AUTHORS):
        return False
    if ctx.user_id in (requisition.hiring_manager_id, requisition.created_by_id):
        return True
    return requisition.assignments.filter(user_id=ctx.user_id).exists()


def can_assign_recruiters(ctx: ExecutionContext) -> bool:
    return ctx.has_role(Role.HR_ADMIN)
