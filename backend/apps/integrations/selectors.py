from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from apps.integrations.models import CalendarBusyBlock
from apps.interviews.scheduling import Interval


def busy_intervals(*, user_ids: Sequence[UUID], start: datetime, end: datetime) -> list[Interval]:
    """Free/busy for the built-in calendar. Other calendar providers implement the same call."""
    blocks = CalendarBusyBlock.objects.filter(user_id__in=user_ids, end__gt=start, start__lt=end)
    return [Interval(block.start, block.end) for block in blocks]
