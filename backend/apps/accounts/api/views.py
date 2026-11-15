"""Session sign-in for the React app, the current user's tenants and roles, and member lookups.

Production adds OIDC (Keycloak) in front of the same session: see docs/adr/0003.
"""

from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView
from apps.accounts.models import User
from apps.accounts.selectors import active_memberships, tenant_members


class MembershipOut(serializers.Serializer[Any]):
    tenant_id = serializers.UUIDField()
    tenant_name = serializers.CharField()
    tenant_slug = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class MeOut(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    username = serializers.CharField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    memberships = MembershipOut(many=True)


def me_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name() or user.username,
        "memberships": [
            {"tenant_id": m.tenant_id, "tenant_name": m.tenant.name, "tenant_slug": m.tenant.slug, "roles": m.roles}
            for m in active_memberships(user.id).select_related("tenant").order_by("tenant__name")
        ],
    }


class LoginIn(serializers.Serializer[Any]):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(responses=inline_serializer("CsrfOut", {"csrf_token": serializers.CharField()}), tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response({"csrf_token": get_token(request._request)})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    @extend_schema(request=LoginIn, responses={200: MeOut}, tags=["auth"])
    def post(self, request: Request) -> Response:
        payload = LoginIn(data=request.data)
        payload.is_valid(raise_exception=True)
        user = authenticate(request._request, **payload.validated_data)
        if user is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Wrong username or password, or the account is locked after too many attempts.",
                        "details": {},
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request._request, user)
        return Response(me_payload(user))


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses=MeOut, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(me_payload(request.user))  # type: ignore[arg-type]


class MemberOut(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    full_name = serializers.CharField()
    username = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class MembersView(TenantAPIView):
    """Members of the active tenant, for pickers. Optional ?role= filter."""

    @extend_schema(
        parameters=[TENANT_HEADER_PARAMETER, OpenApiParameter("role", str, required=False)],
        responses=MemberOut(many=True),
        tags=["auth"],
    )
    def get(self, request: Request) -> Response:
        role = request.query_params.get("role")
        members = tenant_members(tenant_id=self.ctx.tenant_id)
        if role:
            members = members.filter(roles__contains=[role])
        return Response(
            [
                {
                    "user_id": m.user_id,
                    "full_name": m.user.get_full_name() or m.user.username,
                    "username": m.user.username,
                    "roles": m.roles,
                }
                for m in members.order_by("user__first_name", "user__username")
            ]
        )
