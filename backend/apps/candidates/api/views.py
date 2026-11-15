from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView, TenantViewSet
from apps.candidates import selectors, services
from apps.candidates.api.serializers import (
    CandidateCreateIn,
    CandidateDetailSerializer,
    CandidateSerializer,
    ConsentIn,
    ConsentSerializer,
    FactCorrectionIn,
    ReviewQueueOut,
    UploadUrlIn,
    UploadUrlOut,
)
from apps.candidates.models import Candidate
from apps.documents.services import request_upload
from apps.governance.services import log_data_access

UUID_PATTERN = "[0-9a-fA-F-]{36}"


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["candidates"])
class CandidateViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    filterset_fields = ["source", "in_talent_pool"]
    lookup_value_regex = UUID_PATTERN

    def get_queryset(self) -> QuerySet[Candidate]:
        if self.is_schema_request:
            return Candidate.objects.none()
        queryset = selectors.visible_candidates(self.ctx)
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(full_name__icontains=query) | Q(skills__name__iexact=query)).distinct()
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                "consents", "skills", "experience", "education", "certifications", "documents"
            ).select_related("profile")
        return queryset

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        return CandidateDetailSerializer if self.action == "retrieve" else CandidateSerializer

    @extend_schema(parameters=[OpenApiParameter("q", str, description="Name or exact skill")])
    def list(self, request: Request) -> Response:
        return super().list(request)

    def retrieve(self, request: Request, pk: str) -> Response:
        response = super().retrieve(request, pk=pk)
        log_data_access(self.ctx, action="view", target_type="candidate", target_id=pk)
        return response

    @extend_schema(request=CandidateCreateIn, responses={201: CandidateSerializer})
    def create(self, request: Request) -> Response:
        payload = CandidateCreateIn(data=request.data)
        payload.is_valid(raise_exception=True)
        candidate = services.create_candidate(self.ctx, **payload.validated_data)
        return Response(CandidateSerializer(candidate, context={"ctx": self.ctx}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ConsentIn, responses=ConsentSerializer)
    @action(detail=True, methods=["post"])
    def consents(self, request: Request, pk: str) -> Response:
        payload = ConsentIn(data=request.data)
        payload.is_valid(raise_exception=True)
        consent = services.set_consent(self.ctx, candidate_id=UUID(pk), **payload.validated_data)
        return Response(ConsentSerializer(consent).data)

    @extend_schema(request=UploadUrlIn, responses={201: UploadUrlOut})
    @action(detail=True, methods=["post"], url_path="documents/upload-url")
    def upload_url(self, request: Request, pk: str) -> Response:
        payload = UploadUrlIn(data=request.data)
        payload.is_valid(raise_exception=True)
        document, link = request_upload(self.ctx, candidate_id=UUID(pk), **payload.validated_data)
        return Response(
            {"document_id": document.id, "upload_url": link.url, "expires_in": link.expires_in},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["candidates"])
class ReviewQueueView(TenantAPIView):
    """Low-confidence extracted facts for recruiters to confirm or correct."""

    @extend_schema(responses=ReviewQueueOut)
    def get(self, request: Request) -> Response:
        return Response(ReviewQueueOut(selectors.review_queue(self.ctx)).data)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["candidates"])
class FactCorrectionView(TenantAPIView):
    @extend_schema(
        request=FactCorrectionIn,
        responses=inline_serializer(
            "FactCorrectionOut", {"id": serializers.UUIDField(), "needs_review": serializers.BooleanField()}
        ),
    )
    def patch(self, request: Request, fact_type: str, fact_id: UUID) -> Response:
        payload = FactCorrectionIn(data=request.data)
        payload.is_valid(raise_exception=True)
        fact = services.correct_fact(
            self.ctx, fact_type=fact_type, fact_id=fact_id, changes=payload.validated_data["changes"]
        )
        return Response({"id": str(fact.id), "needs_review": fact.needs_review})
