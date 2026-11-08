"""Vault knowledge graph: notes, folders, and the links between them."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from redscribe.domain.models import Node
from redscribe.domain.utils import collapse_whitespace, slugify, truncate
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


@dataclasses.dataclass(frozen=True, slots=True)
class Backlink:
    """A live note that links to another note via a wikilink."""

    node_id: int
    title: str
    path: str = ""
    status: str = "todo"
    target: str = ""
    updated_at: str = ""
    snippet: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class NoteLink:
    """A resolved wikilink target of a note."""

    node_id: int
    title: str
    path: str = ""
    status: str = "todo"
    alias: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class UnresolvedLink:
    """A wikilink in a note that does not resolve to a live note."""

    target: str
    alias: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class NoteLinks:
    """All wikilink relationships for one note."""

    backlinks: tuple[Backlink, ...] = ()
    outlinks: tuple[NoteLink, ...] = ()
    unresolved: tuple[UnresolvedLink, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One recent vault activity item."""

    node_id: int
    title: str
    path: str = ""
    kind: str = "note"
    activity: str = "updated"
    at: str = ""
    status: str = "todo"
    target: str = ""
    flag: str = ""


def _notes_by_slug(vault: Vault) -> dict[str, Node]:
    """Map note title slugs to live notes (first title wins, like the graph)."""
    mapping: dict[str, Node] = {}
    for node in vault.live_nodes():
        if node.is_note:
            mapping.setdefault(slugify(node.title), node)
    return mapping


def _link_snippet(content: str, target_slug: str) -> str:
    """Return a short context excerpt around the first matching wikilink."""
    for match in WIKILINK_RE.finditer(content):
        if slugify(match.group(1)) != target_slug:
            continue
        start = max(0, match.start() - 60)
        end = min(len(content), match.end() + 90)
        excerpt = collapse_whitespace(content[start:end])
        excerpt = excerpt.replace("[[", "").replace("]]", "")
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(content) else ""
        return truncate(f"{prefix}{excerpt}{suffix}", 160)
    return ""


def note_links(vault: Vault, note_id: int) -> NoteLinks:
    """Return backlinks, outlinks, and unresolved wikilinks for ``note_id``.

    Derived on demand from live wikilinks — no schema change. Self-links are
    ignored, matching :func:`build_vault_graph`.
    """
    note = vault.get_node(note_id)
    if note is None:
        raise ValueError("Node does not exist")
    if not note.is_note:
        return NoteLinks()
    by_slug = _notes_by_slug(vault)
    target_slug = slugify(note.title)
    backlinks: list[Backlink] = []
    outlinks: list[NoteLink] = []
    unresolved: list[UnresolvedLink] = []
    seen_out: set[int] = set()
    seen_unresolved: set[str] = set()
    for other in vault.live_nodes():
        if not other.is_note or other.id == note_id:
            continue
        for target, alias in wikilink_pairs(other.content):
            if slugify(target) != target_slug:
                continue
            backlinks.append(
                Backlink(
                    node_id=other.id,
                    title=other.title,
                    path=vault.path_of(other.id, include_self=False),
                    status=other.status,
                    target=other.target,
                    updated_at=other.updated_at,
                    snippet=_link_snippet(other.content, target_slug),
                )
            )
            break
    for target, alias in wikilink_pairs(note.content):
        slug = slugify(target)
        resolved = by_slug.get(slug)
        if resolved is not None and resolved.id != note_id:
            if resolved.id in seen_out:
                continue
            seen_out.add(resolved.id)
            outlinks.append(
                NoteLink(
                    node_id=resolved.id,
                    title=resolved.title,
                    path=vault.path_of(resolved.id, include_self=False),
                    status=resolved.status,
                    alias=alias or "",
                )
            )
        elif resolved is None:
            key = target.lower()
            if key in seen_unresolved:
                continue
            seen_unresolved.add(key)
            unresolved.append(UnresolvedLink(target=target, alias=alias or ""))
    backlinks.sort(key=lambda item: (item.updated_at, item.title.lower()), reverse=True)
    return NoteLinks(
        backlinks=tuple(backlinks),
        outlinks=tuple(outlinks),
        unresolved=tuple(unresolved),
    )


def backlinks_for(vault: Vault, note_id: int) -> tuple[Backlink, ...]:
    """Return the notes linking to ``note_id``, newest first."""
    return note_links(vault, note_id).backlinks


def _descendant_ids(vault: Vault, folder_id: int) -> set[int]:
    found: set[int] = set()
    stack = [folder_id]
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(child.id for child in vault.children(current))
    return found


def build_timeline(
    vault: Vault, *, folder_id: int | None = None, limit: int = 50
) -> tuple[TimelineEvent, ...]:
    """Return recent vault activity, optionally scoped to a folder subtree.

    Activity is ``created`` when a node was never edited after creation,
    otherwise ``updated``. Sorted newest first.
    """
    limit = max(1, min(limit, 200))
    scope = _descendant_ids(vault, folder_id) if folder_id is not None else None
    if folder_id is not None and vault.get_node(folder_id) is None:
        raise ValueError("Folder does not exist")
    events: list[TimelineEvent] = []
    for node in vault.live_nodes():
        if scope is not None and node.id not in scope:
            continue
        events.append(
            TimelineEvent(
                node_id=node.id,
                title=node.title,
                path=vault.path_of(node.id, include_self=False),
                kind=node.kind,
                activity="created" if node.created_at == node.updated_at else "updated",
                at=node.updated_at,
                status=node.status,
                target=node.target,
                flag=node.flag,
            )
        )
    events.sort(key=lambda item: (item.at, item.title.lower()), reverse=True)
    return tuple(events[:limit])


def note_links_payload(links: NoteLinks) -> dict[str, Any]:
    """Return the JSON payload for one note's wikilink relationships."""
    return {
        "backlinks": [dataclasses.asdict(item) for item in links.backlinks],
        "outlinks": [dataclasses.asdict(item) for item in links.outlinks],
        "unresolved": [dataclasses.asdict(item) for item in links.unresolved],
    }


def timeline_payload(events: tuple[TimelineEvent, ...]) -> list[dict[str, Any]]:
    """Return the JSON payload for the timeline view."""
    return [dataclasses.asdict(event) for event in events]
