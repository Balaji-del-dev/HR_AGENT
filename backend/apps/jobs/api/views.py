from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.jobs import selectors, services
from apps.jobs.models import JDTemplate, JobDescription


class JobDescriptionSerializer(serializers.ModelSerializer[JobDescription]):
    requisition_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    approved_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    agent_run_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = JobDescription
        fields = [
            "id",
            "requisition_id",
            "version",
            "title",
            "summary",
            "responsibilities",
            "requirements",
            "body",
            "status",
            "compliance_flags",
            "created_by_id",
            "agent_run_id",
            "prompt_version",
            "approved_by_id",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class JobDescriptionUpdateIn(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=200, required=False)
    summary = serializers.CharField(required=False, allow_blank=True)
    responsibilities = serializers.ListField(child=serializers.CharField(), required=False)
    requirements = serializers.ListField(child=serializers.DictField(), required=False)
    body = serializers.CharField(required=False, allow_blank=True)


class JDTemplateSerializer(serializers.ModelSerializer[JDTemplate]):
    class Meta:
        model = JDTemplate
        fields = ["id", "name", "department", "body", "is_active"]
        read_only_fields = ["id", "is_active"]


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["jobs"])
class JobDescriptionViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = JobDescriptionSerializer
    filterset_fields = ["requisition", "status"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[JobDescription]:
        if self.is_schema_request:
            return JobDescription.objects.none()
        return selectors.visible_jds(self.ctx)

    @extend_schema(request=JobDescriptionUpdateIn, responses=JobDescriptionSerializer)
    def partial_update(self, request: Request, pk: str) -> Response:
        payload = JobDescriptionUpdateIn(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        return Response(
            JobDescriptionSerializer(services.update_jd_draft(self.ctx, jd_id=UUID(pk), **payload.validated_data)).data
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["jobs"])
class JDTemplateViewSet(TenantViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    serializer_class = JDTemplateSerializer

    def get_queryset(self) -> QuerySet[JDTemplate]:
        if self.is_schema_request:
            return JDTemplate.objects.none()
        return selectors.templates_for(self.ctx)

    @extend_schema(request=JDTemplateSerializer, responses={201: JDTemplateSerializer})
    def create(self, request: Request) -> Response:
        payload = JDTemplateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        template = services.create_template(self.ctx, **payload.validated_data)
        return Response(JDTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


router = SimpleRouter()
router.register("job-descriptions", JobDescriptionViewSet, basename="job-description")
router.register("jd-templates", JDTemplateViewSet, basename="jd-template")
urlpatterns = router.urls
