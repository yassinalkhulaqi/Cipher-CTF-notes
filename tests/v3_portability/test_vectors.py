"""Tests for version-vector ordering and causal comparison."""

from __future__ import annotations

import pytest

from redscribe.v3.portability.errors import PortabilityError
from redscribe.v3.portability.vectors import (
    VectorRelation,
    VersionVector,
    merge_vectors,
    sort_vectors,
    vector_from_event_counts,
)


def test_empty_vector() -> None:
    vector = VersionVector.empty()
    assert vector.is_empty()
    assert vector.total() == 0
    assert vector.as_dict() == {}


def test_vector_rejects_invalid_entries() -> None:
    with pytest.raises(PortabilityError):
        VersionVector({"": 1})
    with pytest.raises(PortabilityError):
        VersionVector({"alpha": -1})
    with pytest.raises(PortabilityError):
        VersionVector({"alpha": True})
    with pytest.raises(PortabilityError):
        VersionVector({"alpha": "2"})  # type: ignore[dict-item]


def test_vector_entries_are_sorted_on_construction() -> None:
    vector = VersionVector({"zeta": 2, "alpha": 1})
    assert list(vector.as_dict()) == ["alpha", "zeta"]


def test_bump_returns_new_vector() -> None:
    original = VersionVector({"alpha": 1})
    bumped = original.bump("alpha")
    assert original.get("alpha") == 1
    assert bumped.get("alpha") == 2
    assert bumped.get("beta") == 0
    with pytest.raises(PortabilityError):
        original.bump("alpha", amount=0)


def test_merge_takes_componentwise_maximum() -> None:
    left = VersionVector({"alpha": 3, "beta": 1})
    right = VersionVector({"alpha": 2, "gamma": 5})
    merged = left.merge(right)
    assert merged.as_dict() == {"alpha": 3, "beta": 1, "gamma": 5}
    assert merged.dominates(left)
    assert merged.dominates(right)


def test_equal_vectors_compare_equal() -> None:
    left = VersionVector({"alpha": 2, "beta": 1})
    right = VersionVector({"beta": 1, "alpha": 2})
    assert left.compare(right) is VectorRelation.EQUAL
    assert left.dominates(right)
    assert right.dominates(left)


def test_left_ahead_relation() -> None:
    left = VersionVector({"alpha": 3, "beta": 1})
    right = VersionVector({"alpha": 2, "beta": 1})
    assert left.compare(right) is VectorRelation.LEFT_AHEAD
    assert right.compare(left) is VectorRelation.RIGHT_AHEAD


def test_concurrent_relation() -> None:
    left = VersionVector({"alpha": 2, "beta": 1})
    right = VersionVector({"alpha": 1, "beta": 2})
    assert left.compare(right) is VectorRelation.CONCURRENT
    assert not left.dominates(right)
    assert not right.dominates(left)


def test_vector_distance_and_changed_devices() -> None:
    left = VersionVector({"alpha": 3, "beta": 1})
    right = VersionVector({"alpha": 1, "gamma": 4})
    assert left.distance_from(right) == 7
    assert left.changed_devices(right) == ("alpha", "beta", "gamma")


def test_vector_serialization_round_trip() -> None:
    vector = VersionVector({"alpha": 2, "beta": 3})
    assert VersionVector.from_dict(vector.as_dict()) == vector
    assert VersionVector.from_dict(None).is_empty()
    assert VersionVector.from_dict({}).is_empty()
    with pytest.raises(PortabilityError):
        VersionVector.from_dict(["alpha"])  # type: ignore[arg-type]


def test_merge_vectors_collection() -> None:
    vectors = (
        VersionVector({"alpha": 1}),
        VersionVector({"alpha": 4, "beta": 1}),
        VersionVector({"gamma": 2}),
    )
    assert merge_vectors(vectors).as_dict() == {"alpha": 4, "beta": 1, "gamma": 2}
    assert merge_vectors(()).is_empty()


def test_sort_vectors_is_stable() -> None:
    vectors = (
        VersionVector({"beta": 1}),
        VersionVector({"alpha": 1}),
        VersionVector({"alpha": 1, "beta": 1}),
    )
    ordered = sort_vectors(vectors)
    assert [item.as_dict() for item in ordered] == [
        {"alpha": 1},
        {"alpha": 1, "beta": 1},
        {"beta": 1},
    ]


def test_vector_from_event_counts() -> None:
    assert vector_from_event_counts({"alpha": 2}, scale=3).as_dict() == {"alpha": 6}
    with pytest.raises(PortabilityError):
        vector_from_event_counts({"alpha": 1}, scale=0)


def test_relation_labels_are_human_readable() -> None:
    assert "Independent" in VectorRelation.CONCURRENT.label
    assert "Identical" in VectorRelation.EQUAL.label
    assert VectorRelation.LEFT_AHEAD.value == "left_ahead"
