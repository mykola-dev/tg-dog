from __future__ import annotations

from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def manual_last_n_hours_window(hours: int, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    if hours <= 0:
        raise ValueError("hours must be positive")
    end = now or now_utc()
    start = end - timedelta(hours=hours)
    return start, end


def scheduled_daily_window(
    *,
    previous_end: datetime | None,
    boundary_end: datetime,
) -> tuple[datetime, datetime]:
    if previous_end is None:
        start = boundary_end - timedelta(days=1)
    else:
        start = previous_end
    if start >= boundary_end:
        raise ValueError("scheduled window start must be before end")
    return start, boundary_end
