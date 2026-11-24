from __future__ import annotations

import json

from redscribe.v2.search.models import (
    DEFAULT_FIELD_BOOSTS,
    MAX_QUERY_LENGTH,
    MAX_SEARCH_LIMIT,
    FacetCount,
    FilterClause,
    IndexedDocument,
    IndexedField,
    IndexUpdate,
    ParsedQuery,
    QueryTerm,
    SavedQuery,
    SearchField,
    SortKey,
    Token,
    utc_now,
)
from tests.v2_search.conftest import make_document


def test_field_boosts_cover_every_search_field() -> None:
    assert set(DEFAULT_FIELD_BOOSTS) == {field.value for field in SearchField}
    assert DEFAULT_FIELD_BOOSTS["title"] > DEFAULT_FIELD_BOOSTS["content"]
    assert all(value > 0 for value in DEFAULT_FIELD_BOOSTS.values())


def test_limits_are_bounded() -> None:
    assert MAX_QUERY_LENGTH == 500
    assert MAX_SEARCH_LIMIT == 100


def test_token_as_dict_keeps_offsets() -> None:
    token = Token(text="Scanning", normalized="scanning", start=4, end=12, field="title")
    payload = token.as_dict()
    assert payload["start"] == 4
    assert payload["end"] == 12
    assert payload["field"] == "title"
    assert token.length == 8


def test_indexed_field_length_and_serialization() -> None:
    tokens = (Token("web", "web", 0, 3, "tags"), Token("scan", "scan", 4, 8, "tags"))
    field = IndexedField("tags", "web scan", tokens, 4.0)
    assert field.length == 2
    restored = IndexedField.from_dict(field.as_dict())
    assert restored == field


def test_document_helpers_and_round_trip() -> None:
    document = make_document(3, title="Nmap", tags=("web", "recon"))
    assert document.title == "Nmap"
    assert document.field_text("content") == "body text"
    assert document.field("missing") is None
    assert document.pinned is False
    assert document.fingerprint()
    restored = IndexedDocument.from_dict(document.as_dict())
    assert restored.fingerprint() == document.fingerprint()


def test_index_update_summary() -> None:
    update = IndexUpdate(added=2, updated=1, generation=4)
    assert update.changed is True
    assert update.as_dict() == {
        "added": 2,
        "updated": 1,
        "removed": 0,
        "unchanged": 0,
        "generation": 4,
        "changed": True,
    }
    assert IndexUpdate().changed is False


def test_filter_clause_key_and_serialization() -> None:
    clause = FilterClause("tag", ":", "web", negated=True)
    assert clause.key == "-tag:web"
    assert FilterClause.from_dict(clause.as_dict()) == clause


def test_query_term_and_query_serialization() -> None:
    term = QueryTerm("nmap", field="title", boost=2.5, prefix=True)
    assert term.key == "title:nmap"
    query = ParsedQuery(
        "title:nmap tag:web",
        terms=(term,),
        filters=(FilterClause("tag", ":", "web"),),
        sort=SortKey.UPDATED,
        group_by="tag",
    )
    payload = query.as_dict()
    assert payload["sort"] == "updated"
    assert payload["filters"][0]["field"] == "tag"
    assert query.positive == (term,)
    assert query.negative == ()
    assert query.phrases == ()


def test_saved_query_round_trip() -> None:
    item = SavedQuery(
        id="sq_1",
        name="Weekly review",
        query="tag:web nmap",
        description="review scan notes",
        tags=("web", "recon"),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-02T00:00:00Z",
        use_count=3,
        pinned=True,
    )
    payload = item.as_dict()
    assert json.loads(json.dumps(payload))["tags"] == ["web", "recon"]
    assert SavedQuery.from_dict(payload) == item


def test_facet_and_result_group_serialization() -> None:
    facet = FacetCount("web", 4)
    assert facet.as_dict() == {"value": "web", "count": 4}
    from redscribe.v2.search.models import ResultGroup, ScoreBreakdown, SearchHit, Snippet

    hit = SearchHit(
        node_id=1,
        title="Note",
        path="note.md",
        snippet=Snippet("nmap"),
        score=2.0,
        score_details=ScoreBreakdown(2.0),
    )
    group = ResultGroup("web", "Web", (hit,), 1)
    assert group.as_dict()["total"] == 1
    assert group.as_dict()["hits"][0]["node_id"] == 1


def test_utc_now_is_iso8601() -> None:
    value = utc_now()
    assert "T" in value
    assert value.endswith("+00:00")
