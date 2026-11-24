from __future__ import annotations

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.search.models import FilterClause
from redscribe.v2.search.service import SearchService, create_search_service, document_summaries
from redscribe.v2.search.synonyms import SynonymSet
from tests.v2_search.conftest import seed_vault


def service(vault: Vault) -> SearchService:
    return create_search_service(vault)


def test_documents_sync_and_status(vault: Vault) -> None:
    seed_vault(vault)
    engine = service(vault)
    documents = engine.documents()
    assert len(documents) == 3
    summaries = document_summaries(documents)
    assert all(set(item["fields"]) for item in summaries)
    update = engine.sync()
    assert update.added == 3
    assert engine.status()["documents"] == 3
    assert engine.status()["synced"] is True
    assert engine.status()["commands"] >= 10
    assert engine.reindex().changed is True


def test_search_ranks_and_filters(vault: Vault) -> None:
    first, second, _ = seed_vault(vault)
    engine = service(vault)
    result = engine.search("nmap", limit=10)
    assert result.hits
    assert result.hits[0].node_id == first
    assert result.generation >= 3
    assert result.elapsed_ms >= 0
    payload = result.as_dict()
    assert payload["items"][0]["node_id"] == first
    tag_filtered = engine.search("nmap", filters=(FilterClause("tag", ":", "crypto"),))
    assert all(item.node_id != first for item in tag_filtered.hits)
    assert any(item.node_id == second for item in engine.search("authentication").hits)


def test_search_synonyms_and_facets(vault: Vault) -> None:
    seed_vault(vault)
    engine = service(vault)
    empty_synonyms = SearchService(vault, synonyms=SynonymSet.empty())
    broad = engine.search("port").total
    exact = empty_synonyms.search("port").total
    assert broad >= exact
    facets = engine.facets("tag")
    assert {item.value for item in facets} >= {"web", "recon", "crypto"}
    assert engine.term_dictionary(prefix="nma")
    assert engine.suggest("nma")
    assert engine.describe("nmap tag:web")["text"] == "nmap tag:web"


def test_snippet_and_grouping(vault: Vault) -> None:
    first, _, _ = seed_vault(vault)
    engine = service(vault)
    snippet = engine.snippet(first, "nmap")
    assert snippet["text"]
    assert snippet["chunks"]
    assert engine.snippet(9999, "nmap") == {}
    groups = engine.grouped("nmap tag:web", "group")
    assert groups
    assert groups[0].total >= 1


def test_saved_query_workflow(vault: Vault) -> None:
    seed_vault(vault)
    engine = service(vault)
    item = engine.saved.create("Weekly", "nmap", tags="web", pinned=True)
    assert engine.saved.get(item.id) == item
    assert any(item.id == saved.id for saved in engine.saved.list(search="week"))
    updated = engine.saved.update(item.id, query="port", pinned=False)
    assert updated is not None
    assert updated.query == "port"
    assert engine.saved.record_use(item.id) is not None
    assert engine.saved.delete(item.id) is True


def test_command_parse_suggest_completion_and_run(vault: Vault) -> None:
    seed_vault(vault)
    engine = service(vault)
    engine.saved.create("Weekly", "nmap", tags="web")
    parsed = engine.parse_command("/search nmap --limit=5")
    assert parsed.node is not None
    assert parsed.node.name == "search"
    suggestions = engine.command_suggestions("/se")
    assert any(item.label == "/search" for item in suggestions)
    completion = engine.command_completion("/se")
    assert completion.suggestions
    help_payload = engine.command_help()
    assert "grammar" in help_payload
    assert help_payload["commands"]
    run = engine.run_command("/search nmap --limit=5")
    assert run["ok"] is True
    assert run["plan"]["action"] == "search"
    assert "result" in run
    invalid = engine.run_command("/not-a-command")
    assert invalid["ok"] is False


def test_search_limit_and_empty_query(vault: Vault) -> None:
    seed_vault(vault)
    engine = service(vault)
    assert engine.search("nmap", limit=0).hits == ()
    assert engine.search("", limit=5).hits
    with pytest.raises(ValueError):
        engine.search("x" * 501)
