from uuid import UUID

from apps.accounts.selectors import active_memberships
from apps.core.context import ExecutionContext
from apps.core.exceptions import TenantAccessDenied, TenantRequired


def build_execution_context(
    *, user_id: UUID, requested_tenant_id: UUID | None, request_id: str | None = None
) -> ExecutionContext:
    """Pick the tenant for this request and the user's roles in it.

    * With a requested tenant: the user must be an active member of it.
      A missing tenant and a tenant the user cannot access give the same
      error, so tenant ids cannot be probed.
    * Without one: use the single active membership, or ask for the header.
    """
    memberships = active_memberships(user_id)
    if requested_tenant_id is not None:
        membership = memberships.filter(tenant_id=requested_tenant_id).first()
        if membership is None:
            raise TenantAccessDenied()
    else:
        found = list(memberships[:2])
        if not found:
            raise TenantAccessDenied("You are not an active member of any tenant.")
        if len(found) > 1:
            raise TenantRequired()
        membership = found[0]

    return ExecutionContext(
        user_id=user_id,
        tenant_id=membership.tenant_id,
        roles=frozenset(membership.roles),
        request_id=request_id,
    )
