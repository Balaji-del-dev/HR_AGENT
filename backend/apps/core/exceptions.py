"""
Exceptions shared by every app.

Services raise :class:`ApplicationError` subclasses. The API exception handler
turns them into ``{"error": {...}}`` responses with the given status code, so
service code never imports DRF.
"""

from typing import Any


class ApplicationError(Exception):
    status_code = 400
    code = "invalid_request"
    default_message = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class NotFound(ApplicationError):
    status_code = 404
    code = "not_found"
    default_message = "Not found."


class PolicyDenied(ApplicationError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this action."


class InvalidStateTransition(ApplicationError):
    status_code = 409
    code = "invalid_state"
    default_message = "This action is not allowed in the record's current state."


class TenantRequired(ApplicationError):
    status_code = 400
    code = "tenant_required"
    default_message = "You belong to more than one tenant. Send the X-Tenant-ID header."


class TenantAccessDenied(ApplicationError):
    status_code = 403
    code = "tenant_access_denied"
    default_message = "You do not have access to this tenant."


class TenantScopeError(RuntimeError):
    """A programming error: tenant-owned data touched without the right active tenant.

    Deliberately not an ApplicationError, so it surfaces as a 500 and in Sentry.
    """
