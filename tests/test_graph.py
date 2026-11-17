from __future__ import annotations

import pytest

from redscribe.services.graph import (
    GRAPH_EDGE_LINK,
    GRAPH_EDGE_PARENT,
    build_vault_graph,
    graph_payload,
)
from redscribe.services.graph_analysis import (
    InfluenceConfig,
    build_graph_insights,
    find_bridges,
    find_communities,
    find_orphans,
    graph_insights_payload,
    link_adjacency,
    link_degrees,
    path_payload,
    rank_influence,
    shortest_path,
    suggest_links,
    vault_graph_insights,
)
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api


def _parent_pairs(graph) -> set[tuple[int, int]]:
    return {(edge.source, edge.target) for edge in graph.edges if edge.kind == GRAPH_EDGE_PARENT}


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
    vault.create_node("Writeup")
    api = Api(vault)
    payload = api.graph({})

    assert set(payload) == {"nodes", "edges"}
    assert payload["nodes"]


def test_link_adjacency_and_degrees_cover_both_directions(vault: Vault) -> None:
    first = vault.create_node("First", content="See [[Second]]")
    second = vault.create_node("Second", content="See [[Third]]")
    third = vault.create_node("Third")
    graph = build_vault_graph(vault)

    adjacency = link_adjacency(graph)
    degrees = link_degrees(graph)

    assert adjacency[first.id] == {second.id}
    assert adjacency[second.id] == {first.id, third.id}
    assert adjacency[third.id] == {second.id}
    assert degrees[second.id] == (1, 1)
    assert degrees[first.id] == (0, 1)


def test_rank_influence_prefers_well_linked_notes(vault: Vault) -> None:
    hub = vault.create_node("Hub", content="", pinned=True)
    vault.create_node("Left", content="[[Hub]]")
    vault.create_node("Right", content="[[Hub]]")
    vault.create_node("Island")

    ranked = rank_influence(build_vault_graph(vault))

    assert ranked[0].node_id == hub.id
    assert ranked[0].in_degree == 2
    assert sum(item.score for item in ranked) == pytest.approx(1.0)
    assert ranked == rank_influence(build_vault_graph(vault))


def test_rank_influence_pinned_boost_changes_scores(vault: Vault) -> None:
    pinned = vault.create_node("Pinned", content="[[Target]]", pinned=True)
    vault.create_node("Target")
    graph = build_vault_graph(vault)

    boosted = rank_influence(graph)
    neutral = rank_influence(graph, config=InfluenceConfig(pinned_boost=1.0))

    boosted_score = next(item.score for item in boosted if item.node_id == pinned.id)
    neutral_score = next(item.score for item in neutral if item.node_id == pinned.id)
    assert boosted_score > neutral_score


def test_rank_influence_validates_configuration(vault: Vault) -> None:
    graph = build_vault_graph(vault)
    with pytest.raises(ValueError, match="damping"):
        rank_influence(graph, config=InfluenceConfig(damping=1.0))
    with pytest.raises(ValueError, match="iterations"):
        rank_influence(graph, config=InfluenceConfig(iterations=0))
    with pytest.raises(ValueError, match="weights"):
        rank_influence(graph, config=InfluenceConfig(shared_tag_weight=-1.0))
    with pytest.raises(ValueError, match="pinned_boost"):
        rank_influence(graph, config=InfluenceConfig(pinned_boost=0.0))


def test_rank_influence_on_empty_graph_is_empty(vault: Vault) -> None:
    assert rank_influence(build_vault_graph(vault)) == ()


def test_shortest_path_follows_links_in_both_directions(vault: Vault) -> None:
    first = vault.create_node("Alpha", content="[[Beta]]")
    second = vault.create_node("Beta", content="[[Gamma]]")
    third = vault.create_node("Gamma")
    graph = build_vault_graph(vault)

    direct = shortest_path(graph, first.id, second.id)
    indirect = shortest_path(graph, first.id, third.id)

    assert direct is not None
    assert direct.hops == 1
    assert indirect is not None
    assert indirect.node_ids == (first.id, second.id, third.id)
    assert indirect.titles == ("Alpha", "Beta", "Gamma")
    assert path_payload(indirect)["hops"] == 2


def test_shortest_path_handles_identity_and_missing_nodes(vault: Vault) -> None:
    note = vault.create_node("Alpha")
    graph = build_vault_graph(vault)

    identity = shortest_path(graph, note.id, note.id)
    assert identity is not None
    assert identity.hops == 0
    assert identity.node_ids == (note.id,)
    assert path_payload(None) is None
    with pytest.raises(ValueError, match="does not exist"):
        shortest_path(graph, note.id, 9999)


def test_shortest_path_returns_none_when_disconnected(vault: Vault) -> None:
    first = vault.create_node("Alpha")
    second = vault.create_node("Beta")
    graph = build_vault_graph(vault)

    assert shortest_path(graph, first.id, second.id) is None
    assert shortest_path(graph, first.id, second.id, include_parents=True) is None


