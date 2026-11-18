from __future__ import annotations

from tests.v2_graph.conftest import seed_vault

from redscribe.storage.db import Vault
from redscribe.v2.graph.model import (
    EDGE_LINK,
    EDGE_PARENT,
    EDGE_TAG,
    NODE_NOTE,
    NODE_REFERENCE,
    NODE_TAG,
    GraphEdge,
    GraphNode,
)
from redscribe.v2.graph.store import (
    REFERENCE_ID_BASE,
    TAG_ID_BASE,
    EdgeStore,
    GraphStore,
    NodeStore,
    build_graph_store,
)


def test_node_store_indexes_kinds_and_tags() -> None:
    store = NodeStore()
    alpha = GraphNode(id=1, label="Alpha", tags=("Web", "recon"))
    beta = GraphNode(id=2, label="Beta", kind="tag", tags=("WEB",))
    store.add(alpha)
    store.add(beta)
    assert store.count() == 2
    assert len(store) == 2
    assert 1 in store
    assert 99 not in store
    assert store.get(1) is alpha
    assert store.has_node(2)
    assert [item.id for item in store.all()] == [1, 2]
    assert [item.id for item in store.of_kind(NODE_NOTE)] == [1]
    assert [item.id for item in store.with_tag("web")] == [1, 2]
    assert store.tags() == ("recon", "web")


def test_node_store_replace_and_remove_refresh_indexes() -> None:
    store = NodeStore()
    store.add(GraphNode(id=1, label="Alpha", tags=("web",)))
    store.add(GraphNode(id=1, label="Alpha", kind="folder", tags=("recon",)))
    assert store.count() == 1
    assert store.of_kind(NODE_NOTE) == ()
    assert [item.id for item in store.with_tag("web")] == []
    assert [item.id for item in store.with_tag("recon")] == [1]
    removed = store.remove(1)
    assert removed is not None
    assert store.count() == 0
    assert store.remove(1) is None


def test_edge_store_indexes_directions_and_degrees() -> None:
    store = EdgeStore()
    store.add(GraphEdge(source=1, target=2, kind=EDGE_LINK))
    store.add(GraphEdge(source=2, target=1, kind=EDGE_LINK))
    store.add(GraphEdge(source=3, target=1, kind=EDGE_TAG))
    assert store.count() == 3
    assert len(store) == 3
    assert store.get(1, 2, EDGE_LINK) is not None
    assert store.outgoing(1) == (2,)
    assert store.incoming(1) == (2, 3)
    assert store.neighbors(1) == (2, 3)
    assert [item.target for item in store.incident(1)] == [2, 1, 1]
    assert store.degrees() == {1: (2, 1), 2: (1, 1), 3: (0, 1)}


def test_edge_store_replace_remove_and_remove_node() -> None:
    store = EdgeStore()
    first = GraphEdge(source=1, target=2, kind=EDGE_LINK, weight=1)
    second = GraphEdge(source=1, target=2, kind=EDGE_LINK, weight=3)
    store.add(first)
    store.add(second)
    assert store.count() == 1
    assert store.get(1, 2, EDGE_LINK) is second
    assert store.remove((1, 2, EDGE_LINK)) is second
    assert store.remove((1, 2, EDGE_LINK)) is None
    store.add(GraphEdge(source=1, target=2, kind=EDGE_LINK))
    store.add(GraphEdge(source=2, target=3, kind=EDGE_PARENT))
    removed = store.remove_node(2)
    assert len(removed) == 2
    assert store.count() == 0
    assert store.neighbors(1) == ()


def test_graph_store_round_trips_models_and_stats() -> None:
    model = GraphStore().to_model()
    assert model.size == 0
    store = GraphStore()
    store.add_node(GraphNode(id=1, label="Alpha", tags=("web",)))
    store.add_node(GraphNode(id=2, label="Beta", kind="tag"))
    store.add_edge(GraphEdge(source=1, target=2, kind=EDGE_TAG))
    rebuilt = GraphStore.from_model(store.to_model())
    assert rebuilt.stats() == {
        "nodes": 2,
        "edges": 1,
        "notes": 1,
        "folders": 0,
        "references": 0,
        "tags": 1,
    }
    assert rebuilt.to_model().size == 2
    payload = rebuilt.as_dict()
    assert payload["stats"]["edges"] == 1
    assert payload["nodes"][0]["id"] == 1
    assert payload["edges"][0]["kind"] == EDGE_TAG


