"""Projection of durable event records into activity stream entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from redscribe.v3.activity.models import (
    DEFAULT_TIMEZONE,
    DENSITY_COMFORTABLE,
    PERIOD_DAILY,
    ActivityEntry,
    DateGroup,
    FacetCounts,
    JumpTarget,
    StreamResult,
)
from redscribe.v3.activity.redaction import ActivityRedactor
from redscribe.v3.activity.timezone import (
    bucket_key,
    bucket_label,
    day_key,
    local_datetime,
    resolve_timezone,
    week_key,
)
from redscribe.v3.api.envelope import PageMeta
from redscribe.v3.clock import iso_from_timestamp
from redscribe.v3.events.types import EventRecord

SUMMARY_KEYS: tuple[str, ...] = (
    "title",
    "name",
    "label",
    "message",
    "summary",
    "description",
    "stage",
)
MAX_SUMMARY_LENGTH = 240


class ActivityProjectorError(ValueError):
    """Raised when an event record cannot be projected."""


def event_title(kind: str) -> str:
    """Turn an event kind into a human-readable activity title."""
    parts = [part for part in kind.replace("-", "_").split(".") if part]
    if not parts:
        raise ActivityProjectorError("Event kind cannot be empty")
    words = [part.replace("_", " ").strip().title() for part in parts]
    return " ".join(words) if len(words) == 1 else f"{words[0]} {' '.join(words[1:])}"


def event_summary(payload: Mapping[str, Any]) -> str:
    """Extract the most useful short summary from an event payload."""
    for key in SUMMARY_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return text[:MAX_SUMMARY_LENGTH]
    return ""


def payload_tags(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Normalize a payload tag list into stable display tags."""
    raw = payload.get("tags", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    tags: dict[str, str] = {}
    for item in raw:
        text = str(item).strip().casefold().lstrip("#")
        if text and text not in tags:
            tags[text] = text
    return tuple(tags.values())


class ActivityProjector:
    """Projects event records into redacted, linkable stream entries."""

    def __init__(
        self,
        *,
        timezone: str = DEFAULT_TIMEZONE,
        redactor: ActivityRedactor | None = None,
        density: str = DENSITY_COMFORTABLE,
    ) -> None:
        self._timezone_name = timezone
        self._zone = resolve_timezone(timezone)
        self._redactor = redactor or ActivityRedactor()
        self._density = density

    @property
    def timezone(self) -> str:
        """Configured timezone name."""
        return self._timezone_name

    @property
    def redactor(self) -> ActivityRedactor:
        """Redactor used by this projector."""
        return self._redactor

    @property
    def density(self) -> str:
        """Default density for rendered entries."""
        return self._density

    def entry(self, record: EventRecord) -> ActivityEntry:
        """Project one event record into an activity entry."""
        payload = self._redactor.redact(record.event.payload)
        report = self._redactor.last_report
        label = event_summary(payload)
        jump: JumpTarget | None = None
        if record.subject_ref:
            jump = JumpTarget.for_ref(record.subject_ref, label)
        return ActivityEntry(
            sequence=record.sequence,
            kind=record.kind,
            title=event_title(record.kind),
            summary=label,
            actor=record.event.actor,
            severity=record.event.severity.value,
            timestamp=record.timestamp,
            iso_timestamp=iso_from_timestamp(record.timestamp),
            date_key=day_key(record.timestamp, self._zone),
            week_key=week_key(record.timestamp, self._zone),
            subject_ref=record.subject_ref,
            payload=payload,
            jump=jump,
            correlation_id=record.event.correlation_id,
            request_id=record.request_id,
            tags=payload_tags(payload),
            redactions=report.redacted_keys,
        )

    def entries(self, records: Iterable[EventRecord]) -> tuple[ActivityEntry, ...]:
        """Project a sequence of records in stable sequence order."""
        return tuple(
            self.entry(record) for record in sorted(records, key=lambda item: item.sequence)
        )

    def group(
        self,
        entries: Iterable[ActivityEntry],
        *,
        period: str = PERIOD_DAILY,
    ) -> tuple[DateGroup, ...]:
        """Group entries into date buckets, newest bucket first."""
        buckets: dict[str, list[ActivityEntry]] = {}
        labels: dict[str, str] = {}
        for entry in entries:
            key = bucket_key(entry.timestamp, period, self._zone)
            buckets.setdefault(key, []).append(entry)
            labels.setdefault(key, bucket_label(entry.timestamp, period, self._zone))
        groups: list[DateGroup] = []
        for key in sorted(buckets, reverse=True):
            rows = tuple(sorted(buckets[key], key=lambda item: item.sequence, reverse=True))
            groups.append(DateGroup(key=key, label=labels[key], entries=rows, period=period))
        return tuple(groups)

    def facets(self, entries: Iterable[ActivityEntry]) -> FacetCounts:
        """Build filter-chip counts from projected entries."""
        kinds: dict[str, int] = {}
        actors: dict[str, int] = {}
        severities: dict[str, int] = {}
        subjects: dict[str, int] = {}
        for entry in entries:
            kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
            actors[entry.actor] = actors.get(entry.actor, 0) + 1
            severities[entry.severity] = severities.get(entry.severity, 0) + 1
            if entry.subject_ref:
                subjects[entry.subject_ref] = subjects.get(entry.subject_ref, 0) + 1
        return FacetCounts(kinds=kinds, actors=actors, severities=severities, subjects=subjects)

    def stream(
        self,
        entries: tuple[ActivityEntry, ...],
        *,
        total: int,
        query: str = "",
        page: PageMeta | None = None,
        warnings: tuple[str, ...] = (),
    ) -> StreamResult:
        """Assemble a full stream result from a page of entries."""
        return StreamResult(
            entries=entries,
            total=total,
            groups=self.group(entries),
            facets=self.facets(entries),
            page=page,
            query=query,
            density=self._density,
            timezone=self._timezone_name,
            warnings=warnings,
        )

    def local_iso(self, timestamp: float) -> str:
        """Render a timestamp in the configured local timezone."""
        return local_datetime(timestamp, self._zone).isoformat()
