import json
from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.views import APIView

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope
from apps.integrations import services
from apps.integrations.models import CalendarBusyBlock, IntegrationConnection


class BusyBlockSerializer(serializers.ModelSerializer[CalendarBusyBlock]):
    user_id = serializers.UUIDField()
    interview_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = CalendarBusyBlock
        fields = ["id", "user_id", "start", "end", "title", "interview_id"]
        read_only_fields = ["id", "interview_id"]


class ConnectionSerializer(serializers.ModelSerializer[IntegrationConnection]):
    class Meta:
        model = IntegrationConnection
        fields = ["id", "kind", "provider", "name", "config", "is_active", "last_synced_at"]
        read_only_fields = fields


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["integrations"])
class BusyBlockViewSet(TenantViewSet, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin):
    """The built-in calendar. ?user=<id> to read a panelist's busy times (recruiters and HR admins)."""

    serializer_class = BusyBlockSerializer
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[CalendarBusyBlock]:
        if self.is_schema_request:
            return CalendarBusyBlock.objects.none()
        queryset = CalendarBusyBlock.objects.filter(tenant_id=self.ctx.tenant_id)
        user = self.request.query_params.get("user")
        if user and self.ctx.has_role("hr_admin", "recruiter"):
            return queryset.filter(user_id=user)
        return queryset.filter(user_id=self.ctx.user_id)

    @extend_schema(request=BusyBlockSerializer, responses={201: BusyBlockSerializer})
    def create(self, request: Request) -> Response:
        payload = BusyBlockSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        block = services.add_busy_block(self.ctx, **payload.validated_data)
        return Response(BusyBlockSerializer(block).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, pk: str) -> Response:
        services.delete_busy_block(self.ctx, block_id=UUID(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["integrations"])
class ConnectionViewSet(TenantViewSet, mixins.ListModelMixin):
    serializer_class = ConnectionSerializer

    def get_queryset(self) -> QuerySet[IntegrationConnection]:
        if self.is_schema_request or not self.ctx.has_role("hr_admin"):
            return IntegrationConnection.objects.none()
        return IntegrationConnection.objects.filter(tenant_id=self.ctx.tenant_id)


class AtsWebhookView(APIView):
    """Signed ATS webhooks: POST /api/v1/integrations/webhooks/<tenant_slug>/<connection_id>/

    Header X-Signature: sha256=<hex HMAC of the raw body with the connection's secret>.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "webhooks"

    @extend_schema(
        request=inline_serializer(
            "AtsWebhookIn",
            {
                "event_id": serializers.CharField(),
                "event_type": serializers.CharField(),
                "data": serializers.DictField(),
            },
        ),
        responses={202: None},
        tags=["integrations"],
    )
    def post(self, request: Request, tenant_slug: str, connection_id: UUID) -> Response:
        tenant = Tenant.objects.filter(slug=tenant_slug, is_active=True).first()
        not_found = Response({"error": {"code": "not_found", "message": "Not found.", "details": {}}}, status=404)
        if tenant is None:
            return not_found
        body = request.body
        with tenant_scope(tenant.id):
            connection = IntegrationConnection.objects.filter(pk=connection_id, kind="ats", is_active=True).first()
            if connection is None or not services.verify_signature(
                connection, body, request.headers.get("X-Signature", "")
            ):
                return not_found
            try:
                event = json.loads(body)
                services.receive_webhook(
                    connection=connection,
                    event_id=str(event["event_id"]),
                    event_type=str(event["event_type"]),
                    payload=dict(event["data"]),
                )
            except (KeyError, TypeError, ValueError):
                return Response(
                    {"error": {"code": "invalid_request", "message": "Malformed event.", "details": {}}}, status=400
                )
        return Response(status=status.HTTP_202_ACCEPTED)


router = SimpleRouter()
router.register("calendar/busy-blocks", BusyBlockViewSet, basename="busy-block")
router.register("integrations/connections", ConnectionViewSet, basename="integration-connection")
