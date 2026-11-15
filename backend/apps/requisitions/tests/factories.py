from typing import Any

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.core.tenancy import tenant_scope
from apps.requisitions.models import JobRequisition, RequisitionAssignment


class _TenantScopedFactory(DjangoModelFactory[Any]):
    """Creates the row inside its tenant's scope, the way services do.

    Pass ``tenant=<Tenant>``; it is removed from the model kwargs and the
    model fills tenant_id from the active scope.
    """

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
        tenant = kwargs.pop("tenant")
        with tenant_scope(tenant.id):
            return super()._create(model_class, *args, **kwargs)


class JobRequisitionFactory(_TenantScopedFactory):
    class Meta:
        model = JobRequisition

    title = factory.Sequence(lambda n: f"Backend Engineer {n}")
    department = "Engineering"
    location = "Chennai"
    hiring_manager = factory.SubFactory(UserFactory)
    created_by = factory.SelfAttribute("hiring_manager")


class RequisitionAssignmentFactory(_TenantScopedFactory):
    class Meta:
        model = RequisitionAssignment

    user = factory.SubFactory(UserFactory)
