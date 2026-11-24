"""RedScribe V3 — universal contracts for the 15-branch program."""

from __future__ import annotations

from redscribe.v3.capabilities import (
    ALL_CAPABILITIES,
    Capabilities,
    CapabilityError,
    default_capabilities,
)
from redscribe.v3.clock import Clock, FixedClock, SystemClock, iso_from_timestamp
from redscribe.v3.config import V3Config, default_config
from redscribe.v3.entities import (
    ENTITY_KINDS,
    EntityId,
    EntityKind,
    EntityKindRegistry,
    EntityLink,
    EntityRecord,
    EntityRef,
    EntityService,
    EntityStatus,
    LinkGraph,
    LinkKind,
)
from redscribe.v3.events import (
    DomainEvent,
    EventBus,
    EventFilter,
    EventRecord,
    EventReplay,
    EventSeverity,
    MemoryOutbox,
    OutboxWriter,
    RedactionPolicy,
    make_event,
)
from redscribe.v3.migrations import SCHEMA_VERSION, MigrationChain, chain

VERSION = "3.0.0"

__all__ = [
    "ALL_CAPABILITIES",
    "ENTITY_KINDS",
    "SCHEMA_VERSION",
    "VERSION",
    "Capabilities",
    "CapabilityError",
    "Clock",
    "DomainEvent",
    "EntityId",
    "EntityKind",
    "EntityKindRegistry",
    "EntityLink",
    "EntityRecord",
    "EntityRef",
    "EntityService",
    "EntityStatus",
    "EventBus",
    "EventFilter",
    "EventRecord",
    "EventReplay",
    "EventSeverity",
    "FixedClock",
    "LinkGraph",
    "LinkKind",
    "MemoryOutbox",
    "MigrationChain",
    "OutboxWriter",
    "RedactionPolicy",
    "SystemClock",
    "V3Config",
    "chain",
    "default_capabilities",
    "default_config",
    "iso_from_timestamp",
    "make_event",
]
