from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView
from apps.core.exceptions import ApplicationError
from apps.documents import selectors, services
from apps.documents.api.serializers import DocumentSerializer, SignedLinkOut, SpanSerializer
from apps.governance.services import log_data_access


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["documents"])
class DocumentDetailView(TenantAPIView):
    @extend_schema(responses=DocumentSerializer)
    def get(self, request: Request, document_id: UUID) -> Response:
        return Response(DocumentSerializer(selectors.get_visible_document(self.ctx, document_id)).data)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["documents"])
class DocumentCompleteView(TenantAPIView):
    """Confirm the upload and start the resume pipeline."""

    @extend_schema(request=None, responses={202: DocumentSerializer})
    def post(self, request: Request, document_id: UUID) -> Response:
        return Response(
            DocumentSerializer(services.complete_upload(self.ctx, document_id=document_id)).data, status=202
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["documents"])
class DocumentSpansView(TenantAPIView):
    @extend_schema(responses=SpanSerializer(many=True))
    def get(self, request: Request, document_id: UUID) -> Response:
        spans = selectors.spans_for(self.ctx, document_id)
        log_data_access(self.ctx, action="view", target_type="document", target_id=document_id)
        return Response(SpanSerializer(spans, many=True).data)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["documents"])
class DocumentDownloadUrlView(TenantAPIView):
    @extend_schema(request=None, responses=SignedLinkOut)
    def post(self, request: Request, document_id: UUID) -> Response:
        link = services.download_link(self.ctx, document_id=document_id)
        return Response({"url": link.url, "expires_in": link.expires_in})


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["documents"])
class UploadView(TenantAPIView):
    """The short-lived upload link. Multipart field ``file``."""

    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": inline_serializer("UploadIn", {"file": serializers.FileField()})},
        responses=DocumentSerializer,
    )
    def post(self, request: Request, token: str) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise ApplicationError("Attach the resume as the 'file' field.", details={"file": ["Required."]})
        document = services.receive_upload(self.ctx, token=token, data=upload.read())
        return Response(DocumentSerializer(document).data)


@extend_schema(
    parameters=[TENANT_HEADER_PARAMETER], tags=["documents"], responses={(200, "application/octet-stream"): bytes}
)
class DownloadView(TenantAPIView):
    def get(self, request: Request, token: str) -> HttpResponse:
        document, data = services.read_download(self.ctx, token=token)
        response = HttpResponse(data, content_type=document.detected_content_type or "application/octet-stream")
        response["Content-Disposition"] = (
            f'inline; filename="{document.id}{_extension(document.detected_content_type)}"'
        )
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def _extension(content_type: str) -> str:
    return ".pdf" if content_type == "application/pdf" else ".docx"
