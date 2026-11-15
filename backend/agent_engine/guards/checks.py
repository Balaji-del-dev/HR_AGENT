"""Input and output guards (steps 3 and 9 of the execution chain).

Input: free text typed by staff or written by candidates is scanned for
prompt-injection patterns. Findings are recorded on the run; graphs that read
untrusted text still cannot act without a human approval.

Output: before anything is stored or shown, model output is checked for
contact details the viewer did not ask for, protected attributes in matching
output, and ids of other tenants. Contact details are redacted; a foreign
tenant id is treated as an incident.
"""

import re
from typing import Any
from uuid import UUID

from apps.core.context import ExecutionContext
from document_ai.injection import scan_for_injection
from document_ai.masking import _EMAIL, _mask_phones

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_PROTECTED = re.compile(
    r"\b(age[ds]?|years old|gender|male|female|married|pregnan\w*|religio\w+|caste|nationality|ethnic\w*|race|"
    r"disabilit\w+|disabled)\b",
    re.IGNORECASE,
)


def scan_input(text: str, *, source: str) -> list[dict[str, Any]]:
    return [
        {"guard": "input", "source": source, "label": f.label, "excerpt": f.excerpt} for f in scan_for_injection(text)
    ]


def redact_contact_details(text: str) -> tuple[str, int]:
    redacted, emails = _EMAIL.subn("[EMAIL]", text)
    redacted, phones = _mask_phones(redacted)
    return redacted, emails + phones


def protected_attribute_mentions(text: str) -> list[str]:
    return sorted({match.group(0).lower() for match in _PROTECTED.finditer(text or "")})


def foreign_tenant_ids(text: str, ctx: ExecutionContext) -> list[str]:
    from apps.core.models import Tenant

    ids = {UUID(m.group(0)) for m in _UUID.finditer(text or "")} - {ctx.tenant_id}
    if not ids:
        return []
    return [str(t) for t in Tenant.objects.filter(pk__in=ids).values_list("id", flat=True)]


def strings_in(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in strings_in(item)]
    if isinstance(value, list | tuple):
        return [s for item in value for s in strings_in(item)]
    return []
