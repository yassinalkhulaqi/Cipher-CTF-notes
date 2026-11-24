"""Typed domain event system for RedScribe V3."""

from __future__ import annotations

from redscribe.v3.events.bus import EventBus, EventBusError
from redscribe.v3.events.filters import (
    EventFilter,
    any_of,
    combine,
    count_by_kind,
    latest_per_subject,
    payload_values,
)
from redscribe.v3.events.outbox import (
    JsonFileOutbox,
    MemoryOutbox,
    OutboxStore,
    OutboxWriter,
)
from redscribe.v3.events.redaction import (
    RedactionPolicy,
    is_sensitive_key,
    redact_payload,
    redact_text,
)
from redscribe.v3.events.replay import (
    EventReplay,
    ReplayResult,
    append_reducer,
    count_reducer,
)
from redscribe.v3.events.types import DomainEvent, EventRecord, EventSeverity, make_event

__all__ = [
    "DomainEvent",
    "EventBus",
    "EventBusError",
    "EventFilter",
    "EventRecord",
    "EventReplay",
    "EventSeverity",
    "JsonFileOutbox",
    "MemoryOutbox",
    "OutboxStore",
    "OutboxWriter",
    "RedactionPolicy",
    "ReplayResult",
    "any_of",
    "append_reducer",
    "combine",
    "count_by_kind",
    "count_reducer",
    "is_sensitive_key",
    "latest_per_subject",
    "make_event",
    "payload_values",
    "redact_payload",
    "redact_text",
]
