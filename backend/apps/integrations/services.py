"""Connectors: CSV import (local ATS), signed ATS webhooks, and the built-in calendar."""

import csv
import hashlib
import hmac
import io
import os
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.applications.models import JobApplication
from apps.candidates.models import Candidate
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, NotFound, PolicyDenied
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from apps.integrations.models import CalendarBusyBlock, IntegrationConnection, SyncRun, WebhookEvent
from apps.requisitions.models import JobRequisition

TRUTHY = {"yes", "y", "true", "1"}


def import_applicants_csv(ctx: ExecutionContext, *, requisition_id: UUID, csv_text: str) -> dict[str, Any]:
    """Columns: full_name, email, phone, location, consent (yes/no), talent_pool (yes/no), external_id.

    Rows without application consent are skipped: we do not store people who did not agree.
    """
    from apps.applications.services import create_application
    from apps.candidates.services import create_candidate

    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins import applicants.")
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"full_name", "email", "consent"}
    if not reader.fieldnames or not required <= {f.strip() for f in reader.fieldnames}:
        raise ApplicationError(f"The CSV needs columns {sorted(required)}.")
    stats: dict[str, Any] = {"created": 0, "existing": 0, "skipped_no_consent": 0, "errors": []}
    for line, row in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if row.get("consent", "").lower() not in TRUTHY:
            stats["skipped_no_consent"] += 1
            continue
        try:
            with transaction.atomic():
                candidate = Candidate.objects.filter(email=row["email"].lower()).first()
                if candidate is None:
                    candidate = create_candidate(
                        ctx,
                        full_name=row["full_name"],
                        email=row["email"],
                        phone=row.get("phone", ""),
                        location=row.get("location", ""),
                        source=Candidate.Source.ATS_IMPORT,
                        external_id=row.get("external_id", ""),
                        talent_pool_consent=row.get("talent_pool", "").lower() in TRUTHY,
                        consent_source="ATS import (applicant consented on the application form)",
                    )
                if JobApplication.objects.filter(requisition_id=requisition_id, candidate=candidate).exists():
                    stats["existing"] += 1
                    continue
                create_application(ctx, requisition_id=requisition_id, candidate_id=candidate.id, source="ats_import")
                stats["created"] += 1
        except ApplicationError as exc:
            stats["errors"].append({"line": line, "error": exc.message})
    record_audit(
        ctx,
        action="ats.csv_imported",
        target_type="requisition",
        target_id=requisition_id,
        details={k: v for k, v in stats.items() if k != "errors"},
    )
    return stats


def verify_signature(connection: IntegrationConnection, body: bytes, signature: str) -> bool:
    secret = os.environ.get(connection.secret_env_var, "") if connection.secret_env_var else ""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def receive_webhook(
    *, connection: IntegrationConnection, event_id: str, event_type: str, payload: dict[str, Any]
) -> WebhookEvent:
    """Store and apply an ATS event. Runs inside tenant_scope; redelivery is a no-op."""
    try:
        with transaction.atomic():
            event = WebhookEvent.objects.create(
                connection=connection, event_id=event_id[:120], event_type=event_type[:60], payload=payload
            )
    except IntegrityError:
        return WebhookEvent.objects.get(connection=connection, event_id=event_id[:120])
    try:
        with transaction.atomic():
            _apply_event(connection, event)
            event.processed = True
            event.save(update_fields=["processed", "updated_at"])
    except (ApplicationError, KeyError, ValueError) as exc:
        event.error = str(exc)[:2000]
        event.save(update_fields=["error", "updated_at"])
    return event


def _apply_event(connection: IntegrationConnection, event: WebhookEvent) -> None:
    if event.event_type != "application.created":
        return
    data = event.payload
    requisition = JobRequisition.objects.filter(
        pk=data["requisition_id"], status=JobRequisition.Status.APPROVED
    ).first()
    if requisition is None:
        raise ApplicationError("Unknown or closed requisition.")
    if str(data.get("consent", "")).lower() not in TRUTHY:
        raise ApplicationError("Applicant did not consent; not stored.")
    email = str(data["email"]).strip().lower()
    candidate = Candidate.objects.filter(email=email).first()
    if candidate is None:
        from apps.candidates.models import CandidateConsent

        candidate = Candidate.objects.create(
            full_name=str(data["full_name"])[:200],
            email=email,
            phone=str(data.get("phone", ""))[:40],
            source=Candidate.Source.ATS_IMPORT,
            external_id=str(data.get("external_id", ""))[:120],
        )
        CandidateConsent.objects.create(
            candidate=candidate,
            purpose=CandidateConsent.Purpose.APPLICATION,
            granted_at=timezone.now(),
            source=f"ATS webhook ({connection.name})",
        )
    JobApplication.objects.get_or_create(
        requisition=requisition,
        candidate=candidate,
        defaults={"source": "ats_webhook", "stage_changed_at": timezone.now()},
    )
    record_audit(
        None,
        action="ats.webhook_applied",
        target_type="requisition",
        target_id=requisition.id,
        details={"event_id": event.event_id},
    )


def sync_connection(connection: IntegrationConnection) -> SyncRun:
    """Scheduled sync. The local providers have nothing to pull; remote ATS adapters plug in here."""
    run = SyncRun.objects.create(connection=connection)
    run.status = SyncRun.Status.SUCCEEDED
    run.stats = {"pulled": 0, "provider": connection.provider}
    run.finished_at = timezone.now()
    run.save()
    connection.last_synced_at = run.finished_at
    connection.save(update_fields=["last_synced_at", "updated_at"])
    return run


def add_busy_block(
    ctx: ExecutionContext, *, user_id: UUID, start: datetime, end: datetime, title: str = "Busy"
) -> CalendarBusyBlock:
    require_active_tenant(ctx.tenant_id)
    if user_id != ctx.user_id and not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("You can only edit your own calendar.")
    if end <= start:
        raise ApplicationError("End must be after start.")
    return CalendarBusyBlock.objects.create(user_id=user_id, start=start, end=end, title=title[:200])


def delete_busy_block(ctx: ExecutionContext, *, block_id: UUID) -> None:
    require_active_tenant(ctx.tenant_id)
    block = CalendarBusyBlock.objects.filter(pk=block_id).first()
    if block is None or (block.user_id != ctx.user_id and not ctx.has_role(Role.HR_ADMIN)):
        raise NotFound("Busy block not found.")
    if block.interview_id:
        raise ApplicationError("Interview blocks are removed by cancelling the interview.")
    block.delete()