def test_shortest_path_can_traverse_folder_hierarchy(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    first = vault.create_node("Alpha", folder.id)
    second = vault.create_node("Beta", folder.id)
    graph = build_vault_graph(vault)

    assert shortest_path(graph, first.id, second.id) is None
    path = shortest_path(graph, first.id, second.id, include_parents=True)
    assert path is not None
    assert path.node_ids == (first.id, folder.id, second.id)
    assert path.hops == 2


def test_find_orphans_only_returns_unlinked_notes(vault: Vault) -> None:
    isolated = vault.create_node("Isolated")
    linked = vault.create_node("Linked", content="[[Target]]")
    vault.create_node("Target")
    graph = build_vault_graph(vault)

    orphans = find_orphans(graph)

    assert [item.node_id for item in orphans] == [isolated.id]
    assert orphans[0].title == "Isolated"
    assert linked.id not in {item.node_id for item in orphans}


def test_find_bridges_detects_chain_links_but_not_cycles(vault: Vault) -> None:
    first = vault.create_node("A", content="[[B]]")
    second = vault.create_node("B", content="[[C]]")
    third = vault.create_node("C", content="[[A]]")
    chain = build_vault_graph(vault)
    assert find_bridges(chain) == ()

    vault.update_node(third.id, content="")
    acyclic = build_vault_graph(vault)
    bridges = find_bridges(acyclic)

    pairs = {(item.source_id, item.target_id) for item in bridges}
    assert pairs == {(first.id, second.id), (second.id, third.id)}
    assert all(item.source_title and item.target_title for item in bridges)


def test_find_communities_groups_connected_notes(vault: Vault) -> None:
    left = vault.create_node("Left", content="[[Left2]]")
    left2 = vault.create_node("Left2", content="[[Left]]")
    right = vault.create_node("Right", content="[[Right2]]")
    right2 = vault.create_node("Right2")
    vault.create_node("Isolated")
    graph = build_vault_graph(vault)

    communities = find_communities(graph)

    assert len(communities) == 2
    assert all(item.size == 2 for item in communities)
    assert {frozenset(item.node_ids) for item in communities} == {
        frozenset((left.id, left2.id)),
        frozenset((right.id, right2.id)),
    }
    assert {item.key for item in communities} == {1, 2}
    assert len(find_communities(graph, min_size=1)) == 3
    with pytest.raises(ValueError, match="min_size"):
        find_communities(graph, min_size=0)


def test_suggest_links_matches_unresolved_wikilink_target(vault: Vault) -> None:
    vault.create_node("Start", content="See [[Corporat]] for details")
    target = vault.create_node("Corporate")

    suggestions = suggest_links(build_vault_graph(vault))

    assert any(
        item.target_id == target.id and "unresolved_link" in item.reasons for item in suggestions
    )


def test_suggest_links_uses_shared_tags_without_duplicating_links(vault: Vault) -> None:
    left = vault.create_node("Recon", tags="web, enum")
    right = vault.create_node("Enumeration", tags="WEB, enum")
    vault.create_node("Unrelated")
    graph = build_vault_graph(vault)

    suggestions = suggest_links(graph)
    assert any(
        {item.source_id, item.target_id} == {left.id, right.id} and "shared_tag" in item.reasons
        for item in suggestions
    )

    vault.update_node(left.id, content="[[Enumeration]]")
    linked = suggest_links(build_vault_graph(vault))
    assert not any({item.source_id, item.target_id} == {left.id, right.id} for item in linked)


def test_suggest_links_validates_arguments(vault: Vault) -> None:
    graph = build_vault_graph(vault)
    with pytest.raises(ValueError, match="limit"):
        suggest_links(graph, limit=0)
    with pytest.raises(ValueError, match="min_score"):
        suggest_links(graph, min_score=200)


def test_graph_insights_payload_and_vault_wrapper(vault: Vault) -> None:
    vault.create_node("Start", content="[[Hub]]")
    vault.create_node("Hub", content="[[Leaf]]", pinned=True)
    vault.create_node("Leaf")
    vault.create_node("Isolated")

    insights = vault_graph_insights(vault)
    payload = graph_insights_payload(insights)

    assert payload["summary"] == {
        "notes": 4,
        "orphans": 1,
        "bridges": 2,
        "communities": 1,
        "suggestions": 0,
    }
    assert {entry["title"] for entry in payload["influence"]} == {
        "Start",
        "Hub",
        "Leaf",
        "Isolated",
    }
    assert sum(entry["score"] for entry in payload["influence"]) == pytest.approx(1.0)
    assert payload["orphans"][0]["title"] == "Isolated"
    assert len(payload["bridges"]) == 2
    assert len(payload["communities"][0]["node_ids"]) == 3
    assert build_graph_insights(build_vault_graph(vault)).influence == insights.influence


def test_graph_insights_can_skip_suggestions(vault: Vault) -> None:
    vault.create_node("Alpha", tags="shared")
    vault.create_node("Beta", tags="shared")
    graph = build_vault_graph(vault)

    assert suggest_links(graph)
    assert build_graph_insights(graph, max_suggestions=0).suggestions == ()
