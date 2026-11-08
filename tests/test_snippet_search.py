from __future__ import annotations

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api


def test_search_snippets_matches_titles_and_commands(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap"})

    assert results
    assert any("nmap" in item["title"].lower() for item in results)
    assert all("nmap" in item["command"].lower() or "nmap" in item["title"].lower() for item in results)


def test_search_snippets_ranks_exact_title_hits_first(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap full tcp"})

    assert results
    assert "full tcp" in results[0]["title"].lower()


def test_search_snippets_includes_custom_snippets(vault: Vault) -> None:
    vault.create_snippet(
        "My gobustermole",
        "gobuster dir -u {{target}} -w wordlist.txt",
        "custom directory fuzzing",
        "web",
    )
    api = Api(vault)

    results = api.search_snippets({"query": "gobustermole"})

    assert len(results) == 1
    assert results[0]["title"] == "My gobustermole"
    assert results[0]["builtin"] is False


def test_search_snippets_returns_empty_for_misses(vault: Vault) -> None:
    api = Api(vault)

    assert api.search_snippets({"query": "zzzz-no-such-snippet-zzzz"}) == []


def test_search_snippets_respects_the_limit(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap", "limit": 1})

    assert len(results) == 1


def test_search_snippets_available_through_the_dispatcher(vault: Vault) -> None:
    api = Api(vault)

    results = api.handle("search_snippets", {"query": "shell"})

    assert results
    assert results[0]["title"]
