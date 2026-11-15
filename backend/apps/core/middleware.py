import re
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

from apps.core import tenancy

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class RequestContextMiddleware:
    """Gives every request an id, and makes sure no active tenant outlives it.

    An incoming X-Request-ID is reused when it looks safe (so traces from a
    gateway line up); otherwise a new one is generated. The tenant itself is
    activated later, by the API base view, once DRF has authenticated the user.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        tenancy.deactivate()
        try:
            response = self.get_response(request)
        finally:
            tenancy.deactivate()
        # Log context is left bound on purpose: Django logs 4xx/5xx responses after
        # middleware returns, and those lines should carry the request id. The next
        # request clears it above.
        response[REQUEST_ID_HEADER] = request_id
        return response
