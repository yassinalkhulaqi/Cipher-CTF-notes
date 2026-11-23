"""Typed link graph with traversal and cycle detection."""

from __future__ import annotations

from collections import defaultdict, deque

from redscribe.v3.entities.types import EntityId, EntityLink, LinkKind


class DuplicateLinkError(ValueError):
    """Raised when the same typed link is inserted twice."""


class LinkGraph:
    """An in-memory directed multigraph of entity links.

    Links are keyed by ``(source, target, kind)`` so adding the same relationship
    twice is a caller error rather than silent duplication. The graph is the
    shared substrate for the B04 graph workbench and the B05 pivot navigation.
    """

    def __init__(self, links: tuple[EntityLink, ...] = ()) -> None:
        self._links: dict[tuple[str, str, str], EntityLink] = {}
        self._outgoing: dict[str, set[str]] = defaultdict(set)
        self._incoming: dict[str, set[str]] = defaultdict(set)
        for link in links:
            self.add(link)

    def __len__(self) -> int:
        """Return the number of links."""
        return len(self._links)

    def __contains__(self, link: EntityLink) -> bool:
        """Return whether a link is present."""
        return link.key in self._links

    def add(self, link: EntityLink) -> None:
        """Add a link, rejecting exact duplicates."""
        if link.key in self._links:
            raise DuplicateLinkError(f"Duplicate link: {link.key}")
        source = str(link.source)
        target = str(link.target)
        self._links[link.key] = link
        self._outgoing[source].add(target)
        self._incoming[target].add(source)

    def remove(self, link: EntityLink) -> bool:
        """Remove a link if present, returning whether anything changed."""
        removed = self._links.pop(link.key, None)
        if removed is None:
            return False
        self._outgoing[str(link.source)].discard(str(link.target))
        self._incoming[str(link.target)].discard(str(link.source))
        return True

    def links(self) -> tuple[EntityLink, ...]:
        """Return all links in insertion-independent sorted order."""
        return tuple(self._links[key] for key in sorted(self._links))

    def for_source(self, entity_id: EntityId) -> tuple[EntityLink, ...]:
        """Return links whose source is the given entity."""
        return tuple(link for link in self.links() if link.source == entity_id)

    def for_target(self, entity_id: EntityId) -> tuple[EntityLink, ...]:
        """Return links whose target is the given entity."""
        return tuple(link for link in self.links() if link.target == entity_id)

    def between(self, source: EntityId, target: EntityId) -> tuple[EntityLink, ...]:
        """Return links connecting two entities in either direction."""
        return tuple(
            link for link in self.links() if {link.source, link.target} == {source, target}
        )

    def neighbors(self, entity_id: EntityId, *, undirected: bool = True) -> frozenset[str]:
        """Return adjacent entity identifiers."""
        key = str(entity_id)
        result = set(self._outgoing.get(key, ()))
        if undirected:
            result.update(self._incoming.get(key, ()))
        else:
            result = set(result)
        return frozenset(result)

    def degree(self, entity_id: EntityId) -> int:
        """Return the number of incident links."""
        return len(self.for_source(entity_id)) + len(self.for_target(entity_id))

    def path(self, source: EntityId, target: EntityId) -> tuple[str, ...] | None:
        """Return a shortest undirected path, or ``None`` when disconnected."""
        start = str(source)
        goal = str(target)
        if start == goal:
            return (start,)
        queue: deque[str] = deque([start])
        previous: dict[str, str] = {start: ""}
        while queue:
            current = queue.popleft()
            for neighbor in sorted(self.neighbors(EntityId.parse(current))):
                if neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == goal:
                    result: list[str] = []
                    cursor = neighbor
                    while cursor:
                        result.append(cursor)
                        cursor = previous[cursor]
                    return tuple(reversed(result))
                queue.append(neighbor)
        return None

    def has_cycle(self) -> bool:
        """Return whether the directed graph contains a cycle."""
        state: dict[str, int] = defaultdict(int)
        for link in self.links():
            if state[str(link.source)] == 2:
                continue
            if self._visit(str(link.source), state):
                return True
        return False

    def _visit(self, node: str, state: dict[str, int]) -> bool:
        """Depth-first cycle probe for one node."""
        if state[node] == 1:
            return True
        if state[node] == 2:
            return False
        state[node] = 1
        for neighbor in sorted(self._outgoing.get(node, ())):
            if self._visit(neighbor, state):
                return True
        state[node] = 2
        return False

    def of_kind(self, kind: LinkKind) -> tuple[EntityLink, ...]:
        """Return all links of a given kind."""
        return tuple(link for link in self.links() if link.kind is kind)

    def as_dict(self) -> dict[str, object]:
        """Return a serializable snapshot."""
        return {
            "count": len(self._links),
            "links": [link.as_dict() for link in self.links()],
        }
