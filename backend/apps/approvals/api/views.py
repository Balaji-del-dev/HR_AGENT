from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.approvals import services
from apps.approvals.models import ApprovalDecision, ApprovalRequest


class ApprovalDecisionSerializer(serializers.ModelSerializer[ApprovalDecision]):
    decided_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ApprovalDecision
        fields = ["id", "decided_by_id", "decision", "reason", "edits", "created_at"]
        read_only_fields = fields


class ApprovalRequestSerializer(serializers.ModelSerializer[ApprovalRequest]):
    requested_by_id = serializers.UUIDField(read_only=True)
    assignee_id = serializers.UUIDField(read_only=True, allow_null=True)
    requisition_id = serializers.UUIDField(read_only=True, allow_null=True)
    agent_run_id = serializers.UUIDField(read_only=True, allow_null=True)
    decisions = ApprovalDecisionSerializer(many=True, read_only=True)
    can_decide = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id",
            "kind",
            "target_id",
            "title",
            "summary",
            "payload",
            "required_roles",
            "assignee_id",
            "requisition_id",
            "step",
            "chain_length",
            "status",
            "requested_by_id",
            "agent_run_id",
            "review_round",
            "decided_at",
            "decisions",
            "can_decide",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_can_decide(self, obj: ApprovalRequest) -> bool:
        ctx = self.context.get("ctx")
        return ctx is not None and obj.status == ApprovalRequest.Status.PENDING and services.can_decide(ctx, obj)


class DecideIn(serializers.Serializer[Any]):
    decision = serializers.ChoiceField(choices=ApprovalDecision.Decision.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
    edits = serializers.DictField(required=False, default=dict)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["approvals"])
class ApprovalViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = ApprovalRequestSerializer
    filterset_fields = ["status", "kind", "requisition"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[ApprovalRequest]:
        if self.is_schema_request:
            return ApprovalRequest.objects.none()
        return services.visible_requests(self.ctx).prefetch_related("decisions")

    @extend_schema(request=DecideIn, responses=ApprovalRequestSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str) -> Response:
        payload = DecideIn(data=request.data)
        payload.is_valid(raise_exception=True)
        services.decide(self.ctx, request_id=UUID(pk), **payload.validated_data)
        approval = services.get_visible_request(self.ctx, UUID(pk))
        return Response(ApprovalRequestSerializer(approval, context={"ctx": self.ctx}).data)


router = SimpleRouter()
router.register("approvals", ApprovalViewSet, basename="approval")
urlpatterns = router.urls
