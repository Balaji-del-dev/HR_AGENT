from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.core.exceptions import ApplicationError, PolicyDenied
from apps.governance import services
from apps.governance.models import AuditEvent, DeletionRequest, RetentionPolicy, SecurityIncident

AUDIT_ROLES = ("hr_admin", "auditor")


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor_id",
            "actor_type",
            "action",
            "target_type",
            "target_id",
            "run_id",
            "request_id",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class DeletionRequestSerializer(serializers.ModelSerializer[DeletionRequest]):
    candidate_id = serializers.UUIDField(read_only=True, allow_null=True)
    requested_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = DeletionRequest
        fields = [
            "id",
            "candidate_id",
            "candidate_ref",
            "status",
            "reason",
            "requested_by_id",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class DeletionRequestIn(serializers.Serializer[Any]):
    candidate_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class IncidentSerializer(serializers.ModelSerializer[SecurityIncident]):
    class Meta:
        model = SecurityIncident
        fields = [
            "id",
            "kind",
            "severity",
            "title",
            "description",
            "status",
            "run_id",
            "root_cause",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


class RetentionPolicySerializer(serializers.ModelSerializer[RetentionPolicy]):
    class Meta:
        model = RetentionPolicy
        fields = ["id", "target", "retain_days", "is_active"]
        read_only_fields = ["id"]


class _AuditorOnly(TenantViewSet):
    def check_permissions(self, request: Request) -> None:
        super().check_permissions(request)
        if not self.is_schema_request and not self.ctx.has_role(*AUDIT_ROLES):
            raise PolicyDenied("Only HR admins and auditors can read governance records.")


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["governance"])
class AuditEventViewSet(_AuditorOnly, mixins.ListModelMixin):
    serializer_class = AuditEventSerializer
    filterset_fields = ["action", "target_type", "target_id", "run_id", "actor_type"]

    def get_queryset(self) -> QuerySet[AuditEvent]:
        if self.is_schema_request:
            return AuditEvent.objects.none()
        return AuditEvent.objects.filter(tenant_id=self.ctx.tenant_id)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["governance"])
class IncidentViewSet(_AuditorOnly, mixins.ListModelMixin):
    serializer_class = IncidentSerializer
    filterset_fields = ["kind", "severity", "status"]

    def get_queryset(self) -> QuerySet[SecurityIncident]:
        if self.is_schema_request:
            return SecurityIncident.objects.none()
        return SecurityIncident.objects.filter(tenant_id=self.ctx.tenant_id)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["governance"])
class DeletionRequestViewSet(TenantViewSet, mixins.ListModelMixin):
    serializer_class = DeletionRequestSerializer
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[DeletionRequest]:
        if self.is_schema_request:
            return DeletionRequest.objects.none()
        queryset = DeletionRequest.objects.filter(tenant_id=self.ctx.tenant_id)
        if not self.ctx.has_role(*AUDIT_ROLES):
            queryset = queryset.filter(requested_by_id=self.ctx.user_id)
        return queryset

    @extend_schema(request=DeletionRequestIn, responses={201: DeletionRequestSerializer})
    def create(self, request: Request) -> Response:
        payload = DeletionRequestIn(data=request.data)
        payload.is_valid(raise_exception=True)
        created = services.create_deletion_request(self.ctx, **payload.validated_data)
        return Response(DeletionRequestSerializer(created).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=DeletionRequestSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str) -> Response:
        return Response(
            DeletionRequestSerializer(services.complete_deletion_request(self.ctx, request_id=UUID(pk))).data
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["governance"])
class RetentionPolicyViewSet(TenantViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    serializer_class = RetentionPolicySerializer

    def get_queryset(self) -> QuerySet[RetentionPolicy]:
        if self.is_schema_request:
            return RetentionPolicy.objects.none()
        return RetentionPolicy.objects.filter(tenant_id=self.ctx.tenant_id)

    @extend_schema(request=RetentionPolicySerializer, responses={201: RetentionPolicySerializer})
    def create(self, request: Request) -> Response:
        if not self.ctx.has_role("hr_admin"):
            raise PolicyDenied("Only HR admins set retention.")
        payload = RetentionPolicySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if payload.validated_data["retain_days"] < 30:
            raise ApplicationError("Retention must be at least 30 days.")
        policy, _ = RetentionPolicy.objects.update_or_create(
            target=payload.validated_data["target"],
            defaults={
                "retain_days": payload.validated_data["retain_days"],
                "is_active": payload.validated_data.get("is_active", True),
            },
        )
        services.record_audit(
            self.ctx,
            action="retention.updated",
            target_type="retention_policy",
            target_id=policy.id,
            details={"target": policy.target, "days": policy.retain_days},
        )
        return Response(RetentionPolicySerializer(policy).data, status=status.HTTP_201_CREATED)


router = SimpleRouter()
router.register("audit-events", AuditEventViewSet, basename="audit-event")
router.register("incidents", IncidentViewSet, basename="incident")
router.register("deletion-requests", DeletionRequestViewSet, basename="deletion-request")
router.register("retention-policies", RetentionPolicyViewSet, basename="retention-policy")
urlpatterns = router.urls
