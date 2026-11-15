from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.communications import services
from apps.communications.models import EmailDraft, EmailTemplate


class EmailDraftSerializer(serializers.ModelSerializer[EmailDraft]):
    candidate_id = serializers.UUIDField(read_only=True)
    application_id = serializers.UUIDField(read_only=True, allow_null=True)
    interview_id = serializers.UUIDField(read_only=True, allow_null=True)
    agent_run_id = serializers.UUIDField(read_only=True, allow_null=True)
    sent_at = serializers.DateTimeField(source="message.sent_at", read_only=True, allow_null=True, default=None)

    class Meta:
        model = EmailDraft
        fields = [
            "id",
            "candidate_id",
            "application_id",
            "interview_id",
            "kind",
            "to_email",
            "subject",
            "body",
            "status",
            "agent_run_id",
            "approved_at",
            "sent_at",
            "error",
            "created_at",
        ]
        read_only_fields = fields


class EmailTemplateSerializer(serializers.ModelSerializer[EmailTemplate]):
    class Meta:
        model = EmailTemplate
        fields = ["id", "key", "name", "kind", "subject", "body", "is_active"]
        read_only_fields = ["id", "is_active"]


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["communications"])
class EmailDraftViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = EmailDraftSerializer
    filterset_fields = ["status", "kind", "application", "candidate"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[EmailDraft]:
        if self.is_schema_request:
            return EmailDraft.objects.none()
        return services.visible_drafts(self.ctx).select_related("message")


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["communications"])
class EmailTemplateViewSet(TenantViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    serializer_class = EmailTemplateSerializer

    def get_queryset(self) -> QuerySet[EmailTemplate]:
        if self.is_schema_request:
            return EmailTemplate.objects.none()
        return EmailTemplate.objects.filter(tenant_id=self.ctx.tenant_id)

    @extend_schema(request=EmailTemplateSerializer, responses={201: EmailTemplateSerializer})
    def create(self, request: Request) -> Response:
        payload = EmailTemplateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        template = services.create_template(self.ctx, **payload.validated_data)
        return Response(EmailTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


router = SimpleRouter()
router.register("email-drafts", EmailDraftViewSet, basename="email-draft")
router.register("email-templates", EmailTemplateViewSet, basename="email-template")
urlpatterns = router.urls
