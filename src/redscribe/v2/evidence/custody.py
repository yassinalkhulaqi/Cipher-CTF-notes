"""Append-only chain of custody with hash-linked events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v2.evidence.errors import ValidationError
from redscribe.v2.evidence.hashing import canonical_digest, chain_hash, digest_matches
from redscribe.v2.evidence.models import CustodyAction, CustodyEvent
from redscribe.v2.evidence.validation import (
    normalize_metadata,
    normalize_timestamp,
    now_iso,
    validate_evidence_id,
)

GENESIS_HASH = "0" * 64
MAX_DESCRIPTION_LENGTH = 1_000
MAX_ACTOR_LENGTH = 120
MAX_NAME_LENGTH = 200


def event_payload(
    *,
    evidence_id: str,
    action: CustodyAction,
    actor: str,
    timestamp: str,
    description: str,
    location: str,
    reference: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the canonical hashable payload for a custody event."""
    return {
        "evidence_id": evidence_id,
        "action": action.value,
        "actor": actor,
        "timestamp": timestamp,
        "description": description,
        "location": location,
        "reference": reference,
        "metadata": dict(metadata),
    }


def compute_event_hash(previous: str, payload: Mapping[str, Any]) -> str:
    """Compute the hash stored on a new custody event."""
    return chain_hash(previous, payload)


class CustodyChain:
    """In-memory helper that appends and verifies custody events."""

    def __init__(self, events: Iterable[CustodyEvent] = ()) -> None:
        self._events = sorted(events, key=lambda event: event.id)

    @property
    def events(self) -> tuple[CustodyEvent, ...]:
        return tuple(self._events)

    def last_hash(self, evidence_id: str = "") -> str:
        """Return the most recent event hash for an item or the whole chain."""
        candidates = [
            event for event in self._events if not evidence_id or event.evidence_id == evidence_id
        ]
        if not candidates:
            return GENESIS_HASH
        return max(candidates, key=lambda event: event.id).event_hash

    def next_id(self) -> int:
        """Return the next sequence number for the chain."""
        if not self._events:
            return 1
        return max(event.id for event in self._events) + 1

    def append(
        self,
        evidence_id: str,
        action: CustodyAction,
        *,
        actor: str = "",
        timestamp: str = "",
        description: str = "",
        location: str = "",
        reference: str = "",
        metadata: Mapping[str, Any] | None = None,
        event_id: int | None = None,
    ) -> CustodyEvent:
        """Create a hash-linked custody event and add it to the chain."""
        record_id = validate_evidence_id(evidence_id)
        if not isinstance(actor, str) or len(actor) > MAX_ACTOR_LENGTH:
            raise ValidationError("Invalid custody actor", details={"field": "actor"})
        stamp = normalize_timestamp(timestamp, default=now_iso())
        payload = event_payload(
            evidence_id=record_id,
            action=action,
            actor=actor.strip(),
            timestamp=stamp,
            description=description.strip()[:MAX_DESCRIPTION_LENGTH],
            location=location.strip()[:MAX_NAME_LENGTH],
            reference=reference.strip()[:MAX_NAME_LENGTH],
            metadata=normalize_metadata(metadata),
        )
        previous = self.last_hash(record_id)
        event = CustodyEvent(
            id=event_id if event_id is not None else self.next_id(),
            evidence_id=record_id,
            action=action,
            actor=payload["actor"],
            timestamp=stamp,
            description=payload["description"],
            location=payload["location"],
            reference=payload["reference"],
            previous_hash=previous,
            event_hash=compute_event_hash(previous, payload),
            metadata=payload["metadata"],
        )
        self._events.append(event)
        self._events.sort(key=lambda item: item.id)
        return event

    def for_evidence(self, evidence_id: str) -> list[CustodyEvent]:
        """Return events for one item in append order."""
        return [event for event in self._events if event.evidence_id == evidence_id]

    def verify(self, evidence_id: str = "") -> tuple[bool, list[str]]:
        """Verify hashes, links, and ordering; return problems when invalid."""
        problems: list[str] = []
        expected_previous = GENESIS_HASH
        seen_ids: set[int] = set()
        ordered = sorted(self._events, key=lambda event: event.id)
        for event in ordered:
            if evidence_id and event.evidence_id != evidence_id:
                continue
            if event.id in seen_ids:
                problems.append(f"Duplicate custody event id {event.id}")
            seen_ids.add(event.id)
            if not digest_matches(event.previous_hash, expected_previous):
                problems.append(
                    f"Event {event.id} does not link to event hash {expected_previous[:12]}"
                )
            payload = event_payload(
                evidence_id=event.evidence_id,
                action=event.action,
                actor=event.actor,
                timestamp=event.timestamp,
                description=event.description,
                location=event.location,
                reference=event.reference,
                metadata=event.metadata,
            )
            if not digest_matches(
                event.event_hash, compute_event_hash(event.previous_hash, payload)
            ):
                problems.append(f"Event {event.id} hash does not match its payload")
            expected_previous = event.event_hash
        return not problems, problems

    def replace(self, events: Iterable[CustodyEvent]) -> None:
        """Replace the chain contents, used after repository loads."""
        self._events = sorted(events, key=lambda event: event.id)


def custody_timeline(events: Sequence[CustodyEvent]) -> list[dict[str, Any]]:
    """Group custody events by date for a UI timeline."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        day = event.timestamp[:10] or "unknown"
        groups.setdefault(day, []).append(
            {
                "id": event.id,
                "time": event.timestamp,
                "action": event.action.value,
                "actor": event.actor,
                "description": event.description,
                "location": event.location,
                "reference": event.reference,
                "hash": event.event_hash,
                "previous_hash": event.previous_hash,
            }
        )
    return [{"date": day, "events": entries} for day, entries in sorted(groups.items())]


def custody_summary(events: Sequence[CustodyEvent]) -> dict[str, Any]:
    """Return compact metadata describing a custody chain."""
    if not events:
        return {
            "count": 0,
            "first": "",
            "last": "",
            "actions": [],
            "actors": [],
            "locations": [],
        }
    actions = sorted({event.action.value for event in events})
    actors = sorted({event.actor for event in events if event.actor})
    locations = sorted({event.location for event in events if event.location})
    return {
        "count": len(events),
        "first": events[0].timestamp,
        "last": events[-1].timestamp,
        "actions": actions,
        "actors": actors,
        "locations": locations,
    }


def latest_event(events: Sequence[CustodyEvent], *, evidence_id: str = "") -> CustodyEvent | None:
    """Return the most recent event, optionally for one item."""
    candidates = [event for event in events if not evidence_id or event.evidence_id == evidence_id]
    if not candidates:
        return None
    return max(candidates, key=lambda event: event.id)


def validate_custody_event(event: CustodyEvent) -> None:
    """Raise when a custody event has invalid structural fields."""
    validate_evidence_id(event.evidence_id, field="evidence_id")
    if not event.actor.strip():
        raise ValidationError("Custody actor is required", details={"field": "actor"})
    if not normalize_timestamp(event.timestamp):
        raise ValidationError("Invalid custody timestamp", details={"field": "timestamp"})
    if len(event.event_hash) != 64:
        raise ValidationError("Invalid custody event hash", details={"field": "event_hash"})


def custody_digest(events: Sequence[CustodyEvent]) -> str:
    """Return a single digest representing an entire custody chain."""
    return canonical_digest([event.as_dict() for event in events])


def custody_action_label(action: CustodyAction) -> str:
    """Return a display label for a custody action."""
    return action.value.replace("_", " ").title()
