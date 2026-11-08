from __future__ import annotations

from redscribe.services.graph import (
    GRAPH_EDGE_LINK,
    GRAPH_EDGE_PARENT,
    build_vault_graph,
    graph_payload,
)
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api


def _parent_pairs(graph) -> set[tuple[int, int]]:
    return {
        (edge.source, edge.target)
        for edge in graph.edges
        if edge.kind == GRAPH_EDGE_PARENT
    }


def _resolved_links(graph, source: int) -> list:
    return [
        edge
        for edge in graph.edges
        if edge.kind == GRAPH_EDGE_LINK and edge.source == source and edge.resolved
    ]


def _dangling_links(graph, source: int) -> list:
    return [
        edge
        for edge in graph.edges
        if edge.kind == GRAPH_EDGE_LINK and edge.source == source and not edge.resolved
    ]


def test_graph_on_empty_vault_is_empty(vault: Vault) -> None:
    graph = build_vault_graph(vault)
    assert graph.nodes == ()
    assert graph.edges == ()


def test_graph_includes_folders_and_notes_as_vertices(vault: Vault) -> None:
    folder = vault.create_node("CTF", kind="folder")
    note = vault.create_node("HTB Corporate", folder.id, content="flag{...}")

    graph = build_vault_graph(vault)

    kinds = {node.kind for node in graph.nodes}
    assert kinds == {"folder", "note"}
    assert any(node.id == folder.id and node.kind == "folder" for node in graph.nodes)
    assert any(node.id == note.id and node.kind == "note" for node in graph.nodes)


def test_graph_links_parent_child_hierarchy(vault: Vault) -> None:
    root = vault.create_node("CTF", kind="folder")
    nested = vault.create_node("HTB", root.id, kind="folder")
    note = vault.create_node("Writeup", nested.id, content="flag{...}")

    graph = build_vault_graph(vault)

    pairs = _parent_pairs(graph)
    assert (root.id, nested.id) in pairs
    assert (nested.id, note.id) in pairs


def test_graph_resolves_wikilinks_to_notes(vault: Vault) -> None:
    note = vault.create_node("Writeup", content="See also [[HTB Corporate]] for scope.")
    other = vault.create_node("HTB Corporate", content="flag{...}")

    graph = build_vault_graph(vault)

    resolved = _resolved_links(graph, note.id)
    assert len(resolved) == 1
    assert resolved[0].target == other.id


def test_graph_deduplicates_repeated_wikilinks(vault: Vault) -> None:
    source = vault.create_node("Writeup", content="[[Beta]] then [[Beta|the other]]")
    target = vault.create_node("Beta", content="flag{...}")

    graph = build_vault_graph(vault)

    resolved = _resolved_links(graph, source.id)
    assert len(resolved) == 1
    assert resolved[0].target == target.id


def test_graph_creates_dangling_reference_for_missing_wikilink(vault: Vault) -> None:
    note = vault.create_node("Writeup", content="Remember [[Missing Note]] someday.")

    graph = build_vault_graph(vault)

    dangling = _dangling_links(graph, note.id)
    assert len(dangling) == 1
    reference = next(node for node in graph.nodes if node.id == dangling[0].target)
    assert reference.kind == "reference"
    assert reference.resolved is False


def test_graph_ignores_self_referential_wikilinks(vault: Vault) -> None:
    note = vault.create_node("Alpha", content="[[Alpha]] is the root of all links.")

    graph = build_vault_graph(vault)

    assert _resolved_links(graph, note.id) == []


def test_graph_payload_serializes_vertices_and_edges(vault: Vault) -> None:
    folder = vault.create_node("CTF", kind="folder")
    vault.create_node("Writeup", folder.id, content="[[HTB Corporate]]")

    payload = graph_payload(build_vault_graph(vault))

    assert set(payload) == {"nodes", "edges"}
    assert payload["nodes"][0]["id"] == folder.id
    assert payload["edges"][0]["kind"] == GRAPH_EDGE_PARENT
    assert payload["edges"][0]["source"] == folder.id


def test_api_graph_returns_vault_graph(vault: Vault) -> None:
    api = Api(vault)
    payload = api.graph({})

    assert set(payload) == {"nodes", "edges"}
    assert payload["nodes"]
