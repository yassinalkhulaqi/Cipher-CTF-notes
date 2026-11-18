"""Backlink, outlink, and unresolved-reference services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.graph.extract import (
    extract_wikilinks,
    link_snippet,
    normalize_reference,
)
from redscribe.v2.graph.model import EDGE_LINK, NODE_NOTE, GraphEdge
from redscribe.v2.graph.store import GraphStore, build_graph_store


@dataclass(frozen=True, slots=True)
class LinkRef:
    """One resolved relationship with display metadata."""

    node_id: int
    title: str
    path: str = ""
    status: str = "todo"
    alias: str = ""
    snippet: str = ""
    line: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_id": self.node_id,
            "title": self.title,
            "path": self.path,
            "status": self.status,
            "alias": self.alias,
            "snippet": self.snippet,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class UnresolvedRef:
    """A wikilink whose target is not a live note."""

    target: str
    alias: str = ""
    source_id: int = 0
    line: int = 0
    snippet: str = ""

    @property
    def key(self) -> str:
        """Normalized target key."""
        return normalize_reference(self.target)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "target": self.target,
            "alias": self.alias,
            "source_id": self.source_id,
            "line": self.line,
            "snippet": self.snippet,
            "key": self.key,
        }


@dataclass(frozen=True, slots=True)
class LinkDetail:
    """All link relationships for a single note."""

    node_id: int
    backlinks: tuple[LinkRef, ...] = ()
    outlinks: tuple[LinkRef, ...] = ()
    unresolved: tuple[UnresolvedRef, ...] = ()
    in_degree: int = 0
    out_degree: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_id": self.node_id,
            "backlinks": [item.as_dict() for item in self.backlinks],
            "outlinks": [item.as_dict() for item in self.outlinks],
            "unresolved": [item.as_dict() for item in self.unresolved],
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
        }


class LinkService:
    """Derive links from a graph store and optional note bodies."""

    def __init__(
        self,
        store: GraphStore,
        contents: Mapping[int, str] | None = None,
    ) -> None:
        self.store = store
        self._contents: dict[int, str] = dict(contents or {})

    @classmethod
    def from_vault(cls, vault: Vault) -> LinkService:
        """Build a link service directly from a vault."""
        store = build_graph_store(vault)
        contents = {node.id: node.content for node in vault.live_nodes() if node.is_note}
        return cls(store, contents)

    def content(self, node_id: int) -> str:
        """Return the stored body for one note."""
        return self._contents.get(node_id, "")

    def _ref(self, node_id: int, edge: GraphEdge) -> LinkRef:
        node = self.store.nodes.get(node_id)
        return LinkRef(
            node_id=node_id,
            title=node.label if node is not None else "",
            path=node.path if node is not None else "",
            status=node.status if node is not None else "todo",
            alias=str(edge.metadata.get("alias", "")),
            line=int(edge.metadata.get("line", 0)),
        )

    def backlinks(self, node_id: int) -> tuple[LinkRef, ...]:
        """Return resolved notes that link to ``node_id``."""
        target = self.store.nodes.get(node_id)
        if target is None or target.kind != NODE_NOTE:
            return ()
        key = normalize_reference(target.label)
        found: list[LinkRef] = []
        for edge in self.store.edges.all():
            if edge.kind != EDGE_LINK or not edge.resolved or edge.target != node_id:
                continue
            if edge.source == node_id:
                continue
            ref = self._ref(edge.source, edge)
            ref = LinkRef(
                node_id=ref.node_id,
                title=ref.title,
                path=ref.path,
                status=ref.status,
                alias=ref.alias,
                snippet=self._snippet(edge.source, key),
                line=ref.line,
            )
            found.append(ref)
        found.sort(key=lambda item: (item.title.casefold(), item.node_id))
        return tuple(found)

    def outlinks(self, node_id: int) -> tuple[LinkRef, ...]:
        """Return resolved notes that ``node_id`` links to."""
        source = self.store.nodes.get(node_id)
        if source is None or source.kind != NODE_NOTE:
            return ()
        found: list[LinkRef] = []
        seen: set[int] = set()
        for edge in self.store.edges.all():
            if edge.kind != EDGE_LINK or not edge.resolved or edge.source != node_id:
                continue
            if edge.target in seen or edge.target == node_id:
                continue
            seen.add(edge.target)
            ref = self._ref(edge.target, edge)
            found.append(
                LinkRef(
                    node_id=ref.node_id,
                    title=ref.title,
                    path=ref.path,
                    status=ref.status,
                    alias=ref.alias,
                    snippet=self._snippet(edge.target, normalize_reference(ref.title)),
                    line=ref.line,
                )
            )
        found.sort(key=lambda item: (item.title.casefold(), item.node_id))
        return tuple(found)

    def unresolved(self, node_id: int) -> tuple[UnresolvedRef, ...]:
        """Return unresolved wikilinks belonging to one note."""
        source = self.store.nodes.get(node_id)
        if source is None or source.kind != NODE_NOTE:
            return ()
        found: list[UnresolvedRef] = []
        seen: set[str] = set()
        for edge in self.store.edges.all():
            if edge.kind != EDGE_LINK or edge.resolved or edge.source != node_id:
                continue
            target = self.store.nodes.get(edge.target)
            if target is None:
                continue
            raw = str(target.metadata.get("target", target.label))
            if raw.casefold() in seen:
                continue
            seen.add(raw.casefold())
            found.append(
                UnresolvedRef(
                    target=raw,
                    alias=str(edge.metadata.get("alias", "")),
                    source_id=node_id,
                    line=int(edge.metadata.get("line", 0)),
                    snippet=self._snippet(node_id, normalize_reference(raw)),
                )
            )
        found.sort(key=lambda item: (item.key, item.line))
        return tuple(found)

    def _snippet(self, source_id: int, target_key: str) -> str:
        body = self.content(source_id)
        for occurrence in extract_wikilinks(body):
            if occurrence.key == target_key:
                return link_snippet(body, occurrence.start, occurrence.end)
        return ""

    def detail(self, node_id: int) -> LinkDetail:
        """Return the full link view for one note."""
        backlinks = self.backlinks(node_id)
        outlinks = self.outlinks(node_id)
        return LinkDetail(
            node_id=node_id,
            backlinks=backlinks,
            outlinks=outlinks,
            unresolved=self.unresolved(node_id),
            in_degree=len(backlinks),
            out_degree=len(outlinks),
        )

    def dangling(self) -> tuple[UnresolvedRef, ...]:
        """Return every unresolved reference across the store."""
        found: list[UnresolvedRef] = []
        for node in self.store.nodes.of_kind(NODE_NOTE):
            found.extend(self.unresolved(node.id))
        found.sort(key=lambda item: (item.key, item.source_id, item.line))
        return tuple(found)
