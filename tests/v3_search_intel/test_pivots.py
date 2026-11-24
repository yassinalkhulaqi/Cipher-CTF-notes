"""Cross-entity pivot suggestions and navigation chains."""

from __future__ import annotations

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import EntityKind, LinkKind
from redscribe.v3.search_intel.pivots import (
    pivot_chain,
    pivot_context,
    pivot_query,
    suggest_pivots,
)
from tests.v3_search_intel.helpers import build_service, ref


def test_pivot_query_is_valid_v2_syntax() -> None:
    assert pivot_query("finding", "TLS issue") == 'kind:finding "TLS issue"'


def test_pivot_query_escapes_quotes() -> None:
    assert pivot_query("note", 'say "hi"') == 'kind:note "say hi"'
    assert pivot_query("note", "") == "kind:note"


def test_direct_pivots_include_evidence_and_report() -> None:
    service = build_service()
    suggestions = suggest_pivots(ref("finding", "finding-01"), service.entities)
    kinds = {item.kind for item in suggestions}
    assert "evidence" in kinds
    assert "report" in kinds
    assert all(item.ref != ref("finding", "finding-01") for item in suggestions)


def test_pivot_roles_and_link_kinds() -> None:
    service = build_service()
    suggestions = suggest_pivots(ref("finding", "finding-01"), service.entities)
    evidence = next(item for item in suggestions if item.kind == "evidence")
    assert evidence.role == "evidences"
    assert evidence.link_kind == "evidences"
    report = next(item for item in suggestions if item.kind == "report")
    assert report.role == "report"


def test_pivot_suggestions_are_scored_and_deterministic() -> None:
    service = build_service()
    first = suggest_pivots(ref("finding", "finding-01"), service.entities)
    second = suggest_pivots(ref("finding", "finding-01"), service.entities)
    assert first == second
    assert [item.score for item in first] == sorted((item.score for item in first), reverse=True)


def test_pivot_kind_filter() -> None:
    service = build_service()
    suggestions = suggest_pivots(
        ref("finding", "finding-01"), service.entities, kinds=("evidence",)
    )
    assert {item.kind for item in suggestions} == {"evidence"}


def test_depth_two_reaches_further() -> None:
    service = build_service()
    shallow = suggest_pivots(ref("finding", "finding-01"), service.entities, depth=1)
    deeper = suggest_pivots(ref("finding", "finding-01"), service.entities, depth=2)
    assert len(deeper) >= len(shallow)
    assert any(item.depth == 2 for item in deeper)


def test_unknown_ref_has_no_pivots() -> None:
    service = build_service()
    assert suggest_pivots("finding:missing", service.entities) == ()
    assert suggest_pivots("not-a-ref", service.entities) == ()


def test_pivot_chain_finds_report() -> None:
    service = build_service()
    chain = pivot_chain(ref("finding", "finding-01"), service.entities, "report")
    assert chain[0] == ref("finding", "finding-01")
    assert chain[-1] == ref("report", "report-01")


def test_pivot_chain_missing_kind() -> None:
    service = build_service()
    assert pivot_chain(ref("finding", "finding-01"), service.entities, "extension") == ()


def test_pivot_context_retains_origin() -> None:
    service = build_service()
    context = pivot_context(ref("finding", "finding-01"), service.entities)
    assert context["origin"] == ref("finding", "finding-01")
    assert context["origin_kind"] == "finding"
    assert context["origin_title"] == "TLS misconfiguration"
    assert "evidence" in context["destinations"]


def test_pivot_without_links_is_empty() -> None:
    service = EntityService(clock=FixedClock(start=100.0))
    service.create(EntityKind.NOTE, title="Isolated", value="lonely")
    assert suggest_pivots(ref("note", "lonely"), service) == ()


def test_owns_role_from_contains_direction() -> None:
    service = EntityService(clock=FixedClock(start=100.0))
    parent = service.create(EntityKind.FOLDER, title="Folder", value="f1")
    child = service.create(EntityKind.NOTE, title="Note", value="n1")
    service.link(parent.entity_id, child.entity_id, kind=LinkKind.CONTAINS)
    suggestions = suggest_pivots(ref("note", "n1"), service)
    folder = next(item for item in suggestions if item.kind == "folder")
    assert folder.role == "owns"
