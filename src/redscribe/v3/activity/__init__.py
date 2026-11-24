"""Event-sourced activity stream for RedScribe V3.

The package projects B00 domain events into a linkable stream, applies a small
filter DSL, builds timezone-safe digests and retrospectives, tracks since-last-
visit state, and redacts sensitive payload fields before display.
"""

from __future__ import annotations

from redscribe.v3.activity.digest import (
    DigestBuilder,
    build_digests,
    digest_label,
    digest_summary,
    find_digest,
)
from redscribe.v3.activity.filters import (
    FILTER_KEYS,
    ActivityFilter,
    any_filter,
    combine_filters,
    filter_definitions,
    make_filter_chips,
    parse_query,
    validate_query,
)
from redscribe.v3.activity.models import (
    DENSITY_MODES,
    DIGEST_PERIODS,
    ActivityEntry,
    DateGroup,
    DensityMode,
    Digest,
    DigestCollection,
    DigestInterval,
    FacetCounts,
    FilterChip,
    FilterDefinition,
    FilterValidation,
    JumpTarget,
    RedactionReport,
    RetrospectiveSummary,
    SinceLastVisit,
    StreamResult,
    VisitMarker,
)
from redscribe.v3.activity.projections import (
    ActivityProjector,
    event_summary,
    event_title,
    payload_tags,
)
from redscribe.v3.activity.redaction import (
    DEFAULT_ALLOWED_KEYS,
    ActivityRedactor,
    RedactionRule,
    redact_for_display,
    summarize_redactions,
)
from redscribe.v3.activity.retrospective import (
    RetrospectiveBuilder,
    build_retrospective,
    retrospective_headline,
    retrospective_stats,
    streak_lengths,
)
from redscribe.v3.activity.service import ActivityService, ActivityServiceError
from redscribe.v3.activity.timezone import (
    TimezoneError,
    bucket_key,
    day_key,
    period_bounds,
    resolve_timezone,
    week_key,
    window_keys,
)
from redscribe.v3.activity.visits import (
    VisitError,
    VisitTracker,
    since_last_visit,
)

__all__ = [
    "DEFAULT_ALLOWED_KEYS",
    "DENSITY_MODES",
    "DIGEST_PERIODS",
    "FILTER_KEYS",
    "ActivityEntry",
    "ActivityFilter",
    "ActivityProjector",
    "ActivityRedactor",
    "ActivityService",
    "ActivityServiceError",
    "DateGroup",
    "DensityMode",
    "Digest",
    "DigestBuilder",
    "DigestCollection",
    "DigestInterval",
    "FacetCounts",
    "FilterChip",
    "FilterDefinition",
    "FilterValidation",
    "JumpTarget",
    "RedactionReport",
    "RedactionRule",
    "RetrospectiveBuilder",
    "RetrospectiveSummary",
    "SinceLastVisit",
    "StreamResult",
    "TimezoneError",
    "VisitError",
    "VisitMarker",
    "VisitTracker",
    "any_filter",
    "bucket_key",
    "build_digests",
    "build_retrospective",
    "combine_filters",
    "day_key",
    "digest_label",
    "digest_summary",
    "event_summary",
    "event_title",
    "filter_definitions",
    "find_digest",
    "make_filter_chips",
    "parse_query",
    "payload_tags",
    "period_bounds",
    "redact_for_display",
    "resolve_timezone",
    "retrospective_headline",
    "retrospective_stats",
    "since_last_visit",
    "streak_lengths",
    "summarize_redactions",
    "validate_query",
    "week_key",
    "window_keys",
]
