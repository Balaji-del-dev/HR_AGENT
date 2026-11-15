from celery import shared_task

from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope


@shared_task
def run_retention_purge() -> dict[str, dict[str, int]]:
    """Beat job: apply each tenant's retention policies inside that tenant's scope."""
    from apps.governance.services import purge_expired_data

    results = {}
    for tenant_id in Tenant.objects.filter(is_active=True).values_list("id", flat=True):
        with tenant_scope(tenant_id):
            results[str(tenant_id)] = purge_expired_data(tenant_id=tenant_id)
    return results
