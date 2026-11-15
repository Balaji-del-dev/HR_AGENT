"""Uploads, the resume pipeline's database writes, and short-lived download links."""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import Role
from apps.candidates.selectors import get_visible_candidate
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError, InvalidStateTransition, NotFound, PolicyDenied
from apps.core.tasks import enqueue_on_commit
from apps.core.tenancy import require_active_tenant
from apps.documents.models import CandidateDocument, DocumentSpan, ResumeChunk
from apps.documents.selectors import get_visible_document
from apps.documents.storage import DOCUMENTS, QUARANTINE, document_key, get_storage
from apps.governance.services import log_data_access, record_audit

logger = logging.getLogger(__name__)

UPLOAD_SALT = "documents.upload"
DOWNLOAD_SALT = "documents.download"
ALLOWED_EXTENSIONS = (".pdf", ".docx")


@dataclass(frozen=True, slots=True)
class SignedLink:
    url: str
    expires_in: int


def _require_recruiter(ctx: ExecutionContext) -> None:
    if not ctx.has_role(Role.HR_ADMIN, Role.RECRUITER):
        raise PolicyDenied("Only recruiters and HR admins handle resumes.")


def request_upload(
    ctx: ExecutionContext, *, candidate_id: UUID, filename: str, content_type: str = "", size_bytes: int = 0
) -> tuple[CandidateDocument, SignedLink]:
    """Step 1: record the document and hand back a short-lived upload link (like a presigned URL)."""
    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise ApplicationError("Only PDF and DOCX resumes are accepted.", details={"filename": ["Use .pdf or .docx."]})
    if size_bytes and size_bytes > settings.DOCUMENT_MAX_BYTES:
        raise ApplicationError("The file is too large.", details={"size_bytes": ["Too large."]})
    candidate = get_visible_candidate(ctx, candidate_id)
    if candidate.is_anonymized:
        raise InvalidStateTransition("This candidate's data was erased.")
    document = CandidateDocument(
        candidate=candidate,
        original_name=filename[:255],
        declared_content_type=content_type[:120],
        uploaded_by_id=ctx.user_id,
    )
    document.storage_key = document_key(ctx.tenant_id, candidate.id, document.id)
    document.save()
    token = signing.dumps(
        {"d": str(document.id), "t": str(ctx.tenant_id), "u": str(ctx.user_id)}, salt=UPLOAD_SALT, compress=True
    )
    record_audit(ctx, action="document.upload_requested", target_type="document", target_id=document.id)
    return document, SignedLink(url=f"/api/v1/uploads/{token}/", expires_in=settings.SIGNED_URL_MAX_AGE)


