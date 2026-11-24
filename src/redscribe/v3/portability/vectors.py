"""Version vectors for causally comparing independently edited vaults."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe.v3.portability.errors import PortabilityError


class VectorRelation(str, Enum):
    """Causal relation between two version vectors."""

    EQUAL = "equal"
    LEFT_AHEAD = "left_ahead"
    RIGHT_AHEAD = "right_ahead"
    CONCURRENT = "concurrent"

    @property
    def label(self) -> str:
        """Human-readable relation description."""
        return {
            VectorRelation.EQUAL: "Identical histories",
            VectorRelation.LEFT_AHEAD: "Local history is ahead",
            VectorRelation.RIGHT_AHEAD: "Incoming history is ahead",
            VectorRelation.CONCURRENT: "Independent edits on both sides",
        }[self]


@dataclass(frozen=True, slots=True)
class VersionVector:
    """An immutable per-device logical clock."""

    counters: dict[str, int]

    def __post_init__(self) -> None:
        cleaned: dict[str, int] = {}
        for name, value in self.counters.items():
            if not isinstance(name, str) or not name.strip():
                raise PortabilityError("Vector device names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PortabilityError("Vector counters must be non-negative integers")
            cleaned[name] = value
        object.__setattr__(self, "counters", dict(sorted(cleaned.items())))

    @classmethod
    def empty(cls) -> VersionVector:
        """Return an empty vector."""
        return cls({})

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> VersionVector:
        """Parse a vector from a JSON mapping."""
        if payload is None:
            return cls.empty()
        if not isinstance(payload, dict):
            raise PortabilityError("Version vector must be a mapping")
        return cls({str(key): int(value) for key, value in payload.items()})

    def get(self, device: str) -> int:
        """Return the counter recorded for one device."""
        return self.counters.get(device, 0)

    def bump(self, device: str, *, amount: int = 1) -> VersionVector:
        """Return a vector with one device counter advanced."""
        if amount < 1:
            raise PortabilityError("Vector bump amount must be positive")
        updated = dict(self.counters)
        updated[device] = self.get(device) + amount
        return VersionVector(updated)

    def merge(self, other: VersionVector) -> VersionVector:
        """Return the component-wise maximum of two vectors."""
        names = set(self.counters) | set(other.counters)
        return VersionVector({name: max(self.get(name), other.get(name)) for name in names})

    def dominates(self, other: VersionVector) -> bool:
        """Return whether this vector knows every event in ``other``."""
        return all(self.get(name) >= value for name, value in other.counters.items())

    def compare(self, other: VersionVector) -> VectorRelation:
        """Compare two vectors using causal ordering."""
        left_ahead = self.dominates(other)
        right_ahead = other.dominates(self)
        if left_ahead and right_ahead:
            return VectorRelation.EQUAL
        if left_ahead:
            return VectorRelation.LEFT_AHEAD
        if right_ahead:
            return VectorRelation.RIGHT_AHEAD
        return VectorRelation.CONCURRENT

    def distance_from(self, other: VersionVector) -> int:
        """Return the total counter difference in both directions."""
        names = set(self.counters) | set(other.counters)
        return sum(abs(self.get(name) - other.get(name)) for name in names)

    def changed_devices(self, other: VersionVector) -> tuple[str, ...]:
        """Return device names whose counters differ."""
        names = set(self.counters) | set(other.counters)
        return tuple(sorted(name for name in names if self.get(name) != other.get(name)))

    def is_empty(self) -> bool:
        """Return whether the vector has any events."""
        return not self.counters

    def total(self) -> int:
        """Return the sum of all counters."""
        return sum(self.counters.values())

    def as_dict(self) -> dict[str, int]:
        """Return a JSON-safe representation."""
        return dict(self.counters)


def merge_vectors(vectors: tuple[VersionVector, ...]) -> VersionVector:
    """Merge a collection of vectors into one."""
    result = VersionVector.empty()
    for vector in vectors:
        result = result.merge(vector)
    return result


def vector_from_event_counts(counts: dict[str, int], *, scale: int = 1) -> VersionVector:
    """Build a vector from per-device event counters with an optional scale."""
    if scale < 1:
        raise PortabilityError("Vector scale must be positive")
    return VersionVector({name: value * scale for name, value in counts.items()})


def sort_vectors(vectors: tuple[VersionVector, ...]) -> tuple[VersionVector, ...]:
    """Return vectors in a stable, deterministic order."""
    return tuple(
        sorted(vectors, key=lambda vector: (tuple(vector.as_dict().items()), vector.total()))
    )
