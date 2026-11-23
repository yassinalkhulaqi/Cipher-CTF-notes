from __future__ import annotations

from redscribe.v2.search.index import InvertedIndex
from tests.v2_search.conftest import make_document


def test_empty_index_stats() -> None:
    index = InvertedIndex()
    assert len(index) == 0
    assert 1 not in index
    assert index.documents() == ()
    stats = index.stats().as_dict()
    assert stats["documents"] == 0
    assert stats["generation"] == 0


def test_add_postings_and_term_stats() -> None:
    index = InvertedIndex()
    index.add(make_document(1, title="Nmap scan", content="open ports", tags=("web",)))
    index.add(make_document(2, title="Port scan", content="ssh service", tags=("recon",)))
    assert 1 in index
    assert len(index) == 2
    postings = index.postings("nmap")
    assert len(postings) == 1
    assert postings[0].doc_id == 1
    assert postings[0].field == "title"
    stats = index.term_stats("nmap")
    assert stats.document_frequency == 1
    assert stats.total_frequency >= 1
    assert "title" in stats.fields
    assert index.field_length(1, "title") > 0
    assert "scan" in index.terms_for(1)


def test_sync_tracks_added_updated_removed_and_unchanged() -> None:
    index = InvertedIndex()
    first = make_document(1, title="Nmap")
    second = make_document(2, title="Web")
    initial = index.sync([first, second])
    assert initial.added == 2
    assert initial.unchanged == 0
    assert initial.changed is True
    assert initial.generation == 2
    repeat = index.sync([first, second])
    assert repeat.added == 0
    assert repeat.updated == 0
    assert repeat.unchanged == 2
    changed = make_document(1, title="Nmap updated")
    update = index.sync([changed, second])
    assert update.updated == 1
    assert update.unchanged == 1
    removed = index.sync([changed])
    assert removed.removed == 1
    assert 2 not in index


def test_rebuild_resets_and_increments_counter() -> None:
    index = InvertedIndex()
    index.rebuild([make_document(1), make_document(2)])
    first_generation = index.generation
    update = index.rebuild([make_document(3)])
    assert len(index) == 1
    assert update.added == 1
    assert update.generation > first_generation
    assert index.stats().rebuilds == 2


def test_remove_and_clear() -> None:
    index = InvertedIndex()
    index.add(make_document(1))
    assert index.remove(1) is True
    assert index.remove(1) is False
    index.add(make_document(2))
    index.clear()
    assert len(index) == 0
    assert index.documents() == ()


def test_matching_documents_and_field_scoped_postings() -> None:
    index = InvertedIndex()
    index.add(make_document(1, title="Nmap scan", content="port"))
    index.add(make_document(2, title="Web scan", content="http"))
    assert index.matching_documents(("scan",)) == frozenset({1, 2})
    assert index.matching_documents(("nmap", "scan")) == frozenset({1})
    assert index.matching_documents(("nmap", "http"), require_all=False) == frozenset({1, 2})
    assert index.documents_for_term("port", field="content") == frozenset({1})
    assert index.postings("port", field="title") == ()


def test_prefix_and_fuzzy_terms() -> None:
    index = InvertedIndex()
    index.add(make_document(1, title="scanning scanner", content="nmap"))
    vocabulary = index.vocabulary()
    assert vocabulary
    assert any(item.startswith("scan") for item in index.prefix_terms("scan"))
    assert len(index.prefix_terms("scan", limit=1)) <= 1
    assert "nmap" in index.fuzzy_terms("nmab", limit=5)


def test_serialization_round_trip() -> None:
    index = InvertedIndex()
    index.add(make_document(1, title="Nmap notes", tags=("web",)))
    payload = index.serialize()
    assert payload["version"] == 1
    restored = InvertedIndex.deserialize(payload)
    assert restored.generation == index.generation
    assert restored.documents() == index.documents()
    assert restored.postings("nmap")[0].doc_id == 1
