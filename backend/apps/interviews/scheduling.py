"""Finding common free time for a panel. Plain code: the agent only proposes what this returns."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class Interval:
    start: datetime
    end: datetime


def _merge(busy: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for block in sorted(busy, key=lambda b: b.start):
        if merged and block.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, block.end))
        else:
            merged.append(block)
    return merged


def find_common_slots(
    *,
    busy: Iterable[Interval],
    window_start: datetime,
    days: int,
    duration: timedelta,
    timezone_name: str = "Asia/Kolkata",
    work_start: time = time(10, 0),
    work_end: time = time(18, 0),
    step: timedelta = timedelta(minutes=30),
    limit: int = 3,
    spread_days: bool = True,
) -> list[Interval]:
    """Up to ``limit`` working-hours slots free for everyone, preferring different days."""
    zone = ZoneInfo(timezone_name)
    blocks = _merge(busy)
    found: list[Interval] = []
    day: date = window_start.astimezone(zone).date()
    working_days_seen = 0
    while working_days_seen < days and len(found) < limit:
        if day.weekday() < 5:
            working_days_seen += 1
            cursor = datetime.combine(day, work_start, zone)
            day_end = datetime.combine(day, work_end, zone)
            while cursor + duration <= day_end:
                slot = Interval(cursor, cursor + duration)
                if slot.start >= window_start and not any(b.start < slot.end and slot.start < b.end for b in blocks):
                    found.append(slot)
                    if spread_days or len(found) >= limit:
                        break
                cursor += step
        day += timedelta(days=1)
    return found[:limit]
