"""Tests for the undoable relationship editor."""

from __future__ import annotations

import pytest

from redscribe.v3.capabilities import CAP_GRAPH, Capabilities
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities import EntityId, EntityKind, LinkKind
from redscribe.v3.events import EventBus
from redscribe.v3.graph_workbench.editor import (
    RelationshipEditor,
    link_from_payload,
    parse_entity_ref,
)
from tests.v3_graph_workbench import build_service


def editor_with_bus() -> tuple[RelationshipEditor, EventBus]:
    bus = EventBus()
    return RelationshipEditor(build_service(), bus=bus, clock=FixedClock(100.0)), bus


def test_parse_entity_ref_and_link_payload() -> None:
    ref = EntityId(EntityKind.NOTE, "a")
    assert parse_entity_ref(ref) == ref
    assert parse_entity_ref("finding:b").kind is EntityKind.FINDING
    link = link_from_payload({"source": "note:a", "target": "finding:b", "weight": 0.4})
    assert link.weight == 0.4
    assert link.kind is LinkKind.RELATES
    with pytest.raises(ValueError, match="metadata"):
        link_from_payload({"source": "note:a", "target": "note:b", "metadata": []})


def test_connect_and_duplicate_rejection() -> None:
    editor, bus = editor_with_bus()
    record = editor.connect("note:root", "evidence:cap-01", kind="references", label="cites")
    assert record.action == "add"
    assert record.sequence == 1
    assert editor.can_undo
    assert not editor.can_redo
    assert editor.entities.graph().degree(EntityId.parse("note:root")) == 3
    with pytest.raises(ValueError, match="already exists"):
        editor.connect("note:root", "evidence:cap-01", kind="references")
    assert any(item.kind == "graph.link.added" for item in bus.records())


def test_connect_validates_endpoints() -> None:
    editor, _ = editor_with_bus()
    with pytest.raises(Exception, match="Unknown entity"):
        editor.connect("note:root", "note:missing")
    with pytest.raises(ValueError, match="Self links"):
        editor.connect("note:root", "note:root", kind="evidences")


def test_disconnect_and_undo_restore() -> None:
    editor, bus = editor_with_bus()
    target = ("note:root", "finding:sql-001")
    record = editor.disconnect(*target, kind="evidences")
    assert record.action == "remove"
    assert editor.entities.graph().degree(EntityId.parse(target[0])) == 1
    undone = editor.undo()
    assert undone is not None
    assert undone.sequence == record.sequence
    assert editor.entities.graph().degree(EntityId.parse(target[0])) == 2
    assert any(item.kind == "graph.link.undone" for item in bus.records())
    with pytest.raises(ValueError, match="Unknown relationship"):
        editor.disconnect("note:root", "note:root")


def test_update_relabel_reweight_and_undo() -> None:
    editor, bus = editor_with_bus()
    record = editor.relabel("note:root", "finding:sql-001", "new label", kind="evidences")
    assert record.action == "update"
    assert record.inverse["label"] == "supports"
    assert record.link["label"] == "new label"
    assert (
        editor.reweight("finding:sql-001", "evidence:cap-01", 0.25, kind="derives").link["weight"]
        == 0.25
    )
    assert len(editor.entities.graph()) == 3
    editor.undo()
    assert editor.entities.graph().of_kind(LinkKind.DERIVES)[0].weight == 1.0
    assert any(item.kind == "graph.link.updated" for item in bus.records())


def test_redo_restores_update_inverse() -> None:
    editor, _ = editor_with_bus()
    editor.relabel("note:root", "finding:sql-001", "renamed", kind="evidences")
    editor.undo()
    editor.redo()
    link = next(
        link
        for link in editor.entities.graph().of_kind(LinkKind.EVIDENCES)
        if link.label == "renamed"
    )
    assert link.label == "renamed"
    assert editor.redo() is None
    assert editor.undo() is not None


def test_history_bounded_and_clearable() -> None:
    small = RelationshipEditor(build_service(), capacity=2)
    kinds = ("relates", "references", "duplicates", "supersedes")
    for index, kind in enumerate(kinds):
        small.connect("note:root", "evidence:cap-01", kind=kind, label=f"l{index}")
    history = small.history(limit=1)
    assert history["size"] == 2
    assert len(history["recent"]) == 1
    assert history["sequence"] == 4
    assert small.clear() == 2
    assert small.history()["size"] == 0
    with pytest.raises(ValueError, match="capacity"):
        RelationshipEditor(build_service(), capacity=0)
    with pytest.raises(ValueError, match="limit"):
        small.history(limit=-1)


def test_capability_can_disable_edits() -> None:
    disabled = Capabilities(enabled=frozenset())
    editor = RelationshipEditor(build_service(), capabilities=disabled)
    from redscribe.v3.capabilities import CapabilityError

    with pytest.raises(CapabilityError):
        editor.connect("note:root", "evidence:cap-01")
    with pytest.raises(CapabilityError):
        editor.require_enabled()
    assert CAP_GRAPH in Capabilities().enabled
