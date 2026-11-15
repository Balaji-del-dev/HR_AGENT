from uuid import UUID

from celery import shared_task

from apps.core.tenancy import tenant_scope


@shared_task(acks_late=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def send_approved_email(*, draft_id: str, tenant_id: str) -> str:
    """Integrations queue. Idempotent: the one-to-one EmailMessage row is the send record."""
    from apps.communications.models import EmailDraft
    from apps.communications.services import send_draft_system

    try:
        with tenant_scope(tenant_id):
            message = send_draft_system(draft_id=UUID(draft_id))
    except OSError as exc:
        with tenant_scope(tenant_id):
            EmailDraft.objects.filter(pk=draft_id).update(error=str(exc)[:2000])
        raise
    return "sent" if message else "missing"
