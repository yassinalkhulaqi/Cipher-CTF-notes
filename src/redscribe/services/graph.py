"""Vault knowledge graph: notes, folders, and the links between them."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from redscribe.domain.models import Node
from redscribe.domain.utils import slugify
from redscribe.storage.db import Vault

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", re.IGNORECASE)

GRAPH_NODE_KIND_NOTE = "note"
GRAPH_NODE_KIND_FOLDER = "folder"
GRAPH_NODE_KIND_REFERENCE = "reference"

GRAPH_EDGE_PARENT = "parent"
GRAPH_EDGE_LINK = "link"


@dataclasses.dataclass(frozen=True, slots=True)
class GraphNode:
    """One vertex in the vault knowledge graph."""

    id: int
    title: str
    kind: str
    path: str = ""
    status: str = "todo"
    flag: str = ""
    tags: tuple[str, ...] = ()
    target: str = ""
    pinned: bool = False
    resolved: bool = True


@dataclasses.dataclass(frozen=True, slots=True)
class GraphEdge:
    """One relationship between two graph vertices."""

    source: int
    target: int
    kind: str
    resolved: bool = True


@dataclasses.dataclass(frozen=True, slots=True)
class VaultGraph:
    """The full vault knowledge graph: vertices plus relationships."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def wikilink_pairs(content: str) -> list[tuple[str, str | None]]:
    """Return ``(target, alias)`` pairs for every wikilink in ``content``."""
    pairs: list[tuple[str, str | None]] = []
    for match in WIKILINK_RE.finditer(content):
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) is not None else None
        if target:
            pairs.append((target, alias))
    return pairs


def build_vault_graph(vault: Vault) -> VaultGraph:
    """Build the live vault knowledge graph.

    Vertices are live folders and notes. Edges are parent/child relationships
    for the folder tree plus ``link`` edges for every resolved wikilink. Unresolved
    wikilinks become ``reference`` vertices with ``resolved=False`` so the graph
    can surface dangling references.
    """
    live = vault.live_nodes()
    notes_by_slug: dict[str, int] = {}
    for node in live:
        if node.is_note:
            notes_by_slug.setdefault(slugify(node.title), node.id)

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_edges: set[tuple[int, int, str]] = set()
    next_reference_id = 0

    def add_edge(source: int, target: int, kind: str, *, resolved: bool = True) -> None:
        key = (source, target, kind)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(GraphEdge(source=source, target=target, kind=kind, resolved=resolved))

    def vertex(node: Node, *, resolved: bool = True) -> GraphNode:
        return GraphNode(
            id=node.id,
            title=node.title,
            kind=node.kind,
            path=vault.path_of(node.id, include_self=False),
            status=node.status,
            flag=node.flag,
            tags=tuple(node.tag_list),
            target=node.target,
            pinned=node.pinned,
            resolved=resolved,
        )

    for node in live:
        nodes.append(vertex(node))
        if node.parent_id is not None:
            add_edge(node.parent_id, node.id, GRAPH_EDGE_PARENT)
        if not node.is_note:
            continue
        for target, alias in wikilink_pairs(node.content):
            target_id = notes_by_slug.get(slugify(target))
            if target_id is None or target_id == node.id:
                continue
            add_edge(node.id, target_id, GRAPH_EDGE_LINK)

    # Second pass: unresolved wikilinks become dangling reference vertices.
    # Resolved links were handled above and self-references are ignored.
    unresolved_seen: set[tuple[int, str]] = set()
    for node in live:
        if not node.is_note:
            continue
        for target, alias in wikilink_pairs(node.content):
            if notes_by_slug.get(slugify(target)) is not None:
                continue
            key = (node.id, target.lower())
            if key in unresolved_seen:
                continue
            unresolved_seen.add(key)
            next_reference_id -= 1
            nodes.append(
                GraphNode(
                    id=next_reference_id,
                    title=alias or target,
                    kind=GRAPH_NODE_KIND_REFERENCE,
                    path=vault.path_of(node.id, include_self=False),
                    resolved=False,
                )
            )
            add_edge(node.id, next_reference_id, GRAPH_EDGE_LINK, resolved=False)

    return VaultGraph(nodes=tuple(nodes), edges=tuple(edges))


def graph_payload(graph: VaultGraph) -> dict[str, Any]:
    """Return the JSON-serializable graph payload used by the web frontend."""
    return {
        "nodes": [dataclasses.asdict(node) for node in graph.nodes],
        "edges": [dataclasses.asdict(edge) for edge in graph.edges],
    }
