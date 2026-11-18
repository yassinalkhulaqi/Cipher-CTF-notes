"""Version vectors for change ordering and merge decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VersionVector:
    """A simple per-replica logical clock."""

    clock: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> VersionVector:
        clock: dict[str, int] = {}
        for key, value in (data or {}).items():
            name = str(key).strip()
            if not name:
                continue
            try:
                clock[name] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        return cls(clock=dict(sorted(clock.items())))

    def copy(self) -> VersionVector:
        return VersionVector(clock=dict(self.clock))

    def value(self, replica: str) -> int:
        return self.clock.get(replica, 0)

    def increment(self, replica: str, amount: int = 1) -> VersionVector:
        if amount < 1:
            amount = 1
        self.clock[replica] = self.value(replica) + amount
        self.clock = dict(sorted(self.clock.items()))
        return self

    def merge(self, other: VersionVector) -> VersionVector:
        for replica, value in other.clock.items():
            self.clock[replica] = max(self.value(replica), int(value))
        self.clock = dict(sorted(self.clock.items()))
        return self

    def dominates(self, other: VersionVector) -> bool:
        keys = set(self.clock) | set(other.clock)
        return all(self.value(key) >= other.value(key) for key in keys) and any(
            self.value(key) > other.value(key) for key in keys
        )

    def concurrent_with(self, other: VersionVector) -> bool:
        relation = compare_vectors(self, other)
        return relation == "concurrent"

    def as_dict(self) -> dict[str, int]:
        return dict(sorted(self.clock.items()))


def compare_vectors(left: VersionVector, right: VersionVector) -> str:
    """Compare two vectors and return equal/local/remote/concurrent."""
    if left.clock == right.clock:
        return "equal"
    left_ge = all(left.value(key) >= right.value(key) for key in set(left.clock) | set(right.clock))
    right_ge = all(
        right.value(key) >= left.value(key) for key in set(left.clock) | set(right.clock)
    )
    left_gt = any(left.value(key) > right.value(key) for key in set(left.clock) | set(right.clock))
    right_gt = any(right.value(key) > left.value(key) for key in set(left.clock) | set(right.clock))
    if left_ge and left_gt:
        return "local"
    if right_ge and right_gt:
        return "remote"
    if left_ge and right_ge:
        return "equal"
    return "concurrent"


def bump_vector(
    vector: VersionVector | Mapping[str, Any] | None,
    replica: str,
    amount: int = 1,
) -> VersionVector:
    """Increment a vector-like value and return a concrete vector."""
    current = vector if isinstance(vector, VersionVector) else VersionVector.from_dict(vector)
    return current.copy().increment(replica, amount)


def merge_vector_maps(*vectors: Mapping[str, Any] | VersionVector | None) -> VersionVector:
    """Merge multiple vector maps into one normalized vector."""
    merged = VersionVector()
    for item in vectors:
        if item is None:
            continue
        current = item if isinstance(item, VersionVector) else VersionVector.from_dict(item)
        merged.merge(current)
    return merged
