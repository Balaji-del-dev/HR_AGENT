import redis
from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

_STATUS = inline_serializer("HealthStatus", {"status": serializers.CharField()})


class HealthView(APIView):
    """Liveness: the process is up. Touches nothing else."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(responses=_STATUS, tags=["ops"])
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """Readiness: Postgres and Redis answer. Used by the Kubernetes readiness probe."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: _STATUS,
            503: inline_serializer(
                "ReadinessFailure", {"status": serializers.CharField(), "checks": serializers.DictField()}
            ),
        },
        tags=["ops"],
    )
    def get(self, request: Request) -> Response:
        checks: dict[str, str] = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["postgres"] = "ok"
        except Exception:  # noqa: BLE001 - any failure means not ready
            checks["postgres"] = "unavailable"
        try:
            redis.Redis.from_url(settings.REDIS_CACHE_URL, socket_timeout=1).ping()
            checks["redis"] = "ok"
        except redis.RedisError:
            checks["redis"] = "unavailable"

        if all(value == "ok" for value in checks.values()):
            return Response({"status": "ok"})
        return Response({"status": "unavailable", "checks": checks}, status=503)
