from typing import Any
from uuid import UUID

from django.urls import path
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView
from apps.analytics.reports import REPORTS, run_report
from apps.core.exceptions import PolicyDenied


class ReportOut(serializers.Serializer[Any]):
    name = serializers.CharField()
    title = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    rows = serializers.ListField(child=serializers.ListField())
    query = serializers.CharField()
    notes = serializers.ListField(child=serializers.CharField())


class ReportInfo(serializers.Serializer[Any]):
    name = serializers.CharField()
    description = serializers.CharField()


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["analytics"])
class ReportsView(TenantAPIView):
    @extend_schema(responses=ReportInfo(many=True))
    def get(self, request: Request) -> Response:
        return Response([{"name": name, "description": desc} for name, (desc, _) in REPORTS.items()])


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["analytics"])
class PipelineView(TenantAPIView):
    """GET /analytics/pipeline/?report=pipeline_funnel&requisition=<id>"""

    @extend_schema(
        parameters=[
            OpenApiParameter("report", str, enum=list(REPORTS)),
            OpenApiParameter("requisition", str, required=False),
        ],
        responses=ReportOut,
    )
    def get(self, request: Request) -> Response:
        if not self.ctx.has_role("hr_admin", "recruiter", "hiring_manager", "auditor"):
            raise PolicyDenied("Your roles cannot view analytics.")
        requisition = request.query_params.get("requisition")
        report = run_report(
            self.ctx,
            request.query_params.get("report", "pipeline_funnel"),
            requisition_id=UUID(requisition) if requisition else None,
        )
        return Response(report.as_dict())


urlpatterns = [
    path("analytics/reports/", ReportsView.as_view(), name="analytics-reports"),
    path("analytics/pipeline/", PipelineView.as_view(), name="analytics-pipeline"),
]
