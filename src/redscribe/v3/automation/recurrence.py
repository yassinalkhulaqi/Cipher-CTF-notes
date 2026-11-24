"""Deterministic recurrence rules for scheduled documentation workflows."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

from redscribe.v3.automation.errors import RecurrenceError
from redscribe.v3.automation.parsing import issue
from redscribe.v3.automation.types import Frequency, RecurrenceRule, ValidationIssue

_WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MAX_PERIODS = 200_000


def _utc(timestamp: float) -> datetime:
    """Convert a timestamp to a UTC datetime."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def validate_recurrence(rule: RecurrenceRule) -> tuple[ValidationIssue, ...]:
    """Return diagnostics for a recurrence rule."""
    problems: list[ValidationIssue] = []
    if rule.end_at and rule.end_at <= rule.start_at:
        problems.append(
            issue(
                "invalid_window", "Recurrence end must follow its start", path="recurrence.end_at"
            )
        )
    if rule.frequency is Frequency.WEEKLY and not rule.by_weekday:
        problems.append(
            issue(
                "missing_weekday",
                "Weekly recurrence without by_weekday uses the start date's weekday",
                path="recurrence.by_weekday",
                severity="warning",
            )
        )
    if rule.frequency is not Frequency.MONTHLY and rule.by_month_day is not None:
        problems.append(
            issue(
                "ignored_field",
                "by_month_day is ignored unless frequency is monthly",
                path="recurrence.by_month_day",
                severity="warning",
            )
        )
    return tuple(problems)


def _at_time(moment: datetime, rule: RecurrenceRule) -> datetime:
    """Apply a rule's UTC hour and minute to a calendar date."""
    return moment.replace(hour=rule.hour, minute=rule.minute, second=0, microsecond=0)


def _month_day(year: int, month: int, rule: RecurrenceRule, seed_day: int) -> datetime:
    """Build a monthly candidate, clamping invalid days to the month's last day."""
    day = rule.by_month_day or seed_day
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, min(day, last_day), tzinfo=timezone.utc)


def _first_candidate(rule: RecurrenceRule, lower: float) -> datetime:
    """Build the first candidate at or after ``lower``."""
    moment = _utc(lower)
    if rule.frequency is Frequency.HOURLY:
        candidate = moment.replace(minute=0, second=0, microsecond=0) + timedelta(
            minutes=rule.minute
        )
        while candidate.timestamp() < lower:
            candidate += timedelta(hours=rule.interval)
        return candidate
    if rule.frequency is Frequency.DAILY:
        candidate = _at_time(moment.replace(hour=0, minute=0, second=0, microsecond=0), rule)
        while candidate.timestamp() < lower:
            candidate += timedelta(days=rule.interval)
        return candidate
    if rule.frequency is Frequency.WEEKLY:
        days = tuple(sorted(set(rule.by_weekday or (moment.weekday(),))))
        monday = (moment - timedelta(days=moment.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for offset in range(7):
            candidate_date = monday + timedelta(days=offset)
            if candidate_date.weekday() in days:
                candidate = _at_time(candidate_date, rule)
                if candidate.timestamp() >= lower:
                    return candidate
        return _at_time(monday + timedelta(weeks=rule.interval, days=days[0]), rule)
    candidate = _at_time(_month_day(moment.year, moment.month, rule, moment.day), rule)
    while candidate.timestamp() < lower:
        month_index = candidate.month - 1 + rule.interval
        year = candidate.year + month_index // 12
        month = month_index % 12 + 1
        candidate = _at_time(_month_day(year, month, rule, moment.day), rule)
    return candidate


def _advance(rule: RecurrenceRule, moment: datetime, seed_day: int) -> datetime:
    """Return the next candidate after ``moment`` for the rule's frequency."""
    if rule.frequency is Frequency.HOURLY:
        return moment + timedelta(hours=rule.interval)
    if rule.frequency is Frequency.DAILY:
        return _at_time(moment + timedelta(days=rule.interval), rule)
    if rule.frequency is Frequency.WEEKLY:
        days = tuple(sorted(set(rule.by_weekday or (moment.weekday(),))))
        index = days.index(moment.weekday()) if moment.weekday() in days else -1
        if index + 1 < len(days):
            return _at_time(moment + timedelta(days=days[index + 1] - moment.weekday()), rule)
        return _at_time(
            moment + timedelta(weeks=rule.interval, days=days[0] - moment.weekday()), rule
        )
    month_index = moment.month - 1 + rule.interval
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    return _at_time(_month_day(year, month, rule, seed_day), rule)


def occurrences(
    rule: RecurrenceRule,
    after: float,
    before: float,
    *,
    limit: int = 100,
) -> tuple[float, ...]:
    """Expand a rule into ordered UTC timestamps inside a half-open window."""
    if limit < 0:
        raise RecurrenceError("Occurrence limit cannot be negative", path="recurrence.limit")
    if before <= after or limit == 0:
        return ()
    lower = max(after, rule.start_at)
    upper = min(before, rule.end_at + 1) if rule.end_at else before
    if upper <= lower:
        return ()
    seed_day = _utc(lower).day
    moment = _first_candidate(rule, lower)
    results: list[float] = []
    for _ in range(_MAX_PERIODS):
        timestamp = moment.timestamp()
        if timestamp >= upper:
            break
        if timestamp > after:
            if rule.count and len(results) >= rule.count:
                break
            results.append(timestamp)
            if len(results) >= limit:
                break
        moment = _advance(rule, moment, seed_day)
    return tuple(results)


def next_occurrence(rule: RecurrenceRule, after: float) -> float | None:
    """Return the next timestamp after ``after``, or ``None`` when exhausted."""
    horizon = after + 370 * 86_400 * (max(1, rule.interval) + 1)
    found = occurrences(rule, after, horizon, limit=1)
    return found[0] if found else None


def humanize(rule: RecurrenceRule) -> str:
    """Return a short human-readable description of a rule."""
    interval = "" if rule.interval == 1 else f" every {rule.interval}"
    if rule.frequency is Frequency.HOURLY:
        text = f"Hourly{interval}"
    elif rule.frequency is Frequency.DAILY:
        text = f"Daily{interval}"
    elif rule.frequency is Frequency.WEEKLY:
        days = ",".join(_WEEKDAY_NAMES[day] for day in sorted(set(rule.by_weekday)))
        text = f"Weekly{interval}" + (f" on {days}" if days else "")
    else:
        text = f"Monthly{interval}" + (f" on day {rule.by_month_day}" if rule.by_month_day else "")
    return f"{text} at {rule.hour:02d}:{rule.minute:02d} UTC"


def schedule_label(timestamp: float) -> str:
    """Format an occurrence for display."""
    return _utc(timestamp).strftime("%Y-%m-%d %H:%M UTC")
