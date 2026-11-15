import factory
from factory.django import DjangoModelFactory

from apps.core.models import Tenant


class TenantFactory(DjangoModelFactory[Tenant]):
    class Meta:
        model = Tenant
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")
