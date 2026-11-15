from uuid import UUID

from django.db.models import QuerySet

from apps.accounts.models import Membership, User


def active_memberships(user_id: UUID) -> QuerySet[Membership]:
    return Membership.objects.filter(user_id=user_id, is_active=True, tenant__is_active=True)


def member_has_role(*, tenant_id: UUID, user_id: UUID, role: str) -> bool:
    """True if the user is an active member of the tenant holding ``role``."""
    return active_memberships(user_id).filter(tenant_id=tenant_id, roles__contains=[role]).exists()


def member_has_any_role(*, tenant_id: UUID, user_id: UUID, roles: list[str]) -> bool:
    return active_memberships(user_id).filter(tenant_id=tenant_id, roles__overlap=roles).exists()


def users_with_role(*, tenant_id: UUID, role: str) -> QuerySet[User]:
    return User.objects.filter(
        memberships__tenant_id=tenant_id,
        memberships__is_active=True,
        memberships__roles__contains=[role],
        is_active=True,
    ).distinct()


def tenant_members(*, tenant_id: UUID) -> QuerySet[Membership]:
    return Membership.objects.filter(tenant_id=tenant_id, is_active=True).select_related("user")
