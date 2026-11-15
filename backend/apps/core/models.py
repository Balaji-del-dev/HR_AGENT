import uuid
from typing import Any

from django.db import models

from apps.core.exceptions import TenantScopeError
from apps.core.tenancy import get_current_tenant_id


class Tenant(models.Model):
    """A customer organisation. Platform-level: not itself under Row-Level Security."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=63, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TenantScopedModel(models.Model):
    """Base class for every tenant-owned table.

    Each subclass's migration must add ``EnableRowLevelSecurity`` (see
    ``apps.core.db.operations``); ``test_every_tenant_table_has_rls`` fails
    the build if one is missing.

    ``tenant`` is filled from the active tenant on save and cannot be set to a
    different tenant. The RLS ``WITH CHECK`` clause enforces the same rule in
    the database.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        active = get_current_tenant_id()
        if active is None:
            raise TenantScopeError(f"Cannot save {type(self).__name__} with no active tenant.")
        if self.tenant_id is None:
            self.tenant_id = active
        elif self.tenant_id != active:
            raise TenantScopeError(
                f"Cannot save {type(self).__name__} for tenant {self.tenant_id} while {active} is active."
            )
        super().save(*args, **kwargs)
