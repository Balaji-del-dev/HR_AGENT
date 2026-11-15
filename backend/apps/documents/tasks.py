"""The resume pipeline, steps 2-11, on the documents queue.

Database work happens in short tenant-scoped transactions; extraction, OCR and
embedding run between them, so no transaction stays open while CPU-heavy or
network work happens.
"""

import logging
from typing import Any
from uuid import UUID

from celery import shared_task
from django.conf import settings

from apps.core.tenancy import tenant_scope
from apps.documents.models import CandidateDocument
from apps.documents.storage import QUARANTINE, get_storage
from document_ai.extraction import extract
from document_ai.injection import scan_for_injection
from document_ai.masking import Identity, make_masker
from document_ai.segmentation import chunk, segment
from document_ai.validation import FileInfected, FileRejected, scan_for_malware, validate_file

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, max_retries=2, default_retry_delay=30)
def process_document(*, document_id: str, tenant_id: str) -> str:
    from apps.governance.services import record_audit, report_incident

    with tenant_scope(tenant_id):
        document = CandidateDocument.objects.select_related("candidate").get(pk=document_id)
        if document.status != CandidateDocument.Status.PROCESSING:
            return f"skipped ({document.status})"
        candidate = document.candidate
        identity = Identity(full_name=candidate.full_name, email=candidate.email, phone=candidate.phone)
        allow_terms = _requisition_terms(candidate.id)
        data = get_storage().get(QUARANTINE, document.storage_key)

    try:
        check = validate_file(data, max_bytes=settings.DOCUMENT_MAX_BYTES)
        scan_for_malware(data, clamd_socket=settings.CLAMAV_SOCKET)
        extracted = extract(data, check.content_type, max_pages=settings.DOCUMENT_MAX_PAGES)
    except FileInfected as exc:
        with tenant_scope(tenant_id):
            document = CandidateDocument.objects.get(pk=document_id)
            _fail(document, CandidateDocument.Status.QUARANTINED, f"Failed the malware scan: {exc}")
            report_incident(
                kind="security",
                severity="high",
                title="Resume failed malware scan",
                description=f"Document {document_id}: {exc}",
                reported_by_id=document.uploaded_by_id,
            )
        return "quarantined"
    except FileRejected as exc:
        with tenant_scope(tenant_id):
            _fail(CandidateDocument.objects.get(pk=document_id), CandidateDocument.Status.REJECTED, str(exc))
        return "rejected"

    try:
        spans, chunks, flags, injection = _build(document, extracted.pages, identity, allow_terms)
        embeddings, model_name = _embed([c["content_masked"] for c in chunks])
        for item, vector in zip(chunks, embeddings, strict=True):
            item["embedding"] = vector
            item["embedding_model"] = model_name if vector is not None else ""
    except Exception as exc:
        logger.exception("resume pipeline failed", extra={"document_id": document_id})
        with tenant_scope(tenant_id):
            _fail(
                CandidateDocument.objects.get(pk=document_id),
                CandidateDocument.Status.FAILED,
                f"Processing failed: {exc}",
            )
        raise

    from apps.documents.services import record_spans_and_chunks

    with tenant_scope(tenant_id):
        document = CandidateDocument.objects.select_for_update().get(pk=document_id)
        record_spans_and_chunks(
            document=document,
            spans=spans,
            chunks=chunks,
            page_count=extracted.page_count,
            ocr_used=extracted.ocr_used,
            flags=extracted.flags + flags,
            injection_suspected=injection,
            detected_type=check.content_type,
        )
        record_audit(
            None,
            action="document.processed",
            target_type="document",
            target_id=document.id,
            details={"spans": len(spans), "chunks": len(chunks), "injection_suspected": injection},
        )
        _notify(document, "document.processed")
        _start_parsing(document)
    return "processed"


def _requisition_terms(candidate_id: UUID) -> frozenset[str]:
    from apps.jobs.models import JobRequirement

    names = JobRequirement.objects.filter(requisition__applications__candidate_id=candidate_id).values_list(
        "name", flat=True
    )
    return frozenset(name.lower() for name in names)


def _build(
    document: CandidateDocument, pages: list[str], identity: Identity, allow_terms: frozenset[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], bool]:
    masker = make_masker(identity, backend=settings.PII_MASKER, allow_terms=allow_terms)
    raw_spans = segment(document.short_id, pages)
    spans: list[dict[str, Any]] = []
    masked: dict[str, str] = {}
    injection = False
    flags: list[str] = []
    for position, span in enumerate(raw_spans):
        result = masker.mask(span.text, span.section)
        span_flags = []
        if result.withheld:
            span_flags.append("withheld_protected_attribute")
        findings = scan_for_injection(span.text)
        if findings:
            injection = True
            span_flags.append("possible_prompt_injection")
            flags.append(f"{span.span_id}: text reads like instructions to a model ({findings[0].label})")
        masked[span.span_id] = result.text
        spans.append(
            {
                "span_id": span.span_id,
                "page": span.page,
                "start": span.start,
                "end": span.end,
                "section": span.section,
                "text": span.text,
                "text_masked": result.text,
                "flags": span_flags,
                "position": position,
            }
        )
    chunks = [
        {
            "section": c.section,
            "span_ids": list(c.span_ids),
            "content_masked": "\n".join(masked[span_id] for span_id in c.span_ids),
            "position": position,
        }
        for position, c in enumerate(chunk(raw_spans, masked))
    ]
    return spans, chunks, flags, injection


def _embed(texts: list[str]) -> tuple[list[list[float] | None], str]:
    """Embedding is non-fatal: without it, evidence search falls back to lexical matching."""
    from agent_engine.llm.embeddings import get_embedder

    if not texts:
        return [], ""
    try:
        embedder = get_embedder()
        return list(embedder.embed_documents(texts)), embedder.model_name
    except Exception:
        logger.warning("embedding failed; chunks stored without vectors", exc_info=True)
        return [None] * len(texts), ""


def _fail(document: CandidateDocument, status: str, error: str) -> None:
    from apps.documents.services import mark_failed

    mark_failed(document, status=status, error=error)
    _notify(document, f"document.{status}")


def _notify(document: CandidateDocument, event_type: str) -> None:
    from apps.core.realtime import notify_users

    if document.uploaded_by_id:
        notify_users(
            [document.uploaded_by_id],
            {
                "type": event_type,
                "document_id": str(document.id),
                "candidate_id": str(document.candidate_id),
                "status": document.status,
            },
        )


def _start_parsing(document: CandidateDocument) -> None:
    """Step 8 onwards: the Resume Parsing Agent runs as the uploader."""
    from agent_engine.runtime import start_run_for_user

    if document.uploaded_by_id is None or document.kind != CandidateDocument.Kind.RESUME:
        return
    start_run_for_user(
        user_id=document.uploaded_by_id,
        tenant_id=document.tenant_id,
        kind="resume_parsing",
        payload={"document_id": str(document.id), "candidate_id": str(document.candidate_id)},
    )
