"""Ranking, fragment rendering, and score stability."""

from __future__ import annotations

from redscribe.v3.search_intel.ranking import (
    build_fragment,
    clause_matches,
    query_matches,
    rank_documents,
    rank_stable,
    score_document,
)
from redscribe.v3.search_intel.types import ClauseKind, IndexDocument, QueryClause
from tests.v3_search_intel.helpers import build_service


def test_clause_matches_field_and_term() -> None:
    doc = IndexDocument(
        ref="finding:x",
        kind="finding",
        title="Weak TLS",
        summary="Cipher suites",
        tags=("web",),
        status="active",
        severity="critical",
    )
    field = QueryClause(kind=ClauseKind.FIELD, field="kind", value="finding")
    assert clause_matches(doc, field) == (True, ())
    negated = QueryClause(kind=ClauseKind.FIELD, field="kind", value="finding", negated=True)
    assert clause_matches(doc, negated) == (False, ())
    term = QueryClause(kind=ClauseKind.TERM, value="tls")
    assert clause_matches(doc, term)[0]
    missing = QueryClause(kind=ClauseKind.TERM, value="absent")
    assert clause_matches(doc, missing) == (False, ())


def test_clause_matches_has_link_filter() -> None:
    doc = IndexDocument(
        ref="finding:x",
        kind="finding",
        title="T",
        has_links=True,
        link_kinds=("evidences",),
    )
    link = QueryClause(kind=ClauseKind.HAS_LINK, value="link")
    assert clause_matches(doc, link)[0]
    specific = QueryClause(kind=ClauseKind.HAS_LINK, value="link", link_kind="evidences")
    assert clause_matches(doc, specific)[0]
    wrong = QueryClause(kind=ClauseKind.HAS_LINK, value="link", link_kind="derives")
    assert not clause_matches(doc, wrong)[0]


def test_query_matches_or_groups() -> None:
    service = build_service()
    parsed = service.parse("kind:evidence OR kind:report")
    docs = service.index.documents()
    assert sum(query_matches(doc, parsed)[0] for doc in docs) == 2


def test_ranking_is_stable_and_explained() -> None:
    service = build_service()
    parsed = service.parse("kind:finding")
    hits = rank_documents(service.index.documents(), parsed)
    assert hits
    assert rank_stable(hits)
    assert all(hit.score == hit.details.total for hit in hits)
    assert all("title" in hit.details.components for hit in hits)


def test_ranking_is_deterministic() -> None:
    service = build_service()
    parsed = service.parse("web")
    docs = service.index.documents()
    assert rank_documents(docs, parsed) == rank_documents(docs, parsed)


def test_ranking_limit() -> None:
    service = build_service()
    hits = rank_documents(service.index.documents(), service.parse("kind:finding"), limit=1)
    assert len(hits) == 1


def test_title_matches_score_higher_than_summary() -> None:
    service = build_service()
    docs = service.index.documents()
    title_hit = rank_documents(docs, service.parse("TLS"))[0]
    summary_hit = rank_documents(docs, service.parse("cipher"))[0]
    assert title_hit.details.components["title"] > 0
    assert summary_hit.details.components["content"] > 0


def test_recency_component_requires_now() -> None:
    service = build_service()
    doc = service.index.documents()[0]
    parsed = service.parse("web")
    details = score_document(doc, parsed, matched_terms=("web",), now=doc.updated_at + 10)
    assert details.components["recency"] > 0
    assert score_document(doc, parsed, matched_terms=("web",)).components["recency"] == 0


def test_fragment_highlights_offsets() -> None:
    doc = IndexDocument(
        ref="finding:x", kind="finding", title="TLS", summary="Weak TLS cipher suites"
    )
    fragment = build_fragment(doc, ("tls",))
    assert fragment.text.casefold().count("tls") == len(fragment.highlights)
    for highlight in fragment.highlights:
        assert fragment.text[highlight.start : highlight.end].casefold() == "tls"


def test_fragment_window_and_flags() -> None:
    doc = IndexDocument(ref="note:x", kind="note", title="Long", summary=("word " * 100).strip())
    fragment = build_fragment(doc, (), width=40)
    assert len(fragment.text) == 40
    assert fragment.suffix


def test_fragment_empty_summary_falls_back_to_title() -> None:
    doc = IndexDocument(ref="note:x", kind="note", title="Fallback title")
    fragment = build_fragment(doc, ("fallback",))
    assert "Fallback" in fragment.text
    assert fragment.highlights
