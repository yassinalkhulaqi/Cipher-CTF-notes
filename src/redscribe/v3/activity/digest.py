"""Timezone-safe daily and weekly digest aggregation.

Digest boundaries are anchored to an explicit IANA timezone and generated-at
timestamp supplied by the caller, so the same events always produce the same
digest regardless of the machine's local clock.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from redscribe.v3.activity.models import (
    DEFAULT_TIMEZONE,
    DIGEST_PERIODS,
    PERIOD_DAILY,
    PERIOD_WEEKLY,
    ActivityEntry,
    Digest,
    DigestCollection,
    DigestSection,
)
from redscribe.v3.activity.timezone import (
    bucket_key,
    bucket_label,
    period_bounds,
    resolve_timezone,
)
from redscribe.v3.clock import iso_from_timestamp

DEFAULT_HIGHLIGHT_LIMIT = 5


def _section_title(kind: str) -> str:
    """Humanize an event kind for a digest section heading."""
    parts = [part for part in kind.replace("-", "_").replace(".", "_").split("_") if part]
    return " ".join(part.title() for part in parts) if parts else "Other"


def _count(values: Iterable[str]) -> dict[str, int]:
    """Count occurrences of each string value."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


class DigestBuilder:
    """Builds deterministic digests from projected activity entries."""

    def __init__(self, *, timezone: str = DEFAULT_TIMEZONE) -> None:
        self._timezone_name = timezone
        self._zone = resolve_timezone(timezone)

    @property
    def timezone(self) -> str:
        """Configured timezone name."""
        return self._timezone_name

    def build(
        self,
        entries: Iterable[ActivityEntry],
        *,
        period: str = PERIOD_DAILY,
        generated_at: float,
        highlight_limit: int = DEFAULT_HIGHLIGHT_LIMIT,
    ) -> DigestCollection:
        """Group entries into ordered digests for a period."""
        normalized = period.strip().casefold()
        if normalized not in DIGEST_PERIODS:
            raise ValueError(f"Unknown digest period: {period}")
        rows = tuple(entries)
        groups: dict[str, list[ActivityEntry]] = {}
        for entry in rows:
            groups.setdefault(bucket_key(entry.timestamp, normalized, self._zone), []).append(entry)
        digests: list[Digest] = []
        for key in sorted(groups, reverse=True):
            bucket = tuple(sorted(groups[key], key=lambda item: item.sequence))
            digests.append(
                self._one(
                    key=key,
                    entries=bucket,
                    period=normalized,
                    generated_at=generated_at,
                    highlight_limit=highlight_limit,
                )
            )
        return DigestCollection(
            period=normalized,
            timezone=self._timezone_name,
            generated_at=generated_at,
            digests=tuple(digests),
            total_events=len(rows),
        )

    def for_anchor(
        self,
        entries: Iterable[ActivityEntry],
        *,
        period: str = PERIOD_DAILY,
        anchor: float,
        generated_at: float,
        highlight_limit: int = DEFAULT_HIGHLIGHT_LIMIT,
    ) -> Digest | None:
        """Return the single digest containing ``anchor``, if it has entries."""
        key = bucket_key(anchor, period, self._zone)
        collection = self.build(
            entries,
            period=period,
            generated_at=generated_at,
            highlight_limit=highlight_limit,
        )
        return find_digest(collection, key)

    def _one(
        self,
        *,
        key: str,
        entries: tuple[ActivityEntry, ...],
        period: str,
        generated_at: float,
        highlight_limit: int,
    ) -> Digest:
        first = min(entry.timestamp for entry in entries)
        start, end, bound_key, label = period_bounds(first, period, self._zone)
        by_kind: dict[str, list[ActivityEntry]] = {}
        for entry in entries:
            by_kind.setdefault(entry.kind, []).append(entry)
        sections = tuple(
            DigestSection(
                title=_section_title(kind),
                kind=kind,
                entries=tuple(sorted(rows, key=lambda item: item.sequence, reverse=True)),
            )
            for kind, rows in sorted(by_kind.items())
        )
        highlights = tuple(
            sorted(
                entries,
                key=lambda item: (item.severity_rank, item.sequence),
                reverse=True,
            )[: max(0, highlight_limit)]
        )
        return Digest(
            period=period,
            key=bound_key or key,
            label=label,
            start=start,
            end=end,
            iso_start=iso_from_timestamp(start),
            iso_end=iso_from_timestamp(end),
            timezone=self._timezone_name,
            entries=entries,
            sections=sections,
            highlights=highlights,
            counts=_count(entry.kind for entry in entries),
            actor_counts=_count(entry.actor for entry in entries),
        )


def build_digests(
    entries: Iterable[ActivityEntry],
    *,
    period: str = PERIOD_DAILY,
    timezone: str = DEFAULT_TIMEZONE,
    generated_at: float,
    highlight_limit: int = DEFAULT_HIGHLIGHT_LIMIT,
) -> DigestCollection:
    """Convenience wrapper around :class:`DigestBuilder`."""
    return DigestBuilder(timezone=timezone).build(
        entries,
        period=period,
        generated_at=generated_at,
        highlight_limit=highlight_limit,
    )


def find_digest(collection: DigestCollection, key: str) -> Digest | None:
    """Find a digest by bucket key."""
    for digest in collection.digests:
        if digest.key == key:
            return digest
    return None


def digest_label(timestamp: float, period: str, timezone: str = DEFAULT_TIMEZONE) -> str:
    """Render the label for a timestamp's digest bucket."""
    zone = resolve_timezone(timezone)
    normalized = period.strip().casefold()
    if normalized in (PERIOD_DAILY, PERIOD_WEEKLY):
        return bucket_label(timestamp, normalized, zone)
    raise ValueError(f"Unknown digest period: {period}")


def digest_summary(digest: Digest) -> dict[str, Any]:
    """Return compact presentation data for a digest card."""
    return {
        "key": digest.key,
        "label": digest.label,
        "count": digest.entry_count,
        "top_kind": max(digest.counts, key=lambda key: digest.counts[key]) if digest.counts else "",
        "highlight": digest.highlights[0].title if digest.highlights else "",
    }
