"""Cross-entity pivot suggestions built on the universal link graph."""

from __future__ import annotations

from collections.abc import Sequence

from redscribe.v3.entities.ids import short_form, try_parse
from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityLink,
    LinkKind,
)
from redscribe.v3.search_intel.types import PivotRole, PivotSuggestion

_ROLE_BY_LINK: dict[LinkKind, PivotRole] = {
    LinkKind.CONTAINS: PivotRole.CONTAINS,
    LinkKind.RELATES: PivotRole.RELATES,
    LinkKind.EVIDENCES: PivotRole.EVIDENCES,
    LinkKind.DERIVES: PivotRole.DERIVES,
    LinkKind.REFERENCES: PivotRole.REFERENCES,
    LinkKind.DUPLICATES: PivotRole.RELATES,
    LinkKind.SUPERSEDES: PivotRole.RELATES,
}

_ROLE_PRIORITY: dict[str, float] = {
    PivotRole.REPORT.value: 5.0,
    PivotRole.EVIDENCES.value: 4.0,
    PivotRole.OWNS.value: 3.5,
    PivotRole.DERIVES.value: 3.0,
    PivotRole.CONTAINS.value: 2.5,
    PivotRole.REFERENCES.value: 2.0,
    PivotRole.RELATES.value: 1.0,
    PivotRole.SIBLING.value: 0.5,
}

_KIND_PRIORITY: dict[str, float] = {
    EntityKind.FINDING.value: 2.0,
    EntityKind.EVIDENCE.value: 2.0,
    EntityKind.REPORT.value: 1.8,
    EntityKind.SECTION.value: 1.2,
    EntityKind.TARGET.value: 1.0,
    EntityKind.NOTE.value: 0.8,
}

_DESTINATION_KINDS: frozenset[str] = frozenset(
    {
        EntityKind.FINDING.value,
        EntityKind.EVIDENCE.value,
        EntityKind.REPORT.value,
        EntityKind.SECTION.value,
    }
)


def pivot_query(kind: str, label: str) -> str:
    """Build a query v2 expression that re-finds a pivot target."""
    clean = " ".join(label.split()).replace('"', "")
    return f'kind:{kind} "{clean}"' if clean else f"kind:{kind}"


def _label_for(service: EntityService, entity_id: EntityId) -> str:
    record = service.find(str(entity_id))
    return record.title if record is not None else short_form(entity_id)


def _make_suggestion(
    service: EntityService,
    origin: EntityId,
    neighbor: EntityId,
    link: EntityLink | None,
    *,
    depth: int,
) -> PivotSuggestion | None:
    if neighbor == origin:
        return None
    record = service.find(str(neighbor))
    if record is None:
        return None
    kind = neighbor.kind.value
    role = _ROLE_BY_LINK.get(link.kind, PivotRole.RELATES) if link else PivotRole.SIBLING
    if kind == EntityKind.REPORT.value and role is not PivotRole.REPORT:
        role = PivotRole.REPORT
    if link is not None and link.kind is LinkKind.CONTAINS and link.source == neighbor:
        role = PivotRole.OWNS
    weight = link.weight if link is not None else 0.4
    score = (
        _ROLE_PRIORITY.get(role.value, 1.0)
        + _KIND_PRIORITY.get(kind, 0.2)
        + weight
        - 1.5 * (depth - 1)
    )
    relation = link.kind.value if link is not None else "graph-neighbor"
    reason = f"{relation} link from {short_form(origin)}" if link else "shares a neighbor"
    return PivotSuggestion(
        ref=str(neighbor),
        kind=kind,
        label=record.title,
        role=role.value,
        reason=reason,
        score=score,
        link_kind=link.kind.value if link is not None else "",
        query=pivot_query(kind, record.title),
        depth=depth,
    )


def suggest_pivots(
    ref: str,
    service: EntityService,
    *,
    limit: int = 8,
    depth: int = 1,
    kinds: Sequence[str] | None = None,
) -> tuple[PivotSuggestion, ...]:
    """Suggest entities to pivot into from a result.

    Depth one follows direct typed links. Depth two additionally follows links
    from direct neighbors, with a score penalty, so a finding can reach the
    report that cites its evidence without losing the originating context.
    """
    origin = try_parse(ref)
    if origin is None or service.find(str(origin)) is None:
        return ()
    levels = max(1, min(2, depth))
    graph = service.graph()
    best: dict[str, PivotSuggestion] = {}
    frontier: list[tuple[EntityId, int]] = [(origin, 1)]
    visited: set[str] = {str(origin)}
    while frontier:
        current, current_depth = frontier.pop(0)
        direct_links = (*graph.for_source(current), *graph.for_target(current))
        for link in direct_links:
            neighbor = link.target if link.source == current else link.source
            key = str(neighbor)
            if key in visited:
                continue
            visited.add(key)
            suggestion = _make_suggestion(service, origin, neighbor, link, depth=current_depth)
            if suggestion is None:
                continue
            if kinds and suggestion.kind not in {kind.casefold() for kind in kinds}:
                continue
            existing = best.get(key)
            if existing is None or suggestion.score > existing.score:
                best[key] = suggestion
            if current_depth < levels:
                frontier.append((neighbor, current_depth + 1))
    ordered = sorted(best.values(), key=lambda item: (-item.score, item.ref))
    return tuple(ordered[: max(0, limit)])


def pivot_chain(
    ref: str,
    service: EntityService,
    target_kind: str,
) -> tuple[str, ...]:
    """Return a link path from a result to the nearest entity of a kind."""
    origin = try_parse(ref)
    if origin is None:
        return ()
    wanted = target_kind.strip().casefold()
    graph = service.graph()
    from collections import deque

    queue: deque[str] = deque([str(origin)])
    previous: dict[str, str | None] = {str(origin): None}
    found = ""
    while queue:
        current = queue.popleft()
        parsed = try_parse(current)
        if parsed is not None and parsed.kind.value == wanted and current != str(origin):
            found = current
            break
        for neighbor in sorted(graph.neighbors(parsed)) if parsed else ():
            if neighbor in previous:
                continue
            previous[neighbor] = current
            queue.append(neighbor)
    if not found:
        return ()
    chain: list[str] = []
    cursor: str | None = found
    while cursor:
        chain.append(cursor)
        cursor = previous[cursor]
    return tuple(reversed(chain))


def pivot_context(
    ref: str,
    service: EntityService,
    *,
    limit: int = 8,
) -> dict[str, object]:
    """Return a UI-friendly pivot payload retaining the originating reference."""
    origin = try_parse(ref)
    record = service.find(ref) if origin is not None else None
    suggestions = suggest_pivots(ref, service, limit=limit)
    return {
        "origin": ref,
        "origin_kind": origin.kind.value if origin else "",
        "origin_title": record.title if record else "",
        "pivots": [item.as_dict() for item in suggestions],
        "destinations": sorted(
            {item.kind for item in suggestions if item.kind in _DESTINATION_KINDS}
        ),
    }
