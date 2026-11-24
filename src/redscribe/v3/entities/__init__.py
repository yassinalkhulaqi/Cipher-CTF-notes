"""Universal entity contracts for RedScribe V3."""

from __future__ import annotations

from redscribe.v3.entities.ids import (
    is_valid_value,
    new_id,
    new_value,
    short_form,
    slugify,
    try_parse,
)
from redscribe.v3.entities.links import DuplicateLinkError, LinkGraph
from redscribe.v3.entities.registry import (
    EntityKindRegistry,
    KindSpec,
    default_registry,
)
from redscribe.v3.entities.service import EntityNotFoundError, EntityService
from redscribe.v3.entities.types import (
    ENTITY_KINDS,
    LINK_KINDS,
    EntityId,
    EntityKind,
    EntityLink,
    EntityRecord,
    EntityRef,
    EntityStatus,
    LinkKind,
)

__all__ = [
    "ENTITY_KINDS",
    "LINK_KINDS",
    "DuplicateLinkError",
    "EntityId",
    "EntityKind",
    "EntityKindRegistry",
    "EntityLink",
    "EntityNotFoundError",
    "EntityRecord",
    "EntityRef",
    "EntityService",
    "EntityStatus",
    "KindSpec",
    "LinkGraph",
    "LinkKind",
    "default_registry",
    "is_valid_value",
    "new_id",
    "new_value",
    "short_form",
    "slugify",
    "try_parse",
]
