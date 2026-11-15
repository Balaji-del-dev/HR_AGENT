"""Publishing to WebSocket groups from web processes and Celery workers.

Events go out after the current transaction commits, so a browser never hears
about a row it cannot read yet. Publishing is best effort: a Redis hiccup must
not fail the business transaction that triggered it.
"""

import logging
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)


def run_group(run_id: UUID | str) -> str:
    return f"run_{UUID(str(run_id)).hex}"


def user_group(user_id: UUID | str) -> str:
    return f"user_{UUID(str(user_id)).hex}"


def _send(group: str, event: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": "push.event", "event": event})
    except Exception:
        logger.warning("could not publish realtime event", extra={"group": group}, exc_info=True)


def publish(group: str, event: dict[str, Any], *, on_commit: bool = True) -> None:
    if on_commit:
        transaction.on_commit(lambda: _send(group, event))
    else:
        _send(group, event)


def publish_run_event(run_id: UUID | str, event: dict[str, Any], *, on_commit: bool = True) -> None:
    publish(run_group(run_id), {"run_id": str(run_id), **event}, on_commit=on_commit)


def notify_users(user_ids: Iterable[UUID], event: dict[str, Any]) -> None:
    for user_id in set(user_ids):
        publish(user_group(user_id), event)
