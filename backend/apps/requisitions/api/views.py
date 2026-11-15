from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView, TenantViewSet
from apps.agents.api.serializers import AgentRunSerializer, StartRunIn
from apps.agents.api.views import accepted
from apps.agents.services import start as start_run
from apps.applications.api.serializers import ApplicationSerializer
from apps.applications.selectors import applications_for_requisition
from apps.integrations.services import import_applicants_csv
from apps.matching.api.serializers import AssessmentSerializer
from apps.matching.models import MatchingAssessment
from apps.matching.services import assessments_for_requisition
from apps.requisitions import selectors, services
from apps.requisitions.api.serializers import (
    CloseIn,
    CompBandSerializer,
    ImportApplicantsIn,
    ImportApplicantsOut,
    RecruiterAssignmentCreateSerializer,
    RequisitionAssignmentSerializer,
    RequisitionCreateSerializer,
    RequisitionSerializer,
    RequisitionUpdateSerializer,
)
from apps.requisitions.models import CompBand, JobRequisition

UUID_PATTERN = "[0-9a-fA-F-]{36}"


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["requisitions"])
class RequisitionViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    """HTTP only: validate input, call a service, serialise the result."""

    serializer_class = RequisitionSerializer
    filterset_fields = ["status", "department"]
    lookup_value_regex = UUID_PATTERN

    def get_queryset(self) -> QuerySet[JobRequisition]:
        if self.is_schema_request:
            return JobRequisition.objects.none()
        return selectors.visible_requisitions(self.ctx)

    def _out(self, requisition_id: UUID) -> RequisitionSerializer:
        return RequisitionSerializer(selectors.get_visible_requisition(self.ctx, requisition_id))

    @extend_schema(request=RequisitionCreateSerializer, responses={201: RequisitionSerializer})
    def create(self, request: Request) -> Response:
        payload = RequisitionCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        created = services.create_requisition(self.ctx, **payload.validated_data)
        return Response(self._out(created.pk).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RequisitionUpdateSerializer, responses=RequisitionSerializer)
    def partial_update(self, request: Request, pk: str) -> Response:
        payload = RequisitionUpdateSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        services.update_requisition(self.ctx, requisition_id=UUID(pk), **payload.validated_data)
        return Response(self._out(UUID(pk)).data)

    @extend_schema(request=None, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str) -> Response:
        services.submit_requisition(self.ctx, requisition_id=UUID(pk))
        return Response(self._out(UUID(pk)).data)

    @extend_schema(request=CloseIn, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str) -> Response:
        payload = CloseIn(data=request.data)
        payload.is_valid(raise_exception=True)
        services.close_requisition(self.ctx, requisition_id=UUID(pk), reason=payload.validated_data["reason"])
        return Response(self._out(UUID(pk)).data)

    @extend_schema(request=RecruiterAssignmentCreateSerializer, responses={201: RequisitionAssignmentSerializer})
    @action(detail=True, methods=["post"], url_path="assignments")
    def assign_recruiter(self, request: Request, pk: str) -> Response:
        payload = RecruiterAssignmentCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assignment = services.assign_recruiter(
            self.ctx, requisition_id=UUID(pk), recruiter_id=payload.validated_data["recruiter_id"]
        )
        return Response(RequisitionAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    # --- agent runs started from a requisition (all return 202 + the queued run) ---

    def _start(self, kind: str, pk: str, **extra: object) -> Response:
        payload = StartRunIn(data=self.request.data)
        payload.is_valid(raise_exception=True)
        return accepted(
            start_run(self.ctx, kind=kind, params={"requisition_id": pk, **payload.validated_data, **extra})
        )

    @extend_schema(request=StartRunIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="review-runs", throttle_scope="agent_runs")
    def review_runs(self, request: Request, pk: str) -> Response:
        return self._start("requisition_review", pk)

    @extend_schema(request=StartRunIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="jd-drafts", throttle_scope="agent_runs")
    def jd_drafts(self, request: Request, pk: str) -> Response:
        return self._start("jd_generation", pk)

    @extend_schema(request=StartRunIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="match-runs", throttle_scope="agent_runs")
    def match_runs(self, request: Request, pk: str) -> Response:
        return self._start("matching", pk)

    @extend_schema(request=StartRunIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="sourcing-runs", throttle_scope="agent_runs")
    def sourcing_runs(self, request: Request, pk: str) -> Response:
        return self._start("sourcing", pk)

    # --- reads scoped to one requisition ---

    @extend_schema(responses=AssessmentSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def assessments(self, request: Request, pk: str) -> Response:
        selectors.get_visible_requisition(self.ctx, UUID(pk))
        latest: dict[UUID, MatchingAssessment] = {}
        for assessment in assessments_for_requisition(self.ctx, UUID(pk)).order_by("application_id", "-created_at"):
            latest.setdefault(assessment.application_id, assessment)
        return Response(AssessmentSerializer(list(latest.values()), many=True).data)

    @extend_schema(responses=ApplicationSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def applications(self, request: Request, pk: str) -> Response:
        selectors.get_visible_requisition(self.ctx, UUID(pk))
        queryset = applications_for_requisition(self.ctx, UUID(pk)).order_by("-created_at")
        return Response(ApplicationSerializer(queryset, many=True, context={"ctx": self.ctx}).data)

    @extend_schema(request=ImportApplicantsIn, responses=ImportApplicantsOut)
    @action(detail=True, methods=["post"], url_path="import-applicants")
    def import_applicants(self, request: Request, pk: str) -> Response:
        payload = ImportApplicantsIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return Response(
            import_applicants_csv(self.ctx, requisition_id=UUID(pk), csv_text=payload.validated_data["csv"])
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["requisitions"])
class CompBandViewSet(TenantViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    serializer_class = CompBandSerializer

    def get_queryset(self) -> QuerySet[CompBand]:
        if self.is_schema_request:
            return CompBand.objects.none()
        return selectors.comp_bands(self.ctx)

    @extend_schema(request=CompBandSerializer, responses={201: CompBandSerializer})
    def create(self, request: Request) -> Response:
        payload = CompBandSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        band = services.create_comp_band(self.ctx, **payload.validated_data)
        return Response(CompBandSerializer(band).data, status=status.HTTP_201_CREATED)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["requisitions"])
class DepartmentsView(TenantAPIView):
    @extend_schema(responses={200: {"type": "array", "items": {"type": "string"}}})
    def get(self, request: Request) -> Response:
        return Response(selectors.departments(self.ctx))
