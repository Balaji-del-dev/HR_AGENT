"""Email drafts, approval and idempotent sending. The recipient always comes from the database."""

import hashlib
import logging
from typing import Any
from uuid import UUID, uuid4

from django.core.mail import EmailMessage as DjangoEmail
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from jinja2.sandbox import SandboxedEnvironment

from apps.accounts.roles import Role
from apps.applications.selectors import visible_applications
from apps.approvals.models import ApprovalDecision, ApprovalRequest
from apps.candidates.selectors import get_visible_candidate
from apps.communications.models import EmailDraft, EmailMessage, EmailTemplate
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tasks import enqueue_on_commit
from apps.core.tenancy import require_active_tenant
from apps.governance.services import record_audit
from policies.engine import decide as policy_decide

logger = logging.getLogger(__name__)
_jinja = SandboxedEnvironment(autoescape=False)


def render(text: str, context: dict[str, Any]) -> str:
    return _jinja.from_string(text).render(**context)


def visible_drafts(ctx: ExecutionContext) -> QuerySet[EmailDraft]:
    from apps.candidates.selectors import visible_candidates

    return EmailDraft.objects.filter(tenant_id=ctx.tenant_id, candidate__in=visible_candidates(ctx).values("pk"))


def get_visible_draft(ctx: ExecutionContext, draft_id: UUID, *, for_update: bool = False) -> EmailDraft:
    queryset = visible_drafts(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    draft = queryset.filter(pk=draft_id).first()
    if draft is None:
        raise NotFound("Email draft not found.")
    return draft


def recipient_check(ctx: ExecutionContext, *, candidate_id: UUID, application_id: UUID | None) -> dict[str, Any]:
    """Resource document for the 'emails go only to candidates on this requisition' policy."""
    applications = visible_applications(ctx).filter(candidate_id=candidate_id)
    if application_id is not None:
        applications = applications.filter(pk=application_id)
    return {"candidate_on_visible_requisition": applications.exists()}


def create_email_draft(
    ctx: ExecutionContext,
    *,
    candidate_id: UUID,
    kind: str,
    subject: str,
    body: str,
    application_id: UUID | None = None,
    interview_id: UUID | None = None,
    template_id: UUID | None = None,
    run_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> EmailDraft:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins draft candidate emails.")
    candidate = get_visible_candidate(ctx, candidate_id)
    verdict = policy_decide(
        "tool:create_email_draft", ctx, recipient_check(ctx, candidate_id=candidate.id, application_id=application_id)
    )
    if not verdict.allowed:
        raise PolicyDenied(verdict.reason)
    if not candidate.email:
        raise ApplicationError("This candidate has no email address on file.")
    if kind not in EmailTemplate.Kind.values:
        raise ApplicationError("Unknown email kind.")
    key = idempotency_key or hashlib.sha256(f"{run_id or uuid4()}:{candidate.id}:{kind}".encode()).hexdigest()[:64]
    try:
        with transaction.atomic():
            draft = EmailDraft.objects.create(
                candidate=candidate,
                application_id=application_id,
                interview_id=interview_id,
                kind=kind,
                to_email=candidate.email,
                subject=subject[:200],
                body=body,
                template_id=template_id,
                idempotency_key=key,
                created_by_id=ctx.user_id,
                agent_run_id=run_id,
            )
    except IntegrityError:
        draft = EmailDraft.objects.get(idempotency_key=key)
        if draft.candidate_id != candidate.id:
            raise ApplicationError("Idempotency key reused for another candidate.") from None
        return draft
    record_audit(
        ctx,
        action="email.drafted",
        target_type="email_draft",
        target_id=draft.id,
        run_id=run_id,
        details={"kind": kind},
    )
    return draft


def submit_draft_for_approval(
    ctx: ExecutionContext, *, draft_id: UUID, run_id: UUID | None = None, review_round: int = 1
) -> ApprovalRequest:
    from apps.approvals.services import open_request

    require_active_tenant(ctx.tenant_id)
    with transaction.atomic():
        draft = get_visible_draft(ctx, draft_id, for_update=True)
        if draft.status != EmailDraft.Status.DRAFT:
            raise InvalidStateTransition("Only drafts can be sent for approval.")
        draft.status = EmailDraft.Status.PENDING_APPROVAL
        draft.save(update_fields=["status", "updated_at"])
        requisition_id = draft.application.requisition_id if draft.application else None
        return open_request(
            ctx,
            kind=ApprovalRequest.Kind.EMAIL,
            target_id=draft.id,
            title=f"Approve {draft.get_kind_display().lower()} email to {draft.candidate.full_name}",
            summary=draft.subject,
            payload={
                "email_draft_id": str(draft.id),
                "to": draft.to_email,
                "subject": draft.subject,
                "body": draft.body,
                "kind": draft.kind,
                "candidate_id": str(draft.candidate_id),
            },
            required_roles=[Role.RECRUITER, Role.HR_ADMIN],
            requisition_id=requisition_id,
            agent_run_id=run_id,
            review_round=review_round,
        )


def approve_draft(ctx: ExecutionContext, *, draft_id: UUID, edits: dict[str, Any] | None = None) -> EmailDraft:
    """Mark a draft approved (applying a person's edits) and queue the send after commit."""
    from apps.communications.tasks import send_approved_email

    draft = EmailDraft.objects.select_for_update().get(pk=draft_id)
    if draft.status in (EmailDraft.Status.APPROVED, EmailDraft.Status.SENT):
        return draft
    if draft.status not in (EmailDraft.Status.DRAFT, EmailDraft.Status.PENDING_APPROVAL):
        raise InvalidStateTransition(f"This draft is {draft.status}.")
    edits = edits or {}
    if "subject" in edits:
        draft.subject = str(edits["subject"])[:200]
    if "body" in edits:
        draft.body = str(edits["body"])
    draft.status = EmailDraft.Status.APPROVED
    draft.approved_by_id = ctx.user_id
    draft.approved_at = timezone.now()
    draft.save()
    enqueue_on_commit(send_approved_email, ctx, draft_id=str(draft.id))
    return draft


def on_email_decided(ctx: ExecutionContext, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
    if decision.decision == ApprovalDecision.Decision.APPROVE:
        approve_draft(ctx, draft_id=request.target_id, edits=decision.edits)
    else:
        EmailDraft.objects.filter(pk=request.target_id).update(status=EmailDraft.Status.REJECTED)
    return True


def send_draft_system(*, draft_id: UUID) -> EmailMessage | None:
    """Send an approved draft exactly once. Called by the integrations worker in tenant scope."""
    with transaction.atomic():
        draft = EmailDraft.objects.select_for_update().filter(pk=draft_id).first()
        if draft is None:
            return None
        existing = EmailMessage.objects.filter(draft=draft).first()
        if existing is not None:
            return existing  # a retry or a second resume never sends twice
        if draft.status != EmailDraft.Status.APPROVED:
            raise InvalidStateTransition(f"Draft {draft_id} is {draft.status}, not approved.")
        DjangoEmail(
            subject=draft.subject,
            body=draft.body,
            to=[draft.to_email],
            headers={"X-Idempotency-Key": draft.idempotency_key},
        ).send()
        message = EmailMessage.objects.create(
            draft=draft,
            to_email=draft.to_email,
            subject=draft.subject,
            body=draft.body,
            sent_at=timezone.now(),
            provider="django_mail",
        )
        draft.status = EmailDraft.Status.SENT
        draft.save(update_fields=["status", "updated_at"])
        record_audit(None, action="email.sent", target_type="email_draft", target_id=draft.id)
    return message


def create_template(ctx: ExecutionContext, *, key: str, name: str, kind: str, subject: str, body: str) -> EmailTemplate:
    require_active_tenant(ctx.tenant_id)
    if not ctx.has_role(Role.HR_ADMIN):
        raise PolicyDenied("Only HR admins manage email templates.")
    render(subject, {})  # syntax check
    render(body, {})
    return EmailTemplate.objects.create(key=key, name=name, kind=kind, subject=subject, body=body)
