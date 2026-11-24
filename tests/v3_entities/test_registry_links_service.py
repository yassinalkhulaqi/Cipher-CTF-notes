"""Tests for the entity registry, link graph, and service."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.links import DuplicateLinkError, LinkGraph
from redscribe.v3.entities.registry import EntityKindRegistry, KindSpec
from redscribe.v3.entities.service import EntityNotFoundError, EntityService
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityStatus,
    LinkKind,
)


def test_registry_fallback_and_registration() -> None:
    registry = EntityKindRegistry()
    assert registry.has(EntityKind.NOTE)
    fallback = registry.get("custom")
    assert fallback.label == "Custom"
    assert fallback.order == 999
    registry.register(KindSpec("custom", "Widget", "Widgets", "#fff", "box", 5))
    assert registry.has("custom")
    assert registry.get("custom").label == "Widget"


def test_registry_outputs_are_stable() -> None:
    registry = EntityKindRegistry()
    assert registry.validate() == ()
    labels = registry.labels()
    assert labels["note"] == "Note"
    assert len(registry.colors()) == len(labels)
    assert [spec.order for spec in registry.all()] == sorted(spec.order for spec in registry.all())
    assert len(registry.known_kinds()) == 12


def test_link_graph_add_remove_and_lookup() -> None:
    source = EntityId(EntityKind.FINDING, "f-1")
    target = EntityId(EntityKind.EVIDENCE, "e-1")
    link = EntityLink(source=source, target=target, kind=LinkKind.EVIDENCES)
    graph = LinkGraph((link,))
    assert len(graph) == 1
    assert link in graph
    assert graph.for_source(source) == (link,)
    assert graph.for_target(target) == (link,)
    assert graph.between(source, target) == (link,)
    assert graph.of_kind(LinkKind.EVIDENCES) == (link,)
    assert graph.degree(source) == 1
    assert graph.remove(link) is True
    assert graph.remove(link) is False
    assert len(graph) == 0


def test_link_graph_rejects_duplicates() -> None:
    link = EntityLink(
        source=EntityId(EntityKind.NOTE, "a"),
        target=EntityId(EntityKind.NOTE, "b"),
    )
    graph = LinkGraph((link,))
    with pytest.raises(DuplicateLinkError):
        graph.add(link)


def test_link_graph_path_and_cycle_detection() -> None:
    a = EntityId(EntityKind.NOTE, "a")
    b = EntityId(EntityKind.NOTE, "b")
    c = EntityId(EntityKind.NOTE, "c")
    graph = LinkGraph(
        (
            EntityLink(source=a, target=b),
            EntityLink(source=b, target=c),
        )
    )
    assert graph.path(a, c) == ("note:a", "note:b", "note:c")
    assert graph.path(a, EntityId(EntityKind.NOTE, "z")) is None
    assert graph.path(a, a) == ("note:a",)
    assert graph.has_cycle() is False
    graph.add(EntityLink(source=c, target=a))
    assert graph.has_cycle() is True


def test_link_graph_neighbors() -> None:
    a = EntityId(EntityKind.NOTE, "a")
    b = EntityId(EntityKind.NOTE, "b")
    graph = LinkGraph((EntityLink(source=a, target=b),))
    assert graph.neighbors(a) == frozenset({"note:b"})
    assert graph.neighbors(b) == frozenset({"note:a"})
    assert graph.neighbors(a, undirected=False) == frozenset({"note:b"})
    assert graph.neighbors(b, undirected=False) == frozenset()
    assert graph.as_dict()["count"] == 1


def test_service_create_get_update_remove() -> None:
    clock = FixedClock(start=100.0, step=1.0)
    service = EntityService(clock=clock)
    events: list[tuple[str, object]] = []
    service.subscribe(lambda action, record: events.append((action, record)))
    record = service.create(EntityKind.FINDING, title="SQLi", tags=("Web", "High"))
    assert record.created_at == 100.0
    assert service.get(record.entity_id) == record
    updated = service.update(record.entity_id, title="SQLi confirmed", status=EntityStatus.ACTIVE)
    assert updated.version == 2
    assert updated.updated_at == 101.0
    service.remove(record.entity_id)
    assert service.get(record.entity_id).status is EntityStatus.DELETED
    assert [action for action, _ in events] == ["created", "updated", "deleted"]


def test_service_get_unknown() -> None:
    service = EntityService()
    with pytest.raises(EntityNotFoundError):
        service.get(EntityId(EntityKind.NOTE, "missing"))


def test_service_links_and_refs() -> None:
    service = EntityService(clock=FixedClock(start=1.0))
    note = service.create(EntityKind.NOTE, title="Recon")
    finding = service.create(EntityKind.FINDING, title="Open port")
    link = service.link(note.entity_id, finding.entity_id, kind=LinkKind.DERIVES, weight=0.8)
    assert link in service.graph()
    assert service.unlink(link) is True
    assert service.unlink(link) is False
    refs = service.refs(EntityKind.NOTE)
    assert len(refs) == 1
    assert refs[0].label == "Recon"
    assert len(service.refs()) == 2


def test_service_search_and_tag_counts() -> None:
    service = EntityService()
    service.create(EntityKind.NOTE, title="Active Directory", summary="kerberos", tags=("ad",))
    service.create(EntityKind.FINDING, title="Kerberos abuse", tags=("ad", "creds"))
    assert len(service.search("KERBEROS")) == 2
    assert len(service.search("ad", kind=EntityKind.FINDING)) == 1
    assert service.search("") == ()
    counts = service.tag_counts()
    assert counts["ad"] == 2
    assert counts["creds"] == 1


def test_service_stats_and_snapshot() -> None:
    service = EntityService()
    service.create(EntityKind.NOTE, title="One")
    service.create(EntityKind.EVIDENCE, title="Two")
    stats = service.stats()
    assert stats["entities"] == 2
    assert stats["kind_note"] == 1
    snapshot = service.snapshot()
    assert len(snapshot["records"]) == 2
    assert snapshot["links"] == []
    assert service.duplicate_error() is DuplicateLinkError