def test_graph_store_add_edge_creates_placeholders_and_remove_cleans_up() -> None:
    store = GraphStore()
    store.add_edge(GraphEdge(source=7, target=8, kind=EDGE_LINK, resolved=False))
    assert store.nodes.has_node(7)
    assert store.nodes.has_node(8)
    assert store.remove_node(7) is not None
    assert store.edges.count() == 0


def test_build_graph_store_creates_notes_folders_and_parent_edges(vault: Vault) -> None:
    folder_id, alpha_id, beta_id = seed_vault(vault)
    store = build_graph_store(vault)
    stats = store.stats()
    assert stats["nodes"] >= 7
    assert stats["notes"] == 4
    assert stats["folders"] >= 1
    assert stats["edges"] >= 5
    assert store.edges.get(folder_id, alpha_id, EDGE_PARENT) is not None
    assert store.edges.get(alpha_id, beta_id, EDGE_LINK) is not None
    assert store.nodes.get(alpha_id) is not None
    assert store.nodes.get(alpha_id).tags == ("web", "recon")


def test_build_graph_store_creates_reference_and_tag_vertices(vault: Vault) -> None:
    seed_vault(vault)
    store = build_graph_store(vault)
    references = store.nodes.of_kind(NODE_REFERENCE)
    tags = store.nodes.of_kind(NODE_TAG)
    assert references
    assert tags
    assert all(item.id <= REFERENCE_ID_BASE for item in references)
    assert all(item.id <= TAG_ID_BASE for item in tags)
    assert any(item.label == "Missing Note" for item in references)
    assert any(item.label == "web" for item in tags)
    assert any(edge.kind == EDGE_TAG for edge in store.edges.all())
    assert any(edge.resolved is False for edge in store.edges.all())


def test_build_graph_store_reuses_unresolved_reference_vertices(vault: Vault) -> None:
    vault.create_node("First", content="[[Missing]]")
    vault.create_node("Second", content="[[Missing]]")
    store = build_graph_store(vault)
    references = store.nodes.of_kind(NODE_REFERENCE)
    assert len(references) == 1
    assert sum(1 for edge in store.edges.all() if edge.target == references[0].id) == 2


def test_build_graph_store_ignores_self_links(vault: Vault) -> None:
    note = vault.create_node("Alpha", content="[[Alpha]] is itself.")
    store = build_graph_store(vault)
    assert all(edge.source != edge.target for edge in store.edges.all())
    assert store.nodes.has_node(note.id)


def test_build_graph_store_resolves_case_insensitive_links(vault: Vault) -> None:
    source = vault.create_node("Source", content="[[target note]]")
    target = vault.create_node("Target Note")
    store = build_graph_store(vault)
    assert store.edges.get(source.id, target.id, EDGE_LINK) is not None
    assert store.edges.get(source.id, target.id, EDGE_LINK).resolved is True


def test_build_graph_store_keeps_wikilink_alias_and_line(vault: Vault) -> None:
    source = vault.create_node("Source", content="One\nSee [[Target|the target]]\nThree")
    target = vault.create_node("Target")
    store = build_graph_store(vault)
    edge = store.edges.get(source.id, target.id, EDGE_LINK)
    assert edge is not None
    assert edge.alias == "the target"
    assert edge.metadata["line"] == 2


def test_build_graph_store_marks_pinned_notes_with_weight(vault: Vault) -> None:
    pinned = vault.create_node("Pinned", pinned=True)
    store = build_graph_store(vault)
    assert store.nodes.get(pinned.id).weight == 2.0
    assert store.nodes.get(pinned.id).pinned is True


def test_build_graph_store_stores_note_metadata(vault: Vault) -> None:
    note = vault.create_node("Meta", status="done", flag="HTB{x}", content="#web")
    store = build_graph_store(vault)
    node = store.nodes.get(note.id)
    assert node.status == "done"
    assert node.metadata["flag"] == "HTB{x}"
    assert store.nodes.with_tag("web")


def test_store_helpers_handle_empty_vault(vault: Vault) -> None:
    store = build_graph_store(vault)
    assert store.stats()["nodes"] == 0
    assert store.edges.count() == 0
    assert store.as_dict()["nodes"] == []