def _read_token(token: str, *, salt: str, ctx: ExecutionContext) -> UUID:
    try:
        payload = signing.loads(token, salt=salt, max_age=settings.SIGNED_URL_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise PolicyDenied("This link has expired.") from exc
    except signing.BadSignature as exc:
        raise NotFound("Link not found.") from exc
    if payload.get("t") != str(ctx.tenant_id) or payload.get("u") != str(ctx.user_id):
        raise NotFound("Link not found.")
    return UUID(payload["d"])


def receive_upload(ctx: ExecutionContext, *, token: str, data: bytes) -> CandidateDocument:
    """The upload link: store the bytes in the quarantine bucket. Nothing reads them until scanned."""
    require_active_tenant(ctx.tenant_id)
    document_id = _read_token(token, salt=UPLOAD_SALT, ctx=ctx)
    if len(data) > settings.DOCUMENT_MAX_BYTES:
        raise ApplicationError("The file is too large.")
    with transaction.atomic():
        document = get_visible_document(ctx, document_id, for_update=True)
        if document.status != CandidateDocument.Status.PENDING_UPLOAD:
            raise InvalidStateTransition("This upload link was already used.")
        get_storage().put(QUARANTINE, document.storage_key, data)
        document.size_bytes = len(data)
        document.sha256 = hashlib.sha256(data).hexdigest()
        document.bucket = QUARANTINE
        document.status = CandidateDocument.Status.UPLOADED
        document.save(update_fields=["size_bytes", "sha256", "bucket", "status", "updated_at"])
    return document


def complete_upload(ctx: ExecutionContext, *, document_id: UUID) -> CandidateDocument:
    """Confirm the upload and start the resume pipeline on the documents queue."""
    from apps.documents.tasks import process_document

    require_active_tenant(ctx.tenant_id)
    _require_recruiter(ctx)
    with transaction.atomic():
        document = get_visible_document(ctx, document_id, for_update=True)
        if document.status != CandidateDocument.Status.UPLOADED:
            raise InvalidStateTransition(f"The document is {document.status}, not uploaded.")
        document.status = CandidateDocument.Status.PROCESSING
        document.save(update_fields=["status", "updated_at"])
        enqueue_on_commit(process_document, ctx, document_id=str(document.id))
        record_audit(ctx, action="document.pipeline_started", target_type="document", target_id=document.id)
    return document


def download_link(ctx: ExecutionContext, *, document_id: UUID) -> SignedLink:
    require_active_tenant(ctx.tenant_id)
    document = get_visible_document(ctx, document_id)
    if document.status != CandidateDocument.Status.PROCESSED:
        raise InvalidStateTransition("Only scanned, processed documents can be downloaded.")
    token = signing.dumps(
        {"d": str(document.id), "t": str(ctx.tenant_id), "u": str(ctx.user_id)}, salt=DOWNLOAD_SALT, compress=True
    )
    return SignedLink(url=f"/api/v1/downloads/{token}/", expires_in=settings.SIGNED_URL_MAX_AGE)


def read_download(ctx: ExecutionContext, *, token: str) -> tuple[CandidateDocument, bytes]:
    require_active_tenant(ctx.tenant_id)
    document_id = _read_token(token, salt=DOWNLOAD_SALT, ctx=ctx)
    document = get_visible_document(ctx, document_id)
    if document.status != CandidateDocument.Status.PROCESSED:
        raise NotFound("Link not found.")
    data = get_storage().get(DOCUMENTS, document.storage_key)
    log_data_access(ctx, action="download", target_type="document", target_id=document.id)
    return document, data


def record_spans_and_chunks(
    *,
    document: CandidateDocument,
    spans: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    page_count: int,
    ocr_used: bool,
    flags: list[str],
    injection_suspected: bool,
    detected_type: str,
) -> None:
    """Pipeline step 10: store spans and chunks, move the file out of quarantine."""
    DocumentSpan.objects.filter(document=document).delete()
    ResumeChunk.objects.filter(document=document).delete()
    DocumentSpan.objects.bulk_create(
        [DocumentSpan(tenant_id=document.tenant_id, document=document, **span) for span in spans]
    )
    ResumeChunk.objects.bulk_create(
        [
            ResumeChunk(tenant_id=document.tenant_id, document=document, candidate_id=document.candidate_id, **c)
            for c in chunks
        ]
    )
    get_storage().move(QUARANTINE, DOCUMENTS, document.storage_key)
    document.bucket = DOCUMENTS
    document.page_count = page_count
    document.ocr_used = ocr_used
    document.sanitizer_flags = flags
    document.injection_suspected = injection_suspected
    document.detected_content_type = detected_type
    document.status = CandidateDocument.Status.PROCESSED
    document.processed_at = timezone.now()
    document.error = ""
    document.save()


def mark_failed(document: CandidateDocument, *, status: str, error: str) -> None:
    document.status = status
    document.error = error[:2000]
    document.save(update_fields=["status", "error", "updated_at"])


def delete_document_system(*, document_id: UUID) -> None:
    document = CandidateDocument.objects.filter(pk=document_id).first()
    if document is None:
        return
    storage = get_storage()
    for bucket in (QUARANTINE, DOCUMENTS):
        storage.delete(bucket, document.storage_key)
    document.delete()
