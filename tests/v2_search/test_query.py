from __future__ import annotations

import pytest

from redscribe.v2.search.models import SortKey
from redscribe.v2.search.query import (
    QueryParser,
    describe_query,
    lex_query,
    query_fingerprint,
    query_to_text,
    suggest_query_completions,
)
from redscribe.v2.search.synonyms import SynonymSet


def test_lex_query_exposes_operators_and_modifiers() -> None:
    lexemes = lex_query('title:"sql injection"^3 +port* -noise~')
    assert lexemes
    values = {lexeme.text for lexeme in lexemes}
    assert "sql injection" in values
    assert any(lexeme.field == "title" for lexeme in lexemes)
    assert any(lexeme.boost > 1 for lexeme in lexemes)
    assert any(lexeme.prefix for lexeme in lexemes)
    assert any(lexeme.negated for lexeme in lexemes)


def test_parser_extracts_terms_filters_and_sort() -> None:
    query = QueryParser(SynonymSet.empty()).parse(
        'nmap "open ports" tag:web -noise',
        sort="updated",
        group_by="tag",
    )
    assert query.sort is SortKey.UPDATED
    assert query.group_by == "tag"
    assert any(term.phrase for term in query.terms)
    assert any(term.negated for term in query.terms)
    assert {item.field for item in query.filters} == {"tag"}
    assert query.positive
    assert query.negative


def test_synonym_expansion_marks_optional_terms() -> None:
    parser = QueryParser(SynonymSet([("scan", "nmap")]))
    query = parser.parse("scan")
    assert any(term.synonym and term.optional for term in query.terms)
    assert query.terms[0].value == "scan"


def test_parser_rejects_bad_input() -> None:
    parser = QueryParser()
    with pytest.raises(TypeError):
        parser.parse(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parser.parse("x" * 501)


def test_query_fingerprint_is_stable() -> None:
    parser = QueryParser(SynonymSet.empty())
    first = parser.parse("NMAP tag:web")
    second = parser.parse("nmap tag:web")
    other = parser.parse("ssh tag:web")
    assert query_fingerprint(first) == query_fingerprint(second)
    assert query_fingerprint(first) != query_fingerprint(other)
    assert len(query_fingerprint(first)) == 64


def test_query_to_text_and_describe_query() -> None:
    query = QueryParser(SynonymSet.empty()).parse("title:nmap tag:web", sort="title")
    described = describe_query(query)
    assert described["text"] == "title:nmap tag:web"
    assert described["sort"] == "title"
    assert any(item["field"] == "tag" for item in described["filters"])
    assert "nmap" in query_to_text(query)


def test_suggest_query_completions_uses_vocabulary() -> None:
    query = QueryParser(SynonymSet.empty()).parse("nma")
    suggestions = suggest_query_completions(query.text, ("nmap", "nmapp", "ssh"), limit=2)
    assert "nmap" in suggestions
    assert len(suggestions) <= 2
