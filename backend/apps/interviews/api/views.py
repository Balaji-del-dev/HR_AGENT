from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.agents.api.serializers import AgentRunSerializer
from apps.agents.api.views import accepted
from apps.agents.services import start as start_run
from apps.interviews import services
from apps.interviews.api.serializers import InterviewCreateIn, InterviewSerializer, ScorecardIn, ScorecardSerializer
from apps.interviews.models import Interview


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["interviews"])
class InterviewViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = InterviewSerializer
    filterset_fields = ["application", "status"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[Interview]:
        if self.is_schema_request:
            return Interview.objects.none()
        queryset = services.visible_interviews(self.ctx).select_related(
            "application__candidate", "application__requisition"
        )
        if self.request.query_params.get("mine") == "true":
            queryset = queryset.filter(panel__user_id=self.ctx.user_id)
        return queryset.order_by("scheduled_start", "created_at")

    @extend_schema(parameters=[OpenApiParameter("mine", bool, required=False, description="Only interviews I sit on")])
    def list(self, request: Request) -> Response:
        return super().list(request)

    @extend_schema(request=InterviewCreateIn, responses={201: InterviewSerializer})
    def create(self, request: Request) -> Response:
        payload = InterviewCreateIn(data=request.data)
        payload.is_valid(raise_exception=True)
        interview = services.create_interview(self.ctx, **payload.validated_data)
        return Response(
            InterviewSerializer(services.get_visible_interview(self.ctx, interview.id)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], url_path="schedule-runs", throttle_scope="agent_runs")
    def schedule_runs(self, request: Request, pk: str) -> Response:
        return accepted(start_run(self.ctx, kind="scheduling", params={"interview_id": pk}))

    @extend_schema(request=ScorecardIn, responses={201: ScorecardSerializer})
    @action(detail=True, methods=["post"])
    def scorecards(self, request: Request, pk: str) -> Response:
        payload = ScorecardIn(data=request.data)
        payload.is_valid(raise_exception=True)
        card = services.submit_scorecard(self.ctx, interview_id=UUID(pk), **payload.validated_data)
        return Response(ScorecardSerializer(card).data, status=status.HTTP_201_CREATED)


router = SimpleRouter()
router.register("interviews", InterviewViewSet, basename="interview")
urlpatterns = router.urls
