import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.accounts.roles import Role


class User(AbstractUser):
    """A person who signs in. Platform-level: one user can belong to several tenants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    # The identity provider's `sub` claim, filled on first OIDC sign-in.
    oidc_subject = models.CharField(max_length=255, unique=True, null=True, blank=True)


class Membership(models.Model):
    """A user's roles inside one tenant.

    Not under Row-Level Security: it is what the request reads to decide which
    tenant to activate. Read it only through apps.accounts.selectors.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    roles = ArrayField(models.CharField(max_length=32, choices=Role.choices), default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="membership_unique_tenant_user"),
            models.CheckConstraint(condition=Q(roles__contained_by=Role.values), name="membership_roles_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.tenant}"
