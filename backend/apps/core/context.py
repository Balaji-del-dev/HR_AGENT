"""The caller's identity for one unit of work."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Who is acting, for which tenant, and with which roles.

    Built on the server side, from the authenticated user and their tenant
    membership, and passed to every service call. Agent tools receive the
    same object as LangGraph runtime context. The model never sees it and
    cannot change it.
    """

    user_id: UUID
    tenant_id: UUID
    roles: frozenset[str]
    request_id: str | None = None
    run_id: UUID | None = None  # set when an agent run acts on the user's behalf

    def has_role(self, *roles: str) -> bool:
        return not self.roles.isdisjoint(roles)
