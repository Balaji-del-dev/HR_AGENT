"""Audit trail, access logs, data-subject requests, retention and incidents."""

import hashlib
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.core.context import ExecutionContext
from apps.core.exceptions import InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tenancy import get_current_tenant_id, require_active_tenant
from apps.governance.models import (
    AuditEvent,
    DataAccessLog,
    DeletionRequest,
    RetentionPolicy,
    SecurityIncident,
)

logger = logging.getLogger(__name__)


def record_audit(
    ctx: ExecutionContext | None,
    *,
    action: str,
    target_type: str,
    target_id: UUID | str | None = None,
    details: dict[str, Any] | None = None,
    run_id: UUID | None = None,
) -> AuditEvent:
    """Append one audit row. Needs an active tenant; pass ctx=None for system actions."""
    if ctx is not None:
        require_active_tenant(ctx.tenant_id)
    actor_type = AuditEvent.ActorType.SYSTEM
    if ctx is not None:
        actor_type = AuditEvent.ActorType.AGENT if (ctx.run_id or run_id) else AuditEvent.ActorType.USER
    return AuditEvent.objects.create(
        actor_id=ctx.user_id if ctx else None,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        run_id=run_id or (ctx.run_id if ctx else None),
        request_id=(ctx.request_id or "") if ctx else "",
        details=details or {},
    )


def log_data_access(ctx: ExecutionContext, *, action: str, target_type: str, target_id: UUID | str) -> None:
    require_active_tenant(ctx.tenant_id)
    DataAccessLog.objects.create(
        actor_id=ctx.user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        request_id=ctx.request_id or "",
    )


def candidate_reference(candidate_id: UUID) -> str:
    """A stable, non-identifying reference that survives erasure."""
    return hashlib.sha256(f"candidate:{candidate_id}".encode()).hexdigest()[:24]


def create_deletion_request(ctx: ExecutionContext, *, candidate_id: UUID, reason: str = "") -> DeletionRequest:
    from apps.candidates.selectors import get_visible_candidate

    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only HR admins and recruiters can log deletion requests.")
    candidate = get_visible_candidate(ctx, candidate_id)
    request = DeletionRequest.objects.create(
        candidate=candidate,
        candidate_ref=candidate_reference(candidate.id),
        reason=reason,
        requested_by_id=ctx.user_id,
    )
    record_audit(ctx, action="deletion_request.created", target_type="candidate", target_id=candidate.id)
    return request


def complete_deletion_request(ctx: ExecutionContext, *, request_id: UUID) -> DeletionRequest:
    """Erase the candidate's personal data. HR admins only; the request row keeps a reference."""
    from apps.candidates.services import erase_candidate

    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN):
        raise PolicyDenied("Only HR admins can complete deletion requests.")
    with transaction.atomic():
        request = DeletionRequest.objects.select_for_update().filter(pk=request_id, tenant_id=ctx.tenant_id).first()
        if request is None:
            raise NotFound("Deletion request not found.")
        if request.status != DeletionRequest.Status.PENDING:
            raise InvalidStateTransition("This deletion request is already closed.")
        if request.candidate_id is not None:
            erase_candidate(ctx, candidate_id=request.candidate_id)
        request.status = DeletionRequest.Status.COMPLETED
        request.completed_by_id = ctx.user_id
        request.completed_at = timezone.now()
        request.save(update_fields=["status", "completed_by", "completed_at", "updated_at"])
        record_audit(ctx, action="deletion_request.completed", target_type="deletion_request", target_id=request.id)
    return request


def report_incident(
    *,
    kind: str,
    title: str,
    description: str,
    severity: str = SecurityIncident.Severity.MEDIUM,
    run_id: UUID | None = None,
    reported_by_id: UUID | None = None,
) -> SecurityIncident:
    """Open an incident in the active tenant. Agents call this when a guard blocks something."""
    if get_current_tenant_id() is None:
        raise RuntimeError("report_incident needs an active tenant.")
    incident = SecurityIncident.objects.create(
        kind=kind,
        title=title[:200],
        description=description,
        severity=severity,
        run_id=run_id,
        reported_by_id=reported_by_id,
    )
    logger.warning("security incident opened", extra={"incident_id": str(incident.id), "kind": kind})
    return incident


def purge_expired_data(*, tenant_id: UUID, now: Any = None) -> dict[str, int]:
    """Apply the tenant's retention policies. Runs inside tenant_scope(tenant_id)."""
    from apps.agents.models import AgentRun
    from apps.applications.models import JobApplication
    from apps.candidates.models import Candidate
    from apps.candidates.services import erase_candidate_system
    from apps.documents.services import delete_document_system

    require_active_tenant(tenant_id)
    now = now or timezone.now()
    counts = {"candidates": 0, "documents": 0, "agent_runs": 0}
    open_stages = [
        JobApplication.Stage.APPLIED,
        JobApplication.Stage.SCREENING,
        JobApplication.Stage.SHORTLISTED,
        JobApplication.Stage.INTERVIEW,
        JobApplication.Stage.OFFER,
    ]
    for policy in RetentionPolicy.objects.filter(is_active=True):
        cutoff = now - timedelta(days=policy.retain_days)
        if policy.target == RetentionPolicy.Target.CANDIDATES:
            stale = (
                Candidate.objects.filter(is_anonymized=False, updated_at__lt=cutoff)
                .exclude(applications__stage__in=open_stages)
                .exclude(in_talent_pool=True)
                .distinct()
            )
            for candidate in stale:
                erase_candidate_system(candidate_id=candidate.id)
                counts["candidates"] += 1
        elif policy.target == RetentionPolicy.Target.DOCUMENTS:
            from apps.documents.models import CandidateDocument

            for document in CandidateDocument.objects.filter(created_at__lt=cutoff).exclude(
                candidate__applications__stage__in=open_stages
            ):
                delete_document_system(document_id=document.id)
                counts["documents"] += 1
        elif policy.target == RetentionPolicy.Target.AGENT_RUNS:
            from agent_engine.runtime import delete_checkpoints

            finished = AgentRun.objects.filter(
                finished_at__lt=cutoff,
                status__in=[AgentRun.Status.COMPLETED, AgentRun.Status.FAILED, AgentRun.Status.CANCELLED],
            )
            for run in finished:
                delete_checkpoints(run.id)
                counts["agent_runs"] += 1
            finished.delete()
    if any(counts.values()):
        record_audit(None, action="retention.purged", target_type="tenant", target_id=tenant_id, details=counts)
    return counts
