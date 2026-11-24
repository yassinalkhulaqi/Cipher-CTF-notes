"""Timezone-safe calendar helpers used by activity digests and projections.

All boundaries are computed in an explicit IANA timezone. No wall clock is
read here, so results are deterministic for a fixed timestamp and timezone.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redscribe.v3.activity.models import (
    DEFAULT_TIMEZONE,
    DIGEST_PERIODS,
    PERIOD_DAILY,
    PERIOD_WEEKLY,
)

UTC = timezone.utc


class TimezoneError(ValueError):
    """Raised when an unsupported timezone name is requested."""


def resolve_timezone(name: str = DEFAULT_TIMEZONE) -> tzinfo:
    """Resolve an IANA timezone name, rejecting unknown values."""
    cleaned = (name or DEFAULT_TIMEZONE).strip()
    if cleaned.casefold() in {"utc", "z", "+00:00", ""}:
        return UTC
    try:
        return ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise TimezoneError(f"Unknown timezone: {name}") from error


def local_datetime(timestamp: float, zone: tzinfo) -> datetime:
    """Convert a Unix timestamp to an aware datetime in ``zone``."""
    return datetime.fromtimestamp(timestamp, tz=UTC).astimezone(zone)


def day_key(timestamp: float, zone: tzinfo) -> str:
    """Return the local calendar day key (``YYYY-MM-DD``)."""
    return local_datetime(timestamp, zone).date().isoformat()


def week_key(timestamp: float, zone: tzinfo) -> str:
    """Return the local ISO week key (``YYYY-Www``)."""
    local = local_datetime(timestamp, zone)
    iso = local.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def start_of_day(timestamp: float, zone: tzinfo) -> datetime:
    """Return midnight at the start of the local day containing ``timestamp``."""
    local_date = local_datetime(timestamp, zone).date()
    return datetime.combine(local_date, time.min, tzinfo=zone)


def start_of_week(timestamp: float, zone: tzinfo) -> datetime:
    """Return Monday midnight of the local week containing ``timestamp``."""
    local_date = local_datetime(timestamp, zone).date()
    monday = local_date - timedelta(days=local_date.weekday())
    return datetime.combine(monday, time.min, tzinfo=zone)


def period_bounds(
    timestamp: float,
    period: str,
    zone: tzinfo,
) -> tuple[float, float, str, str]:
    """Return ``(start, end, key, label)`` for a digest period boundary.

    The end boundary is the start of the following period, so neighbouring
    buckets never overlap even across daylight-saving transitions.
    """
    normalized = period.strip().casefold()
    if normalized not in DIGEST_PERIODS:
        raise TimezoneError(f"Unknown digest period: {period}")
    if normalized == PERIOD_WEEKLY:
        start = start_of_week(timestamp, zone)
        end = start + timedelta(weeks=1)
    else:
        start = start_of_day(timestamp, zone)
        end = start + timedelta(days=1)
    key = start.date().isoformat() if normalized == PERIOD_DAILY else _iso_week_label(start)
    label = (
        start.date().isoformat()
        if normalized == PERIOD_DAILY
        else f"Week of {start.date().isoformat()}"
    )
    return start.timestamp(), end.timestamp(), key, label


def _iso_week_label(moment: datetime) -> str:
    """Format a Monday datetime as an ISO week label."""
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def bucket_key(timestamp: float, period: str, zone: tzinfo) -> str:
    """Return the bucket key for a timestamp and period."""
    normalized = period.strip().casefold()
    if normalized == PERIOD_WEEKLY:
        return week_key(timestamp, zone)
    if normalized == PERIOD_DAILY:
        return day_key(timestamp, zone)
    raise TimezoneError(f"Unknown digest period: {period}")


def bucket_label(timestamp: float, period: str, zone: tzinfo) -> str:
    """Return a human-friendly label for a timestamp's bucket."""
    normalized = period.strip().casefold()
    if normalized == PERIOD_WEEKLY:
        return f"Week of {start_of_week(timestamp, zone).date().isoformat()}"
    if normalized == PERIOD_DAILY:
        return day_key(timestamp, zone)
    raise TimezoneError(f"Unknown digest period: {period}")


def window_keys(start: float, end: float, period: str, zone: tzinfo) -> tuple[str, ...]:
    """List every bucket key whose start lies inside ``[start, end)``."""
    if end <= start:
        return ()
    normalized = period.strip().casefold()
    if normalized not in DIGEST_PERIODS:
        raise TimezoneError(f"Unknown digest period: {period}")
    keys: list[str] = []
    cursor = start_of_day(start, zone) if normalized == PERIOD_DAILY else start_of_week(start, zone)
    step = timedelta(days=1) if normalized == PERIOD_DAILY else timedelta(weeks=1)
    while cursor.timestamp() < end:
        keys.append(
            _iso_week_label(cursor) if normalized == PERIOD_WEEKLY else cursor.date().isoformat()
        )
        cursor = cursor + step
    return tuple(keys)
