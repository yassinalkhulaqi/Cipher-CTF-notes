from __future__ import annotations

from redscribe.v2.search.index import InvertedIndex
from redscribe.v2.search.models import SortKey
from redscribe.v2.search.query import QueryParser
from redscribe.v2.search.ranking import (
    RankingConfig,
    RankingEngine,
    facet_counts,
    group_hits,
    highlight_preview,
    matched_term_count,
    query_coverage,
    rerank_by_group,
    score_label,
    sort_hits,
)
from redscribe.v2.search.synonyms import SynonymSet
from tests.v2_search.conftest import make_document


def test_ranking_config_boosts() -> None:
    config = RankingConfig()
    adjusted = config.with_boosts({"title": 10.0})
    assert adjusted.field_boosts["title"] == 10.0
    assert config.field_boosts["title"] != 10.0


def test_score_rewards_field_boosts() -> None:
    engine = RankingEngine()
    index = InvertedIndex()
    title_doc = make_document(1, title="nmap scan", content="unrelated words")
    content_doc = make_document(2, title="unrelated", content="nmap nmap nmap")
    index.add(title_doc)
    index.add(content_doc)
    query = QueryParser(SynonymSet.empty()).parse("nmap")
    title_score = engine.score(query, title_doc, index).total
    content_score = engine.score(query, content_doc, index).total
    assert title_score > content_score


def test_rank_orders_by_relevance_and_limits() -> None:
    engine = RankingEngine()
    index = InvertedIndex()
    documents = [
        make_document(1, title="nmap nmap nmap", content="nmap ports", tags=("nmap",)),
        make_document(2, title="Web", content="http service"),
        make_document(3, title="Port scan", content="nmap port scan"),
    ]
    for document in documents:
        index.add(document)
    query = QueryParser(SynonymSet.empty()).parse("nmap")
    hits = engine.rank(query, documents, index, limit=2)
    assert len(hits) == 2
    assert hits[0].node_id in {1, 3}
    assert hits[0].score >= hits[1].score
    assert engine.explain(hits[0])
    assert hits[0].score_details.total > 0


def test_rank_sort_keys() -> None:
    engine = RankingEngine()
    index = InvertedIndex()
    documents = [
        make_document(1, title="Alpha", updated_at="2026-01-01T00:00:00Z"),
        make_document(2, title="Beta", updated_at="2026-02-01T00:00:00Z"),
    ]
    for document in documents:
        index.add(document)
    query = QueryParser(SynonymSet.empty()).parse("alpha beta")
    updated = engine.rank(query, documents, index, sort=SortKey.UPDATED)
    titled = engine.rank(query, documents, index, sort=SortKey.TITLE)
    assert updated[0].node_id == 2
    assert titled[0].node_id == 1


def test_group_hits_and_rerank() -> None:
    engine = RankingEngine()
    index = InvertedIndex()
    documents = [
        make_document(1, title="Nmap", group="recon"),
        make_document(2, title="Scan", group="web"),
        make_document(3, title="Port", group="recon"),
    ]
    for document in documents:
        index.add(document)
    query = QueryParser(SynonymSet.empty()).parse("nmap scan port")
    hits = engine.rank(query, documents, index, limit=10, group_by="group")
    groups = group_hits(hits, "group")
    assert [group.key for group in groups] == ["recon", "web"]
    assert groups[0].total == 2
    preferred = rerank_by_group(hits, "web")
    assert preferred[0].group == "web"
    assert len(sort_hits(hits, SortKey.ID)) == 3


def test_coverage_and_matched_terms() -> None:
    engine = RankingEngine()
    index = InvertedIndex()
    document = make_document(1, title="nmap scan", content="port")
    index.add(document)
    query = QueryParser(SynonymSet.empty()).parse("nmap missing")
    assert matched_term_count(query, document, index) == 1
    assert 0 < query_coverage(query, document, index) < 1
    hits = engine.rank(query, (document,), index, limit=1)
    assert highlight_preview(hits[0])


def test_facet_counts_and_score_label() -> None:
    documents = [
        make_document(1, tags=("web", "recon")),
        make_document(2, tags=("web",)),
    ]
    facets = facet_counts(documents, "tag")
    assert facets[0].value == "web"
    assert facets[0].count == 2
    assert score_label(100) in {"exact", "strong", "high"}
    assert score_label(0) in {"weak", "none", "low"}
