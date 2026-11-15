"""WebSocket consumers: live events for one agent run, and notifications for the signed-in user.

The client connects with ``?ticket=<one-time ticket>`` from POST /api/v1/ws-tickets/.
The ticket is deleted on first use. For a run, the consumer checks (under the
ticket's tenant, with Row-Level Security) that the user may see it before
joining group run_<id>.
"""

from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache

from apps.core.realtime import run_group, user_group

WS_TICKET_PREFIX = "ws-ticket:"


def redeem_ticket(query_string: bytes) -> dict[str, str] | None:
    ticket = parse_qs(query_string.decode()).get("ticket", [""])[0]
    if not ticket:
        return None
    key = WS_TICKET_PREFIX + ticket
    data: dict[str, str] | None = cache.get(key)
    if data is not None:
        cache.delete(key)  # one-time
    return data


def can_view_run(user_id: str, tenant_id: str, run_id: str) -> bool:
    from apps.accounts.services import build_execution_context
    from apps.agents.selectors import visible_runs
    from apps.core.exceptions import ApplicationError
    from apps.core.tenancy import tenant_scope

    try:
        ctx = build_execution_context(user_id=UUID(user_id), requested_tenant_id=UUID(tenant_id))
        with tenant_scope(ctx.tenant_id):
            return visible_runs(ctx).filter(pk=UUID(str(run_id))).exists()
    except (ApplicationError, ValueError):
        return False


class _PushConsumer(AsyncJsonWebsocketConsumer):  # type: ignore[misc]
    group: str = ""

    async def disconnect(self, code: int) -> None:
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def push_event(self, message: dict[str, Any]) -> None:
        await self.send_json(message["event"])

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})


class RunEventsConsumer(_PushConsumer):
    async def connect(self) -> None:
        ticket = await database_sync_to_async(redeem_ticket)(self.scope["query_string"])
        run_id = self.scope["url_route"]["kwargs"]["run_id"]
        if ticket is None or not await database_sync_to_async(can_view_run)(
            ticket["user_id"], ticket["tenant_id"], run_id
        ):
            await self.close(code=4403)
            return
        self.group = run_group(run_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()


class NotificationsConsumer(_PushConsumer):
    async def connect(self) -> None:
        ticket = await database_sync_to_async(redeem_ticket)(self.scope["query_string"])
        if ticket is None:
            await self.close(code=4403)
            return
        self.group = user_group(ticket["user_id"])
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
