from celery import shared_task

from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope


@shared_task
def sync_all_connections() -> int:
    """Beat job: sync every active ATS connection, one tenant scope at a time."""
    from apps.integrations.models import IntegrationConnection
    from apps.integrations.services import sync_connection

    count = 0
    for tenant_id in Tenant.objects.filter(is_active=True).values_list("id", flat=True):
        with tenant_scope(tenant_id):
            for connection in IntegrationConnection.objects.filter(kind="ats", is_active=True):
                sync_connection(connection)
                count += 1
    return count
