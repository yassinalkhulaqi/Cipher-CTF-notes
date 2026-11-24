"""End-to-end service behavior across all B05 primitives."""

from __future__ import annotations

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityKind, LinkKind
from redscribe.v3.search_intel.service import SearchIntelService
from tests.v3_search_intel.helpers import build_service, ref


def test_service_search_returns_all_sections() -> None:
    service = build_service()
    payload = service.search("kind:finding", fields=("kind", "severity"))
    assert set(payload) == {
        "query",
        "hits",
        "total",
        "facets",
        "clusters",
        "pivots",
        "index",
    }
    assert payload["total"] == 2
    assert payload["hits"]


def test_service_search_without_facets() -> None:
    service = build_service()
    assert service.search("kind:finding")["facets"] == []


def test_service_search_includes_pivot_context() -> None:
    service = build_service()
    payload = service.search("kind:finding")
    assert payload["pivots"]
    assert any(context["origin_kind"] == "finding" for context in payload["pivots"])


def test_service_facets_and_clusters_helpers() -> None:
    service = build_service()
    facets = service.facets("tag:web", fields=("kind",))
    assert facets
    assert facets[0]["field"] == "kind"
    clusters = service.clusters("tag:web", strategy="none")
    assert len(clusters) == 1


def test_service_pivots_depth() -> None:
    service = build_service()
    shallow = service.pivots(ref("finding", "finding-01"), depth=1)
    deeper = service.pivots(ref("finding", "finding-01"), depth=2)
    assert shallow["origin"] == ref("finding", "finding-01")
    assert len(deeper["pivots"]) >= len(shallow["pivots"])


def test_autocomplete_fields_and_values() -> None:
    service = build_service()
    fields = service.autocomplete("ki")
    assert any(item.kind == "field" and item.value == "kind:" for item in fields)
    values = service.autocomplete("kind:fi")
    assert any(item.value == "finding" for item in values)


def test_autocomplete_saved_and_templates() -> None:
    service = build_service()
    service.saved.create("Critical triage", "kind:finding severity:critical")
    completions = service.autocomplete("crit")
    assert any(item.kind == "saved" for item in completions)
    assert any(item.kind == "template" for item in completions)


def test_autocomplete_empty_partial() -> None:
    service = build_service()
    assert service.autocomplete("") == ()
    assert service.autocomplete("web ") == ()


def test_snapshot_round_trip() -> None:
    service = build_service()
    service.saved.create("A", "kind:note")
    service.facet_sets.create("B", ("kind", "severity"))
    snapshot = service.snapshot()
    other = SearchIntelService(clock=FixedClock(start=1.0))
    assert other.load(snapshot) == 2
    assert other.snapshot() == snapshot


def test_save_search_convenience() -> None:
    service = build_service()
    item = service.save_search("Triage", "kind:finding", tags="triage")
    assert item["name"] == "Triage"
    assert service.saved.get(item["id"]) is not None


def test_index_follows_entity_edits_end_to_end() -> None:
    service = build_service()
    before = service.search("weak cipher")["total"]
    assert before >= 1
    record = service.entities.find(ref("finding", "finding-01"))
    assert record is not None
    service.entities.update(record.entity_id, summary="Completely different content")
    assert service.search("weak cipher")["total"] == before - 1
    assert service.search("completely different")["total"] == 1


def test_new_entities_are_searchable_automatically() -> None:
    service = build_service()
    service.entities.create(
        EntityKind.SNIPPET,
        title="Newly indexed snippet",
        summary="Fresh content",
        value="snippet-new",
    )
    assert service.search("newly indexed", fields=("kind",))["total"] == 1


def test_deleted_entities_leave_the_index() -> None:
    service = build_service()
    record = service.entities.find(ref("note", "recon-01"))
    assert record is not None
    service.entities.remove(record.entity_id)
    assert service.search("port 443")["total"] == 0


def test_link_change_updates_has_link_facet() -> None:
    service = build_service()
    fresh = service.entities.create(EntityKind.NOTE, title="Unlinked note", value="unlinked")
    fresh_doc = service.index.find(str(fresh.entity_id))
    assert fresh_doc is not None
    assert not fresh_doc.has_links
    other = service.entities.refs(EntityKind.FINDING)[0].entity_id
    service.entities.link(fresh.entity_id, other, kind=LinkKind.RELATES)
    service.index.refresh_links(service.entities)
    doc = service.index.find(str(fresh.entity_id))
    assert doc is not None
    assert doc.has_links
