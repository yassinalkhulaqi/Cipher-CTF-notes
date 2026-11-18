from __future__ import annotations

import pytest
from tests.v2_search.conftest import seed_vault

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import V2Error
from redscribe.ui.web.v2.namespaces.search import get_service, register
from redscribe.ui.web.v2.routes import ApiV2

ROUTES = (
    "search.query",
    "search.suggest",
    "search.facets",
    "search.snippet",
    "search.terms",
    "search.status",
    "search.reindex",
    "search.describe",
    "saved.list",
    "saved.get",
    "saved.create",
    "saved.update",
    "saved.delete",
    "saved.use",
    "commands.parse",
    "commands.suggest",
    "commands.complete",
    "commands.list",
    "commands.help",
    "commands.run",
)


def api(vault: Vault) -> ApiV2:
    instance = ApiV2(vault)
    register(instance)
    return instance


def test_register_is_idempotent_and_adds_all_routes(vault: Vault) -> None:
    instance = api(vault)
    before = set(instance.routes)
    register(instance)
    assert set(instance.routes) == before
    assert set(ROUTES) <= before
    for name in ROUTES:
        assert instance.route(name).name == name
        assert instance.route(name).as_schema()["name"] == name


def test_service_is_cached_per_api(vault: Vault) -> None:
    instance = api(vault)
    assert get_service(instance) is get_service(instance)
    other = api(vault)
    assert get_service(other) is not get_service(instance)


def test_search_routes(vault: Vault) -> None:
    first, _, _ = seed_vault(vault)
    instance = api(vault)
    result = instance.invoke("search.query", {"query": "nmap", "limit": 5})
    payload = result.data["result"]
    assert payload["items"]
    assert payload["items"][0]["node_id"] == first
    assert result.data["page"]["limit"] == 5
    assert result.etag
    assert instance.invoke("search.suggest", {"query": "nma"}).data["suggestions"]
    assert instance.invoke("search.facets", {"field": "tag"}).data["facets"]
    assert instance.invoke("search.terms", {}).data["terms"]
    assert instance.invoke("search.status", {}).data["documents"] == 3
    assert instance.invoke("search.describe", {"query": "nmap"}).data["text"] == "nmap"
    assert instance.invoke("search.reindex", {}).data["changed"] is True
    snippet = instance.invoke("search.snippet", {"id": first, "query": "nmap"}).data
    assert snippet["text"]


def test_search_route_validation(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    with pytest.raises(V2Error):
        instance.invoke("search.query", {"limit": 0})
    with pytest.raises(V2Error):
        instance.invoke("search.query", {"filters": "tag:web"})
    with pytest.raises(V2Error):
        instance.invoke("search.facets", {})
    with pytest.raises(V2Error):
        instance.invoke("search.snippet", {"id": 9999, "query": "nmap"})


def test_saved_routes(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    created = instance.invoke(
        "saved.create",
        {"name": "Weekly", "query": "nmap", "tags": ["web"], "pinned": True},
    )
    assert created.status == 201
    saved_id = created.data["id"]
    assert instance.invoke("saved.list", {}).data["items"][0]["id"] == saved_id
    assert instance.invoke("saved.get", {"id": saved_id}).data["name"] == "Weekly"
    updated = instance.invoke("saved.update", {"id": saved_id, "name": "Renamed"})
    assert updated.data["name"] == "Renamed"
    used = instance.invoke("saved.use", {"id": saved_id})
    assert used.data["saved"]["use_count"] == 1
    assert used.data["result"]["items"]
    assert instance.invoke("saved.delete", {"id": saved_id}).data["removed"] is True
    with pytest.raises(V2Error):
        instance.invoke("saved.get", {"id": saved_id})
    with pytest.raises(V2Error):
        instance.invoke("saved.create", {"name": "", "query": "nmap"})


def test_command_routes(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    parsed = instance.invoke("commands.parse", {"text": "/search nmap --limit=5"}).data
    assert parsed["node"]["name"] == "search"
    assert parsed["plan"]["action"] == "search"
    assert instance.invoke("commands.suggest", {"text": "/se"}).data["suggestions"]
    completion = instance.invoke("commands.complete", {"text": "/se"}).data
    assert completion["suggestions"]
    assert instance.invoke("commands.list", {}).data["commands"]
    assert instance.invoke("commands.help", {"text": "search"}).data["commands"]
    run = instance.invoke("commands.run", {"text": "/search nmap"}).data
    assert run["ok"] is True
    with pytest.raises(V2Error):
        instance.invoke("commands.parse", {})


def test_system_capabilities_include_search_namespace(vault: Vault) -> None:
    instance = api(vault)
    capabilities = instance.invoke("system.capabilities", {}).data
    namespaces = capabilities["namespaces"]
    assert "search" in namespaces or "search" in str(namespaces)
    schema = instance.invoke("system.api_schema", {}).data
    assert "search.query" in schema["route_names"] or any(
        item["name"] == "search.query" for item in schema["routes"]
    )
