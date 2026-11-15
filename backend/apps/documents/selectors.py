from uuid import UUID

from django.db.models import QuerySet

from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound
from apps.documents.models import CandidateDocument, DocumentSpan


def visible_documents(ctx: ExecutionContext) -> QuerySet[CandidateDocument]:
    from apps.candidates.selectors import visible_candidates

    return CandidateDocument.objects.filter(tenant_id=ctx.tenant_id, candidate__in=visible_candidates(ctx).values("pk"))


def get_visible_document(ctx: ExecutionContext, document_id: UUID, *, for_update: bool = False) -> CandidateDocument:
    queryset = visible_documents(ctx)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    document = queryset.filter(pk=document_id).first()
    if document is None:
        raise NotFound("Document not found.")
    return document


def spans_for(ctx: ExecutionContext, document_id: UUID) -> QuerySet[DocumentSpan]:
    document = get_visible_document(ctx, document_id)
    return document.spans.all()


def latest_resume(candidate_id: UUID) -> CandidateDocument | None:
    return (
        CandidateDocument.objects.filter(
            candidate_id=candidate_id, kind=CandidateDocument.Kind.RESUME, status=CandidateDocument.Status.PROCESSED
        )
        .order_by("-processed_at")
        .first()
    )
