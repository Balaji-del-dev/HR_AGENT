"""One error shape for the whole API: {"error": {"code", "message", "details", "request_id"}}."""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.exceptions import ApplicationError


def _body(code: str, message: str, details: Any, request: Any) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": getattr(request, "request_id", None),
        }
    }


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    request = context.get("request")

    if isinstance(exc, ApplicationError):
        return Response(_body(exc.code, exc.message, exc.details, request), status=exc.status_code)

    # DRF converts these internally; convert first so the body below is shaped too.
    # The generic message also avoids naming the model that was looked up.
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled: Django returns a 500 and Sentry records it

    if isinstance(exc, drf_exceptions.ValidationError):
        response.data = _body("validation_error", "Some fields are invalid.", response.data, request)
    elif isinstance(exc, drf_exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        message = exc.detail if isinstance(exc.detail, str) else str(exc.default_detail)
        response.data = _body(code, str(message), {}, request)
    return response
