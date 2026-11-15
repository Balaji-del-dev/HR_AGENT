from typing import Any
from uuid import UUID

import structlog
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import exceptions, viewsets
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.services import build_execution_context
from apps.core import tenancy
from apps.core.context import ExecutionContext

TENANT_HEADER = "X-Tenant-ID"

TENANT_HEADER_PARAMETER = OpenApiParameter(
    name=TENANT_HEADER,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Tenant to act in. Required only for users with more than one tenant.",
)


class TenantContextMixin:
    """Base for every view that touches tenant data.

    Straight after DRF authenticates the user, and before permission checks,
    it builds ``request.ctx`` (an ExecutionContext) and activates the tenant
    for the request transaction. A view that forgets this mixin fails closed:
    with no tenant active, Row-Level Security returns no rows and rejects writes.
    """

    def perform_authentication(self, request: Request) -> None:
        super().perform_authentication(request)  # type: ignore[misc]
        user = request.user
        if not user or not user.is_authenticated:
            raise exceptions.NotAuthenticated()

        raw = request.headers.get(TENANT_HEADER)
        try:
            requested = UUID(raw) if raw else None
        except ValueError as exc:
            raise exceptions.ValidationError({TENANT_HEADER: "Must be a UUID."}) from exc

        ctx = build_execution_context(
            user_id=user.pk, requested_tenant_id=requested, request_id=getattr(request, "request_id", None)
        )
        tenancy.activate_tenant(ctx.tenant_id)
        structlog.contextvars.bind_contextvars(tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
        request.ctx = ctx  # type: ignore[attr-defined]

    def get_serializer_context(self) -> dict[str, Any]:
        context: dict[str, Any] = super().get_serializer_context()  # type: ignore[misc]
        context["ctx"] = getattr(self.request, "ctx", None)  # type: ignore[attr-defined]
        return context


class TenantAPIView(TenantContextMixin, APIView):
    """An APIView with ``self.ctx`` (the caller's ExecutionContext) activated."""

    @property
    def ctx(self) -> ExecutionContext:
        return self.request.ctx  # type: ignore[attr-defined, no-any-return]


class TenantViewSet(TenantContextMixin, viewsets.GenericViewSet):  # type: ignore[type-arg]
    throttle_scope = ""  # set per action, e.g. @action(..., throttle_scope="agent_runs")

    @property
    def ctx(self) -> ExecutionContext:
        return self.request.ctx  # type: ignore[attr-defined, no-any-return]

    @property
    def is_schema_request(self) -> bool:
        return bool(getattr(self, "swagger_fake_view", False))
