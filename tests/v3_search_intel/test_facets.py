"""Facet extraction and drill-down counts."""

from __future__ import annotations

from redscribe.v3.search_intel.facets import (
    document_values,
    extract_facets,
    facet_deltas,
    facet_groups,
    matches_selection,
    normalize_facet_fields,
    normalize_selection,
)
from redscribe.v3.search_intel.types import FacetField, IndexDocument
from tests.v3_search_intel.helpers import build_service


def _docs() -> tuple[IndexDocument, ...]:
    return build_service().index.documents()


def test_document_values_by_facet() -> None:
    doc = _docs()[0]
    assert document_values(doc, FacetField.KIND.value) == (doc.kind,)
    assert document_values(doc, FacetField.STATUS.value) == (doc.status,)
    assert document_values(doc, FacetField.HAS_LINK.value) in (("yes",), ("no",))
    assert document_values(doc, "unknown") == ()


def test_normalize_facet_fields_dedupes_and_falls_back() -> None:
    assert normalize_facet_fields("kind, tag,kind") == ("kind", "tag")
    assert normalize_facet_fields(()) == ("kind", "status", "severity", "tag", "has_link")


def test_normalize_selection_ignores_unknown_fields() -> None:
    result = normalize_selection({"kind": ["FINDING"], "unknown": ["x"]})
    assert result == {"kind": frozenset({"finding"})}


def test_matches_selection() -> None:
    doc = _docs()[0]
    assert matches_selection(doc, {})
    assert matches_selection(doc, {"kind": frozenset({doc.kind})})
    assert not matches_selection(doc, {"kind": frozenset({"not-a-kind"})})


def test_facet_counts_are_sorted_and_stable() -> None:
    docs = _docs()
    facets = extract_facets(docs, fields=("kind",))
    assert len(facets) == 1
    values = facets[0].values
    assert [item.count for item in values] == sorted((item.count for item in values), reverse=True)
    assert facets[0].total == len(docs)
    assert extract_facets(docs, fields=("kind",)) == facets


def test_facet_counts_for_tags() -> None:
    facets = extract_facets(_docs(), fields=("tag",))
    counts = facet_groups(facets)["tag"]
    assert dict(counts)["web"] == 4
    assert "recon" in dict(counts)


def test_drill_down_counts_exclude_own_selection() -> None:
    docs = _docs()
    facets = extract_facets(docs, fields=("kind",), selected={"kind": ["finding"]})
    values = {item.value: item for item in facets[0].values}
    assert values["finding"].selected
    assert values["finding"].count == sum(1 for doc in docs if doc.kind == "finding")
    assert facets[0].total == len(docs)


def test_cross_field_selection_filters_counts() -> None:
    docs = _docs()
    facets = extract_facets(docs, fields=("severity",), selected={"kind": ["finding"]})
    assert facets[0].total == sum(1 for doc in docs if doc.kind == "finding")
    assert {item.value for item in facets[0].values} >= {"critical", "warning"}


def test_has_link_facet_counts() -> None:
    facets = extract_facets(_docs(), fields=("has_link",))
    values = {item.value: item.count for item in facets[0].values}
    assert values["yes"] > 0
    assert values["no"] > 0


def test_facet_limit_caps_values() -> None:
    facets = extract_facets(_docs(), fields=("tag",), limit=2)
    assert len(facets[0].values) == 2


def test_facet_deltas_reports_selection() -> None:
    facets = extract_facets(_docs(), fields=("kind",), selected={"kind": ["finding"]})
    assert facet_deltas(facets) == {"kind": ("finding",)}


def test_missing_values_are_counted() -> None:
    doc = IndexDocument(ref="note:x", kind="note", title="No severity")
    facets = extract_facets((doc,), fields=("severity",))
    assert facets[0].values[0].value == "(none)"
