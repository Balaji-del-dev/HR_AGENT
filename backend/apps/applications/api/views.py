from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.agents.api.serializers import AgentRunSerializer
from apps.agents.api.views import accepted
from apps.agents.services import start as start_run
from apps.applications import selectors, services
from apps.applications.api.serializers import (
    ApplicationCreateIn,
    ApplicationDetailSerializer,
    ApplicationSerializer,
    CommsRunIn,
    DecisionIn,
    ReasonIn,
)
from apps.applications.models import JobApplication
from apps.interviews.api.serializers import ScorecardSerializer
from apps.interviews.services import scorecards_for_application
from apps.matching.api.serializers import AssessmentSerializer, RecruiterDecisionSerializer
from apps.matching.services import latest_assessment

UUID_PATTERN = "[0-9a-fA-F-]{36}"


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["applications"])
class ApplicationViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    filterset_fields = ["requisition", "stage", "candidate"]
    lookup_value_regex = UUID_PATTERN

    def get_queryset(self) -> QuerySet[JobApplication]:
        if self.is_schema_request:
            return JobApplication.objects.none()
        return selectors.visible_applications(self.ctx).select_related("candidate", "requisition")

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        return ApplicationDetailSerializer if self.action == "retrieve" else ApplicationSerializer

    @extend_schema(request=ApplicationCreateIn, responses={201: ApplicationSerializer})
    def create(self, request: Request) -> Response:
        payload = ApplicationCreateIn(data=request.data)
        payload.is_valid(raise_exception=True)
        application = services.create_application(self.ctx, **payload.validated_data)
        return Response(
            ApplicationSerializer(selectors.get_visible_application(self.ctx, application.id)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=DecisionIn, responses={201: RecruiterDecisionSerializer})
    @action(detail=True, methods=["post"])
    def decisions(self, request: Request, pk: str) -> Response:
        payload = DecisionIn(data=request.data)
        payload.is_valid(raise_exception=True)
        decision = services.record_decision(self.ctx, application_id=UUID(pk), **payload.validated_data)
        return Response(RecruiterDecisionSerializer(decision).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReasonIn, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"])
    def withdraw(self, request: Request, pk: str) -> Response:
        payload = ReasonIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return Response(
            ApplicationSerializer(
                services.withdraw(self.ctx, application_id=UUID(pk), reason=payload.validated_data["reason"])
            ).data
        )

    @extend_schema(responses=AssessmentSerializer)
    @action(detail=True, methods=["get"])
    def assessment(self, request: Request, pk: str) -> Response:
        return Response(AssessmentSerializer(latest_assessment(self.ctx, UUID(pk))).data)

    @extend_schema(responses=ScorecardSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def scorecards(self, request: Request, pk: str) -> Response:
        return Response(ScorecardSerializer(scorecards_for_application(self.ctx, UUID(pk)), many=True).data)

    @extend_schema(request=CommsRunIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="comms-runs", throttle_scope="agent_runs")
    def comms_runs(self, request: Request, pk: str) -> Response:
        payload = CommsRunIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return accepted(
            start_run(self.ctx, kind="communication", params={"application_id": pk, **payload.validated_data})
        )

    @extend_schema(request=None, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="feedback-runs", throttle_scope="agent_runs")
    def feedback_runs(self, request: Request, pk: str) -> Response:
        return accepted(start_run(self.ctx, kind="feedback_summary", params={"application_id": pk}))

    @extend_schema(request=None, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="offer-runs", throttle_scope="agent_runs")
    def offer_runs(self, request: Request, pk: str) -> Response:
        return accepted(start_run(self.ctx, kind="offer", params={"application_id": pk}))
