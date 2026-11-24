"""Incremental index consistency after entity and domain events."""

from __future__ import annotations

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityKind, LinkKind
from redscribe.v3.events.types import DomainEvent, make_event
from redscribe.v3.search_intel.index import (
    SearchIndex,
    document_from_dict,
    document_from_record,
)
from tests.v3_search_intel.helpers import build_service


def test_document_from_record_projects_fields() -> None:
    service = build_service()
    record = service.entities.get(service.entities.refs(EntityKind.FINDING)[0].entity_id)
    doc = document_from_record(record, link_degree=2, link_kinds=("evidences",))
    assert doc.ref == str(record.entity_id)
    assert doc.kind == "finding"
    assert doc.severity == "critical"
    assert doc.has_links
    assert doc.link_degree == 2
    assert doc.link_kinds == ("evidences",)


def test_upsert_updates_inverted_index() -> None:
    index = SearchIndex()
    index.upsert(document_from_dict({"ref": "note:a", "kind": "note", "title": "Alpha"}))
    assert "note:a" in index.postings("alpha")
    assert index.find("note:a") is not None
    assert index.state().documents == 1
    assert index.state().tokens == 1


def test_remove_cleans_postings() -> None:
    index = SearchIndex()
    index.upsert(document_from_dict({"ref": "note:a", "kind": "note", "title": "Alpha"}))
    assert index.remove("note:a")
    assert not index.remove("note:a")
    assert index.postings("alpha") == frozenset()
    assert index.state().documents == 0


def test_replace_removes_stale_tokens() -> None:
    index = SearchIndex()
    index.upsert(document_from_dict({"ref": "note:a", "kind": "note", "title": "Alpha"}))
    index.upsert(document_from_dict({"ref": "note:a", "kind": "note", "title": "Beta"}))
    assert index.postings("alpha") == frozenset()
    assert "note:a" in index.postings("beta")
    assert index.state().generation == 2


def test_dirty_tracking_and_drain() -> None:
    index = SearchIndex()
    index.upsert(document_from_dict({"ref": "note:a", "kind": "note", "title": "A"}))
    index.upsert(document_from_dict({"ref": "note:b", "kind": "note", "title": "B"}))
    assert index.drain_dirty() == ("note:a", "note:b")
    assert index.drain_dirty() == ()
    assert index.state().dirty == 0


def test_attach_tracks_entity_changes() -> None:
    from redscribe.v3.entities.service import EntityService

    service = EntityService(clock=FixedClock(start=100.0))
    index = SearchIndex()
    index.attach(service)
    record = service.create(EntityKind.NOTE, title="Created note", value="n1")
    assert index.find(str(record.entity_id)) is not None
    service.update(record.entity_id, title="Updated note")
    updated = index.find(str(record.entity_id))
    assert updated is not None
    assert updated.title == "Updated note"
    service.remove(record.entity_id)
    assert index.find(str(record.entity_id)) is None


def test_domain_event_create_and_delete() -> None:
    index = SearchIndex()
    event = make_event(
        "entities.created",
        payload={
            "record": {
                "ref": "finding:x",
                "kind": "finding",
                "title": "Event finding",
            }
        },
    )
    assert index.consume_event(event)
    assert index.find("finding:x") is not None
    deleted = DomainEvent(kind="entities.deleted", payload={"ref": "finding:x"})
    assert index.consume_event(deleted)
    assert index.find("finding:x") is None


def test_domain_event_without_record_is_ignored() -> None:
    index = SearchIndex()
    assert not index.consume_event(make_event("entities.touched"))


def test_refresh_links_updates_metadata() -> None:
    service = build_service()
    index = SearchIndex()
    index.upsert(document_from_dict({"ref": "finding:fresh", "kind": "finding", "title": "T"}))
    fresh = service.entities.create(
        EntityKind.FINDING, title="Fresh finding", value="fresh"
    ).entity_id
    source = service.entities.refs(EntityKind.EVIDENCE)[0].entity_id
    service.entities.link(source, fresh, kind=LinkKind.EVIDENCES)
    changed = index.refresh_links(service.entities)
    assert changed >= 1
    doc = index.find("finding:fresh")
    assert doc is not None
    assert doc.has_links
    assert "evidences" in doc.link_kinds


def test_reindex_replaces_everything() -> None:
    service = build_service()
    index = SearchIndex()
    index.reindex(service.index.documents())
    assert index.state().documents == len(service.index.documents())
    assert index.state().last_action == "reindex"
    assert index.documents() == service.index.documents()


def test_index_state_by_kind_is_bounded() -> None:
    service = build_service()
    state = service.index.state(by_kind_limit=2)
    assert len(state.by_kind) == 2


def test_document_from_dict_rejects_missing_ref() -> None:
    assert document_from_dict({}) is None
