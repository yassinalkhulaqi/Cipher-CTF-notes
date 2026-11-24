"""Retrospective summaries over an explicit activity window."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from redscribe.v3.activity.models import (
    DEFAULT_TIMEZONE,
    ActivityEntry,
    DayCount,
    RetrospectiveSummary,
)
from redscribe.v3.activity.timezone import day_key, resolve_timezone, week_key
from redscribe.v3.clock import iso_from_timestamp

DEFAULT_TOP_LIMIT = 5
DEFAULT_HIGHLIGHT_LIMIT = 5


def _top(counts: dict[str, int], limit: int) -> tuple[tuple[str, int], ...]:
    """Rank counts by frequency then key for deterministic output."""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(ordered[: max(0, limit)])


def streak_lengths(date_keys: Iterable[str]) -> tuple[int, int]:
    """Return ``(longest, trailing)`` consecutive-day streaks.

    The trailing streak ends on the most recent active day in the window.
    """
    keys = sorted(set(date_keys))
    if not keys:
        return 0, 0
    longest = 1
    current = 1
    for index in range(1, len(keys)):
        previous = date.fromisoformat(keys[index - 1])
        current_date = date.fromisoformat(keys[index])
        current = current + 1 if current_date - previous == timedelta(days=1) else 1
        longest = max(longest, current)
    trailing = 0
    expected = date.fromisoformat(keys[-1])
    for key in reversed(keys):
        if date.fromisoformat(key) != expected:
            break
        trailing += 1
        expected -= timedelta(days=1)
    return longest, trailing


class RetrospectiveBuilder:
    """Builds deterministic retrospective rollups."""

    def __init__(self, *, timezone: str = DEFAULT_TIMEZONE) -> None:
        self._timezone_name = timezone
        self._zone = resolve_timezone(timezone)

    def build(
        self,
        entries: Iterable[ActivityEntry],
        *,
        start: float,
        end: float,
        top_limit: int = DEFAULT_TOP_LIMIT,
        highlight_limit: int = DEFAULT_HIGHLIGHT_LIMIT,
    ) -> RetrospectiveSummary:
        """Summarize activity in ``[start, end)``."""
        if end <= start:
            raise ValueError("Retrospective end must be after start")
        rows = tuple(entry for entry in entries if start <= entry.timestamp < end)
        daily: dict[str, int] = {}
        kinds: dict[str, int] = {}
        actors: dict[str, int] = {}
        subjects: dict[str, int] = {}
        severities: dict[str, int] = {}
        weeks: set[str] = set()
        for entry in rows:
            day = day_key(entry.timestamp, self._zone)
            daily[day] = daily.get(day, 0) + 1
            weeks.add(week_key(entry.timestamp, self._zone))
            kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
            actors[entry.actor] = actors.get(entry.actor, 0) + 1
            if entry.subject_ref:
                subjects[entry.subject_ref] = subjects.get(entry.subject_ref, 0) + 1
            severities[entry.severity] = severities.get(entry.severity, 0) + 1
        daily_counts = tuple(DayCount(key, daily[key]) for key in sorted(daily))
        busiest = max(daily_counts, key=lambda item: (item.count, item.date_key), default=None)
        highlights = tuple(
            sorted(rows, key=lambda item: (item.severity_rank, item.sequence), reverse=True)[
                : max(0, highlight_limit)
            ]
        )
        longest, trailing = streak_lengths(daily)
        return RetrospectiveSummary(
            start=start,
            end=end,
            iso_start=iso_from_timestamp(start),
            iso_end=iso_from_timestamp(end),
            timezone=self._timezone_name,
            total_events=len(rows),
            active_days=len(daily),
            active_weeks=len(weeks),
            longest_streak=longest,
            trailing_streak=trailing,
            busiest_day=busiest,
            top_kinds=_top(kinds, top_limit),
            top_actors=_top(actors, top_limit),
            top_subjects=_top(subjects, top_limit),
            severity_mix=dict(sorted(severities.items())),
            highlights=highlights,
            daily_counts=daily_counts,
        )


def build_retrospective(
    entries: Iterable[ActivityEntry],
    *,
    start: float,
    end: float,
    timezone: str = DEFAULT_TIMEZONE,
    top_limit: int = DEFAULT_TOP_LIMIT,
    highlight_limit: int = DEFAULT_HIGHLIGHT_LIMIT,
) -> RetrospectiveSummary:
    """Convenience wrapper around :class:`RetrospectiveBuilder`."""
    return RetrospectiveBuilder(timezone=timezone).build(
        entries,
        start=start,
        end=end,
        top_limit=top_limit,
        highlight_limit=highlight_limit,
    )


def retrospective_headline(summary: RetrospectiveSummary) -> str:
    """Render a one-line headline for a retrospective card."""
    top = summary.top_kinds[0][0] if summary.top_kinds else "activity"
    return (
        f"{summary.total_events} events across {summary.active_days} active days; "
        f"most frequent: {top}"
    )


def retrospective_stats(summary: RetrospectiveSummary) -> dict[str, Any]:
    """Return compact, display-ready retrospective stats."""
    return {
        "events": summary.total_events,
        "days": summary.active_days,
        "weeks": summary.active_weeks,
        "longest_streak": summary.longest_streak,
        "trailing_streak": summary.trailing_streak,
        "headline": retrospective_headline(summary),
    }
