"""Tests for V3 entity value types and identifier helpers."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.ids import (
    is_valid_value,
    new_id,
    new_value,
    short_form,
    slugify,
    try_parse,
)
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityRecord,
    EntityRef,
    EntityStatus,
    LinkKind,
)


def test_entity_kind_parse() -> None:
    assert EntityKind.parse("NOTE") is EntityKind.NOTE
    assert EntityKind.parse(" finding ") is EntityKind.FINDING
    with pytest.raises(ValueError):
        EntityKind.parse("unknown")


def test_entity_id_roundtrip() -> None:
    entity_id = EntityId(EntityKind.FINDING, "web-001")
    assert str(entity_id) == "finding:web-001"
    assert EntityId.parse(str(entity_id)) == entity_id
    assert entity_id.same_kind(EntityId(EntityKind.FINDING, "other"))
    assert not entity_id.same_kind(EntityId(EntityKind.NOTE, "web-001"))


def test_entity_id_validation() -> None:
    with pytest.raises(ValueError):
        EntityId(EntityKind.NOTE, "")
    with pytest.raises(ValueError):
        EntityId(EntityKind.NOTE, "has space")
    with pytest.raises(ValueError):
        EntityId.parse("no-separator")


def test_entity_id_as_dict() -> None:
    payload = EntityId(EntityKind.EVIDENCE, "cap-01").as_dict()
    assert payload["kind"] == "evidence"
    assert payload["value"] == "cap-01"
    assert payload["ref"] == "evidence:cap-01"


def test_entity_ref_helpers() -> None:
    ref = EntityRef.of("target", "host-01", "Primary host")
    assert ref.kind is EntityKind.TARGET
    assert str(ref) == "target:host-01"
    assert ref.as_dict()["label"] == "Primary host"
    assert ref.as_dict()["kind"] == "target"


def test_link_kind_properties() -> None:
    assert LinkKind.parse("EVIDENCES") is LinkKind.EVIDENCES
    assert LinkKind.RELATES.is_directed is False
    assert LinkKind.CONTAINS.is_directed is True
    with pytest.raises(ValueError):
        LinkKind.parse("missing")


def test_entity_link_reverse_and_key() -> None:
    source = EntityId(EntityKind.FINDING, "f-1")
    target = EntityId(EntityKind.EVIDENCE, "e-1")
    link = EntityLink(source=source, target=target, kind=LinkKind.EVIDENCES, weight=0.5)
    assert link.key == ("finding:f-1", "evidence:e-1", "evidences")
    reversed_link = link.reversed()
    assert reversed_link.source == target
    assert reversed_link.target == source
    assert reversed_link.weight == 0.5
    assert link.as_dict()["kind"] == "evidences"


def test_entity_link_weight_bounds() -> None:
    source = EntityId(EntityKind.NOTE, "a")
    target = EntityId(EntityKind.NOTE, "b")
    with pytest.raises(ValueError):
        EntityLink(source=source, target=target, weight=-0.1)
    with pytest.raises(ValueError):
        EntityLink(source=source, target=target, weight=1.1)


def test_entity_record_updates_are_immutable() -> None:
    record = EntityRecord(entity_id=EntityId(EntityKind.NOTE, "a"), title="Original")
    updated = record.with_updates(title="Changed", status=EntityStatus.ACTIVE)
    assert record.title == "Original"
    assert updated.title == "Changed"
    assert updated.status is EntityStatus.ACTIVE
    assert updated.version == record.version + 1


def test_entity_record_validation() -> None:
    with pytest.raises(ValueError):
        EntityRecord(entity_id=EntityId(EntityKind.NOTE, "a"), title="   ")
    with pytest.raises(ValueError):
        EntityRecord(entity_id=EntityId(EntityKind.NOTE, "a"), title="ok", version=0)


def test_entity_record_tag_set() -> None:
    record = EntityRecord(
        entity_id=EntityId(EntityKind.NOTE, "a"),
        title="Title",
        tags=("Web", "RECON"),
    )
    assert record.tag_set == frozenset({"web", "recon"})
    assert record.as_dict()["tags"] == ["Web", "RECON"]


def test_generated_ids_are_valid_and_unique() -> None:
    first = new_id(EntityKind.FINDING, prefix="SQL Injection")
    second = new_id(EntityKind.FINDING, prefix="SQL Injection")
    assert first != second
    assert first.kind is EntityKind.FINDING
    assert is_valid_value(first.value)
    assert len(new_value(EntityKind.NOTE)) == 16


def test_slugify_and_short_form() -> None:
    assert slugify("  Hello, World!  ") == "hello-world"
    assert slugify("***") == "item"
    short = short_form(EntityId(EntityKind.REPORT, "abcdefghijklmnop"), length=8)
    assert short == "rep:abcdefgh"
    with pytest.raises(ValueError):
        short_form(EntityId(EntityKind.NOTE, "abc"), length=2)


def test_try_parse() -> None:
    assert try_parse("note:abc") == EntityId(EntityKind.NOTE, "abc")
    assert try_parse("bad") is None
    assert try_parse("nope:abc") is None
