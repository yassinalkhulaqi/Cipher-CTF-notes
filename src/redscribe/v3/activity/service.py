"""Facade service that assembles the activity stream from B00 events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v3.activity.digest import DigestBuilder
from redscribe.v3.activity.filters import (
    ActivityFilter,
    filter_definitions,
    parse_query,
    validate_query,
)
from redscribe.v3.activity.models import (
    DEFAULT_TIMEZONE,
    DENSITY_COMFORTABLE,
    PERIOD_DAILY,
    PERIOD_WEEKLY,
    ActivityEntry,
    Digest,
    DigestCollection,
    FacetCounts,
    FilterValidation,
    JumpTarget,
    RedactionReport,
    RetrospectiveSummary,
    SinceLastVisit,
    StreamResult,
    VisitMarker,
)
from redscribe.v3.activity.projections import ActivityProjector
from redscribe.v3.activity.redaction import ActivityRedactor
from redscribe.v3.activity.retrospective import RetrospectiveBuilder
from redscribe.v3.activity.timezone import bucket_key, resolve_timezone
from redscribe.v3.activity.visits import VisitTracker
from redscribe.v3.api.pagination import PageRequest, filter_hash, paginate
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.config import V3Config, default_config
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import EventRecord


class ActivityServiceError(ValueError):
    """Raised for invalid activity service requests."""


class ActivityService:
    """Owns projections, filters, digests, visits, and retrospectives."""

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        redactor: ActivityRedactor | None = None,
        config: V3Config | None = None,
        highlight_limit: int = 5,
    ) -> None:
        self._clock: Clock = clock or SystemClock()
        self._config = config or default_config
        self._bus = bus or EventBus(clock=self._clock)
        self._timezone = timezone
        resolve_timezone(timezone)
        self._redactor = redactor or ActivityRedactor(enabled=self._config.redact_activity)
        self._projector = ActivityProjector(timezone=timezone, redactor=self._redactor)
        self._digests = DigestBuilder(timezone=timezone)
        self._retrospective = RetrospectiveBuilder(timezone=timezone)
        self._visits = VisitTracker(clock=self._clock)
        self._entries: dict[int, ActivityEntry] = {}
        self._reports: dict[int, RedactionReport] = {}
        self._highlight_limit = max(0, highlight_limit)

    @property
    def bus(self) -> EventBus:
        """The underlying event bus."""
        return self._bus

    @property
    def timezone(self) -> str:
        """Configured display timezone."""
        return self._timezone

    @property
    def projector(self) -> ActivityProjector:
        """Projection helper."""
        return self._projector

    def entries(self) -> tuple[ActivityEntry, ...]:
        """Return all projected entries in sequence order."""
        return tuple(self._entries[key] for key in sorted(self._entries))

    def entry(self, sequence: int) -> ActivityEntry | None:
        """Look up an entry by event sequence."""
        return self._entries.get(sequence)

    def jump_to(self, sequence: int) -> JumpTarget | None:
        """Return the resolver target attached to an entry."""
        entry = self.entry(sequence)
        return entry.jump if entry is not None else None

    def ingest(self, record: EventRecord) -> ActivityEntry:
        """Project and store one event record (idempotent by sequence)."""
        existing = self._entries.get(record.sequence)
        if existing is not None:
            return existing
        entry = self._projector.entry(record)
        self._entries[record.sequence] = entry
        self._reports[record.sequence] = self._redactor.last_report
        return entry

    def observe(self, record: EventRecord) -> None:
        """Bus-compatible subscriber wrapper around :meth:`ingest`."""
        self.ingest(record)

    def install_subscriber(self) -> None:
        """Start projecting every bus event into this service."""
        self._bus.subscribe_all(self.observe)

    def ingest_all(self, records: Iterable[EventRecord]) -> int:
        """Ingest records, returning how many were newly projected."""
        before = len(self._entries)
        for record in records:
            self.ingest(record)
        return len(self._entries) - before

    def sync_from_bus(self) -> int:
        """Project all records currently held by the bus."""
        return self.ingest_all(self._bus.records())

    def stream(
        self,
        event_filter: ActivityFilter | None = None,
        *,
        query: str = "",
        offset: int = 0,
        size: int | None = None,
        density: str = DENSITY_COMFORTABLE,
        warnings: Sequence[str] = (),
    ) -> StreamResult:
        """Return a filtered, paginated, date-grouped activity stream."""
        active_filter = event_filter or ActivityFilter()
        page_size = self._config.page_size if size is None else size
        request = PageRequest.parse(offset=offset, size=page_size)
        ordered = tuple(
            sorted(self._entries.values(), key=lambda item: item.sequence, reverse=True)
        )
        matched = active_filter.apply(ordered)
        digest = filter_hash(query, active_filter.kinds)
        window, page, _cursor = paginate(matched, request, filter_hash=digest)
        facets = self._projector.facets(matched)
        projector = self._projector
        if density != projector.density:
            projector = ActivityProjector(
                timezone=self._timezone, redactor=self._redactor, density=density
            )
        result = projector.stream(
            window,
            total=len(matched),
            query=query,
            page=page,
            warnings=tuple(warnings),
        )
        return _with_facets(result, facets)

    def digest(
        self,
        period: str = PERIOD_DAILY,
        *,
        anchor: float | None = None,
        generated_at: float | None = None,
        highlight_limit: int | None = None,
    ) -> DigestCollection:
        """Build daily or weekly digests for all projected entries."""
        normalized = period.strip().casefold()
        if normalized not in (PERIOD_DAILY, PERIOD_WEEKLY):
            raise ActivityServiceError(f"Unknown digest period: {period}")
        moment = self._clock.now_timestamp() if generated_at is None else generated_at
        return self._digests.build(
            self.entries(),
            period=normalized,
            generated_at=moment,
            highlight_limit=self._highlight_limit if highlight_limit is None else highlight_limit,
        )

    def digest_at(
        self,
        anchor: float,
        *,
        period: str = PERIOD_DAILY,
        generated_at: float | None = None,
    ) -> Digest | None:
        """Return the digest covering a specific timestamp."""
        moment = self._clock.now_timestamp() if generated_at is None else generated_at
        return self._digests.for_anchor(
            self.entries(),
            period=period,
            anchor=anchor,
            generated_at=moment,
            highlight_limit=self._highlight_limit,
        )

    def since(self, identity: str, *, limit: int | None = None) -> SinceLastVisit:
        """Return activity new since an identity's last visit."""
        return self._visits.since(identity, self.entries(), limit=limit)

    def mark_visit(
        self,
        identity: str,
        *,
        timestamp: float | None = None,
        sequence: int | None = None,
        note: str = "",
    ) -> VisitMarker:
        """Mark the current stream position as seen for an identity."""
        marker_sequence = max(self._entries, default=0) if sequence is None else sequence
        return self._visits.mark(identity, timestamp=timestamp, sequence=marker_sequence, note=note)

    def retrospective(
        self,
        *,
        start: float,
        end: float,
        top_limit: int = 5,
        highlight_limit: int | None = None,
    ) -> RetrospectiveSummary:
        """Build a retrospective for ``[start, end)``."""
        if end <= start:
            raise ActivityServiceError("Retrospective end must be after start")
        return self._retrospective.build(
            self.entries(),
            start=start,
            end=end,
            top_limit=top_limit,
            highlight_limit=self._highlight_limit if highlight_limit is None else highlight_limit,
        )

    def validate(self, query: str) -> FilterValidation:
        """Validate a filter query string."""
        return validate_query(query)

    def filters(self) -> dict[str, Any]:
        """Return filter DSL metadata for the UI."""
        return {
            "keys": [definition.as_dict() for definition in filter_definitions()],
            "operators": ["include", "exclude"],
            "grammar": "key:value with optional '-' prefix; free text is allowed",
        }

    def redact(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Redact a payload for display."""
        return self._redactor.redact(payload)

    def redaction_report(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Redact a payload and return only the report."""
        _cleaned, report = self._redactor.redact_with_report(payload)
        return report.as_dict()

    def last_redaction_report(self) -> dict[str, Any]:
        """Return the report produced by the most recent redaction."""
        return self._redactor.last_report.as_dict()

    def redaction_totals(self) -> RedactionReport:
        """Aggregate redaction reports across all ingested entries."""
        total = RedactionReport()
        for report in self._reports.values():
            total = total.merge(report)
        return total

    def stats(self) -> dict[str, Any]:
        """Return a compact activity dashboard snapshot."""
        entries = self.entries()
        kinds: dict[str, int] = {}
        severities: dict[str, int] = {}
        for entry in entries:
            kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
            severities[entry.severity] = severities.get(entry.severity, 0) + 1
        return {
            "entries": len(entries),
            "sequences": sorted(self._entries),
            "kinds": dict(sorted(kinds.items())),
            "severities": dict(sorted(severities.items())),
            "visitors": list(self._visits.identities()),
            "bus_errors": len(self._bus.errors()),
            "redactions": self.redaction_totals().as_dict(),
            "timezone": self._timezone,
        }

    def reset(self) -> None:
        """Drop projected state and visit markers."""
        self._entries.clear()
        self._reports.clear()
        self._visits.clear()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe service snapshot."""
        return {
            "timezone": self._timezone,
            "stats": self.stats(),
            "entries": [entry.as_dict() for entry in self.entries()],
        }

    def active_day_keys(self, period: str = PERIOD_DAILY) -> tuple[str, ...]:
        """Return distinct bucket keys touched by projected entries."""
        return tuple(
            sorted(
                {
                    bucket_key(entry.timestamp, period, resolve_timezone(self._timezone))
                    for entry in self.entries()
                }
            )
        )


def _with_facets(result: StreamResult, facets: FacetCounts) -> StreamResult:
    """Replace facet counts on a stream result without mutating it."""
    return StreamResult(
        entries=result.entries,
        total=result.total,
        groups=result.groups,
        facets=facets,
        page=result.page,
        query=result.query,
        density=result.density,
        timezone=result.timezone,
        warnings=result.warnings,
    )


def parse_stream_query(query: str) -> tuple[ActivityFilter, tuple[str, ...]]:
    """Parse a query into a filter and any validation errors."""
    event_filter, _chips, errors = parse_query(query)
    return event_filter, errors
