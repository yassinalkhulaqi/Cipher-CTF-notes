from __future__ import annotations

import pytest
from tests.v2_search.conftest import make_document

from redscribe.v2.search.filters import (
    apply_filters,
    clause_matches,
    document_value,
    extract_filters,
    facet_values,
    filter_summary,
    filters_from_dict,
    filters_to_query,
    format_filter,
    parse_filter_token,
    validate_filter_clause,
)
from redscribe.v2.search.models import FilterClause


def test_parse_filter_token_supports_operators() -> None:
    assert parse_filter_token("tag:web") == FilterClause("tag", ":", "web")
    assert parse_filter_token("-tag:web") == FilterClause("tag", ":", "web", True)
    assert parse_filter_token('title:"sql injection"').value == "sql injection"
    assert parse_filter_token("updated>=2026-01-01").operator == ">="
    assert parse_filter_token("status!=closed").operator == "!="
    with pytest.raises(ValueError):
        parse_filter_token("bogus:value")
    with pytest.raises(ValueError):
        parse_filter_token("tag:")
    with pytest.raises(ValueError):
        parse_filter_token("nonsense")


def test_validate_and_format_filters() -> None:
    validate_filter_clause(FilterClause("tag", ":", "web"))
    with pytest.raises(ValueError):
        validate_filter_clause(FilterClause("tag", "??", "web"))
    assert format_filter(FilterClause("tag", ":", "web", True)) == "-tag:web"
    assert format_filter(FilterClause("title", ":", "two words")) == 'title:"two words"'


def test_extract_filters_keeps_free_text() -> None:
    text, filters = extract_filters("nmap tag:web -status:closed path:recon")
    assert text == "nmap"
    assert [item.key for item in filters] == ["tag:web", "-status:closed", "path:recon"]
    assert filters_to_query(filters)


def test_filters_from_dict_ignores_bad_records() -> None:
    clauses = filters_from_dict(
        [
            {"field": "tag", "value": "web"},
            {"field": "status", "operator": "!=", "value": "closed", "negated": True},
        ]
    )
    assert len(clauses) == 2
    with pytest.raises(ValueError):
        filters_from_dict([{"field": "nope", "value": "x"}])
    assert clauses[1].key == "-status!=closed"


def test_document_value_reads_scalar_and_list_metadata() -> None:
    document = make_document(1, tags=("web", "recon"), target="example.com", status="open")
    assert document_value(document, "title") == "Note"
    assert set(document_value(document, "tag")) == {"web", "recon"}
    assert document_value(document, "target") == "example.com"
    assert document_value(document, "node_id") == 1
    assert document_value(document, "missing") is None


def test_clause_matches_string_and_numeric_filters() -> None:
    document = make_document(1, tags=("web",), status="open")
    assert clause_matches(document, FilterClause("tag", ":", "web"))
    assert not clause_matches(document, FilterClause("tag", ":", "crypto"))
    assert clause_matches(document, FilterClause("status", "!=", "closed"))
    assert clause_matches(document, FilterClause("node_id", ">", "0"))
    assert clause_matches(document, FilterClause("node_id", "<=", "1"))
    assert not clause_matches(document, FilterClause("title", "~", "missing"))


def test_apply_filters_combines_clauses() -> None:
    documents = [
        make_document(1, tags=("web",), status="open"),
        make_document(2, tags=("web",), status="closed"),
        make_document(3, tags=("crypto",), status="open"),
    ]
    result = apply_filters(
        documents,
        (FilterClause("tag", ":", "web"), FilterClause("status", ":", "open")),
    )
    assert [item.doc_id for item in result] == [1]
    excluded = apply_filters(documents, (FilterClause("tag", ":", "web", True),))
    assert [item.doc_id for item in excluded] == [3]


def test_facet_values_counts_metadata_values() -> None:
    documents = [
        make_document(1, tags=("web", "recon"), status="open"),
        make_document(2, tags=("web",), status="closed"),
    ]
    facets = facet_values(documents, "tag")
    assert facets[0].value == "web"
    assert facets[0].count == 2
    statuses = {item.value: item.count for item in facet_values(documents, "status")}
    assert statuses == {"open": 1, "closed": 1}
    assert facet_values(documents, "missing") == ()


def test_filter_summary_describes_clauses() -> None:
    summary = filter_summary(
        (FilterClause("tag", ":", "web"), FilterClause("status", "!=", "closed"))
    )
    assert "tag" in summary
    assert "status" in summary
    assert filter_summary(())
