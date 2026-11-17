from __future__ import annotations

from tests.v2_search.conftest import make_document

from redscribe.v2.search.models import SortKey
from redscribe.v2.search.query import QueryParser
from redscribe.v2.search.snippets import (
    build_document_snippet,
    build_snippet,
    find_query_spans,
    find_term_spans,
    highlight_chunks,
    merge_spans,
    token_offsets,
)
from redscribe.v2.search.synonyms import SynonymSet


def test_find_term_spans_matches_offsets() -> None:
    spans = find_term_spans("Nmap nmap scanning", "nmap")
    assert len(spans) == 2
    assert spans[0].start == 0
    assert spans[0].end == 4
    assert spans[1].start == 5
    assert all(span.term == "nmap" for span in spans)


def test_find_query_spans_deduplicates() -> None:
    spans = find_query_spans("nmap scanning scan", ("scan", "nmap"))
    assert spans
    assert len({(span.start, span.end) for span in spans}) == len(spans)


def test_merge_spans_combines_overlaps() -> None:
    from redscribe.v2.search.models import HighlightSpan

    merged = merge_spans(
        [
            HighlightSpan(0, 4, "nmap"),
            HighlightSpan(3, 8, "scan"),
            HighlightSpan(10, 12, "80"),
        ]
    )
    assert len(merged) == 2
    assert merged[0].end == 8


def test_build_snippet_highlights_and_chunks() -> None:
    snippet = build_snippet("Nmap found open ports on the target", ("nmap", "port"), width=80)
    assert snippet.matched is True
    assert snippet.highlights
    assert snippet.fragments >= 1
    chunks = highlight_chunks(snippet)
    assert any(chunk.match for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == snippet.text


def test_build_snippet_truncates_without_matches() -> None:
    snippet = build_snippet("x" * 100, ("missing",), width=20)
    assert snippet.matched is False
    assert len(snippet.text) <= 21
    assert build_snippet("", ("nmap",)) == build_snippet("", ("nmap",))


def test_build_document_snippet_prefers_matching_field() -> None:
    document = make_document(
        1,
        title="Nmap notes",
        content="This content mentions nmap scanning and open ports",
        tags=("recon",),
    )
    query = QueryParser(SynonymSet.empty()).parse("nmap", sort=SortKey.RELEVANCE.value)
    snippet = build_document_snippet(document, query, width=60)
    assert snippet.matched is True
    assert any("nmap" in span.term for span in snippet.highlights)


def test_build_document_snippet_falls_back_to_content() -> None:
    document = make_document(1, title="Plain", content="some content", tags=("web",))
    query = QueryParser(SynonymSet.empty()).parse("missing")
    snippet = build_document_snippet(document, query)
    assert snippet.matched is False
    assert snippet.text == "some content"


def test_token_offsets_preserve_source_positions() -> None:
    tokens = token_offsets("nmap found 80 ports")
    assert tokens[0].start == 0
    assert tokens[1].start == 5
    assert tokens[2].text == "80"
