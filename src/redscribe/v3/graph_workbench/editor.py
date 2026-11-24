"""Relationship editor with bounded, deterministic undo/redo history.

The editor is the only component allowed to mutate the universal
:class:`~redscribe.v3.entities.LinkGraph` owned by ``EntityService``. Each
mutation is recorded as a reversible command and emitted as a V3 domain event
for the activity stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.capabilities import CAP_GRAPH, Capabilities
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities import (
    DuplicateLinkError,
    EntityId,
    EntityLink,
    EntityService,
    LinkKind,
)
from redscribe.v3.events import DomainEvent, EventBus, make_event

DEFAULT_HISTORY = 100

EDIT_ADD = "add"
EDIT_REMOVE = "remove"
EDIT_UPDATE = "update"


def parse_entity_ref(value: EntityId | str) -> EntityId:
    """Accept either a typed id or its canonical wire form."""
    if isinstance(value, EntityId):
        return value
    return EntityId.parse(str(value))


def link_from_payload(payload: dict[str, Any]) -> EntityLink:
    """Build a universal link from a validated editor payload."""
    source = parse_entity_ref(payload["source"])
    target = parse_entity_ref(payload["target"])
    kind = LinkKind.parse(str(payload.get("kind", LinkKind.RELATES.value)))
    label = str(payload.get("label", ""))
    weight = float(payload.get("weight", 1.0))
    metadata = payload.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("Link metadata must be an object")
    return EntityLink(
        source=source,
        target=target,
        kind=kind,
        label=label,
        weight=weight,
        metadata=dict(metadata),
    )


@dataclass(frozen=True, slots=True)
class EditRecord:
    """One reversible relationship mutation."""

    sequence: int
    action: str
    link: dict[str, Any]
    inverse: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    actor: str = "local"

    @property
    def can_undo(self) -> bool:
        """Return whether this record can be reversed."""
        return self.action in (EDIT_ADD, EDIT_REMOVE, EDIT_UPDATE)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "sequence": self.sequence,
            "action": self.action,
            "link": dict(self.link),
            "inverse": dict(self.inverse),
            "timestamp": self.timestamp,
            "actor": self.actor,
        }


class RelationshipEditor:
    """Mutable relationship commands layered over the shared entity service."""

    def __init__(
        self,
        entities: EntityService,
        *,
        bus: EventBus | None = None,
        capabilities: Capabilities | None = None,
        clock: Clock | None = None,
        capacity: int = DEFAULT_HISTORY,
    ) -> None:
        if capacity < 1:
            raise ValueError("History capacity must be positive")
        self.entities = entities
        self.bus = bus
        self.capabilities = capabilities or Capabilities()
        self.clock: Clock = clock or SystemClock()
        self.capacity = capacity
        self._undo: list[EditRecord] = []
        self._redo: list[EditRecord] = []
        self._sequence = 0

    def _require_capability(self) -> None:
        """Fail fast when the graph capability is disabled."""
        self.capabilities.require(CAP_GRAPH)

    def _emit(self, kind: str, record: EditRecord) -> None:
        """Publish a mutation event when a bus is attached."""
        if self.bus is None:
            return
        source = parse_entity_ref(record.link["source"])
        event: DomainEvent = make_event(
            kind,
            source,
            sequence=record.sequence,
            action=record.action,
            source_ref=record.link["source"],
            target_ref=record.link["target"],
            link_kind=record.link.get("kind", ""),
            actor=record.actor,
        )
        self.bus.publish(event)

    def _record(
        self,
        action: str,
        link: EntityLink,
        *,
        inverse: EntityLink | None = None,
        actor: str = "local",
    ) -> EditRecord:
        """Append a reversible command and clear the redo branch."""
        self._sequence += 1
        record = EditRecord(
            sequence=self._sequence,
            action=action,
            link=link.as_dict(),
            inverse=inverse.as_dict() if inverse is not None else {},
            timestamp=self.clock.now_timestamp(),
            actor=actor,
        )
        self._undo.append(record)
        while len(self._undo) > self.capacity:
            self._undo.pop(0)
        self._redo.clear()
        return record

    def _validate_endpoints(self, link: EntityLink) -> None:
        """Ensure both endpoints exist in the universal entity store."""
        self.entities.get(link.source)
        self.entities.get(link.target)
        if link.source == link.target and link.kind is not LinkKind.RELATES:
            raise ValueError("Self links must use the 'relates' kind")

    def connect(
        self,
        source: EntityId | str,
        target: EntityId | str,
        *,
        kind: str = LinkKind.RELATES.value,
        label: str = "",
        weight: float = 1.0,
        actor: str = "local",
    ) -> EditRecord:
        """Create a typed relationship between two existing entities."""
        self._require_capability()
        link = link_from_payload(
            {
                "source": str(parse_entity_ref(source)),
                "target": str(parse_entity_ref(target)),
                "kind": kind,
                "label": label,
                "weight": weight,
            }
        )
        self._validate_endpoints(link)
        try:
            self.entities.graph().add(link)
        except DuplicateLinkError as error:
            raise ValueError(f"Relationship already exists: {error}") from error
        record = self._record(EDIT_ADD, link, actor=actor)
        self._emit("graph.link.added", record)
        return record

    def disconnect(
        self,
        source: EntityId | str,
        target: EntityId | str,
        *,
        kind: str = LinkKind.RELATES.value,
        label: str = "",
        weight: float = 1.0,
        actor: str = "local",
    ) -> EditRecord:
        """Remove one exact relationship."""
        self._require_capability()
        link = link_from_payload(
            {
                "source": str(parse_entity_ref(source)),
                "target": str(parse_entity_ref(target)),
                "kind": kind,
                "label": label,
                "weight": weight,
            }
        )
        if not self.entities.graph().remove(link):
            raise ValueError(f"Unknown relationship: {link.key}")
        record = self._record(EDIT_REMOVE, link, actor=actor)
        self._emit("graph.link.removed", record)
        return record

    def update(
        self,
        source: EntityId | str,
        target: EntityId | str,
        *,
        kind: str = LinkKind.RELATES.value,
        label: str | None = None,
        weight: float | None = None,
        actor: str = "local",
    ) -> EditRecord:
        """Replace one relationship with a revised label or weight."""
        self._require_capability()
        existing = link_from_payload(
            {
                "source": str(parse_entity_ref(source)),
                "target": str(parse_entity_ref(target)),
                "kind": kind,
            }
        )
        graph = self.entities.graph()
        stored = next((link for link in graph.links() if link.key == existing.key), None)
        if stored is None:
            raise ValueError(f"Unknown relationship: {existing.key}")
        revised = EntityLink(
            source=stored.source,
            target=stored.target,
            kind=stored.kind,
            label=stored.label if label is None else label,
            weight=stored.weight if weight is None else weight,
            metadata=dict(stored.metadata),
        )
        if revised.key == stored.key and revised.as_dict() == stored.as_dict():
            raise ValueError("Relationship update did not change anything")
        graph.remove(stored)
        graph.add(revised)
        record = self._record(EDIT_UPDATE, revised, inverse=stored, actor=actor)
        self._emit("graph.link.updated", record)
        return record

    def relabel(
        self,
        source: EntityId | str,
        target: EntityId | str,
        label: str,
        *,
        kind: str = LinkKind.RELATES.value,
    ) -> EditRecord:
        """Change the human-readable label of one relationship."""
        return self.update(source, target, kind=kind, label=label)

    def reweight(
        self,
        source: EntityId | str,
        target: EntityId | str,
        weight: float,
        *,
        kind: str = LinkKind.RELATES.value,
    ) -> EditRecord:
        """Change the confidence weight of one relationship."""
        return self.update(source, target, kind=kind, weight=weight)

    def undo(self) -> EditRecord | None:
        """Reverse the most recent mutation, returning it when one exists."""
        self._require_capability()
        if not self._undo:
            return None
        record = self._undo.pop()
        graph = self.entities.graph()
        affected = link_from_payload(record.link)
        if record.action == EDIT_ADD:
            graph.remove(affected)
        elif record.action == EDIT_REMOVE:
            graph.add(affected)
        else:
            graph.remove(affected)
            graph.add(link_from_payload(record.inverse))
        self._redo.append(record)
        self._emit("graph.link.undone", record)
        return record

    def redo(self) -> EditRecord | None:
        """Reapply the most recently undone mutation."""
        self._require_capability()
        if not self._redo:
            return None
        record = self._redo.pop()
        graph = self.entities.graph()
        if record.action == EDIT_ADD:
            graph.add(link_from_payload(record.link))
        elif record.action == EDIT_REMOVE:
            graph.remove(link_from_payload(record.link))
        else:
            graph.remove(link_from_payload(record.inverse))
            graph.add(link_from_payload(record.link))
        self._undo.append(record)
        self._emit("graph.link.redone", record)
        return record

    @property
    def can_undo(self) -> bool:
        """Return whether an undo is available."""
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """Return whether a redo is available."""
        return bool(self._redo)

    def history(self, *, limit: int = 20) -> dict[str, Any]:
        """Return history metadata and the most recent records."""
        if limit < 0:
            raise ValueError("limit cannot be negative")
        return {
            "size": len(self._undo),
            "redo_size": len(self._redo),
            "can_undo": self.can_undo,
            "can_redo": self.can_redo,
            "sequence": self._sequence,
            "recent": [record.as_dict() for record in self._undo[::-1][:limit]],
        }

    def clear(self) -> int:
        """Drop all history without touching the graph."""
        count = len(self._undo) + len(self._redo)
        self._undo.clear()
        self._redo.clear()
        return count

    def require_enabled(self) -> None:
        """Public capability probe used by namespace routes."""
        self._require_capability()
