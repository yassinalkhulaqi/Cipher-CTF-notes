"""V2 API namespace for graph intelligence and link analytics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from weakref import WeakKeyDictionary

from redscribe.ui.web.v2.contracts import (
    MAX_PAGE_SIZE,
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_int,
    optional_str,
    paginate,
    require_str,
)
from redscribe.ui.web.v2.routes import ApiV2, RouteResult
from redscribe.v2.graph.extract import normalize_reference
from redscribe.v2.graph.payload import endpoint_ids, positive_int, string_list
from redscribe.v2.graph.service import GraphFilters, GraphIntelligenceService

_SERVICES: WeakKeyDictionary[ApiV2, GraphIntelligenceService] = WeakKeyDictionary()
NamespaceHandler = Callable[[GraphIntelligenceService, dict[str, Any]], RouteResult]
GuardT = TypeVar("GuardT")

_ROUTE_SPECS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], bool, str], ...] = (
    (
        "graph.overview",
        "Return graph counts, metrics, and tag vocabulary.",
        (),
        ("refresh",),
        False,
        "graph",
    ),
    (
        "graph.nodes",
        "List graph vertices with optional filters and pagination.",
        (),
        ("kinds", "tags", "statuses", "query", "max_nodes", "cursor", "limit"),
        False,
        "graph_node",
    ),
    (
        "graph.edges",
        "List edges whose endpoints match optional filters.",
        (),
        ("kinds", "tags", "statuses", "query", "max_nodes", "cursor", "limit"),
        False,
        "graph_edge",
    ),
    (
        "graph.neighbors",
        "Return a bounded neighborhood around one vertex.",
        ("id",),
        ("depth", "kinds"),
        False,
        "graph_node",
    ),
    (
        "graph.backlinks",
        "Return resolved notes linking to one note.",
        ("id",),
        (),
        False,
        "graph_node",
    ),
    (
        "graph.outlinks",
        "Return resolved notes linked from one note.",
        ("id",),
        (),
        False,
        "graph_node",
    ),
    (
        "graph.dangling",
        "List unresolved wikilinks across the vault.",
        (),
        ("limit",),
        False,
        "graph_reference",
    ),
    (
        "graph.path",
        "Find the shortest path between two vertices.",
        ("source", "target"),
        ("from", "to", "weighted", "directed", "max_hops"),
        False,
        "graph_path",
    ),
    (
        "graph.components",
        "List connected components of the graph.",
        (),
        ("min_size", "limit"),
        False,
        "graph_component",
    ),
    (
        "graph.centrality",
        "Rank vertices by a chosen centrality measure.",
        (),
        ("measure", "limit"),
        False,
        "graph_node",
    ),
    (
        "graph.clustering",
        "Return local clustering coefficients and average.",
        (),
        ("limit",),
        False,
        "graph_node",
    ),
    (
        "graph.communities",
        "Detect link communities in the graph.",
        (),
        ("limit",),
        False,
        "graph_community",
    ),
    (
        "graph.cycles",
        "Find simple cycles in the link structure.",
        (),
        ("limit",),
        False,
        "graph_cycle",
    ),
    (
        "graph.recommend",
        "Recommend missing links and popular notes.",
        (),
        ("limit",),
        False,
        "graph_recommendation",
    ),
    (
        "graph.related",
        "Recommend notes related to one note.",
        ("id",),
        ("limit", "min_score"),
        False,
        "graph_recommendation",
    ),
    (
        "graph.tags",
        "Suggest note pairs sharing a tag.",
        ("tag",),
        ("limit",),
        False,
        "graph_recommendation",
    ),
    (
        "graph.resolve",
        "Resolve a wikilink-style label to a note id.",
        ("label",),
        (),
        False,
        "graph_node",
    ),
    (
        "graph.layout",
        "Return a layout-ready node and edge payload.",
        (),
        ("kinds", "tags", "statuses", "query", "max_nodes"),
        False,
        "graph",
    ),
    (
        "graph.insights",
        "Return the combined graph-intelligence dashboard.",
        (),
        ("limit",),
        False,
        "graph",
    ),
    (
        "graph.snapshot.create",
        "Capture a named graph snapshot.",
        (),
        ("label", "source"),
        True,
        "graph_snapshot",
    ),
    (
        "graph.snapshot.list",
        "List stored graph snapshots.",
        (),
        ("limit",),
        False,
        "graph_snapshot",
    ),
    (
        "graph.snapshot.get",
        "Return one snapshot with its records.",
        ("id",),
        (),
        False,
        "graph_snapshot",
    ),
    (
        "graph.snapshot.restore",
        "Restore a snapshot as a model payload.",
        ("id",),
        (),
        False,
        "graph_snapshot",
    ),
    (
        "graph.snapshot.diff",
        "Diff two stored graph snapshots.",
        ("left", "right"),
        (),
        False,
        "graph_snapshot",
    ),
    ("graph.snapshot.delete", "Delete one stored snapshot.", ("id",), (), True, "graph_snapshot"),
)


def _bind(
    service: GraphIntelligenceService,
    handler: NamespaceHandler,
) -> Callable[[dict[str, Any]], RouteResult]:
    def call(body: dict[str, Any]) -> RouteResult:
        return handler(service, body)

    return call


def get_service(api: ApiV2) -> GraphIntelligenceService:
    """Return the graph service attached to one API registry."""
    service = _SERVICES.get(api)
    if service is None:
        service = GraphIntelligenceService(api.vault)
        _SERVICES[api] = service
    return service


def _failure(
    message: str, *, field: str = "", code: V2ErrorCode = V2ErrorCode.INVALID_REQUEST
) -> V2Error:
    details = {"field": field} if field else None
    return V2Error(400, code, message, details=details)


def _guard(call: Callable[[], GuardT], *, field: str = "") -> GuardT:
    try:
        return call()
    except ValueError as exc:
        raise _failure(str(exc), field=field) from exc
    except TypeError as exc:
        raise _failure(str(exc), field=field, code=V2ErrorCode.INVALID_TYPE) from exc


def _json(data: Any, *, status: int = 200) -> RouteResult:
    return RouteResult(data, status=status, etag=compute_etag(data))


def _limit(body: Mapping[str, Any], *, default: int = 20) -> int:
    return _guard(
        lambda: positive_int(body.get("limit"), field="limit", default=default), field="limit"
    )


def _boolean(body: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    value = body.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _failure(f"{key} must be a boolean", field=key, code=V2ErrorCode.INVALID_TYPE)
    return value


def _score(body: Mapping[str, Any], key: str, *, default: float) -> float:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _failure(f"{key} must be a number", field=key, code=V2ErrorCode.INVALID_TYPE)
    if value < 0 or value > 1:
        raise _failure(f"{key} must be between 0 and 1", field=key)
    return float(value)


def _filters(body: Mapping[str, Any], *, include_kinds: bool = True) -> GraphFilters:
    return _guard(
        lambda: GraphFilters.from_dict(
            {
                "kinds": string_list(body.get("kinds"), field="kinds") if include_kinds else (),
                "tags": string_list(body.get("tags"), field="tags"),
                "statuses": string_list(body.get("statuses"), field="statuses"),
                "query": optional_str(body, "query", default="") or "",
                "max_nodes": body.get("max_nodes", 0),
            }
        ),
        field="filters",
    )


def graph_overview(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return structural counts and graph-quality metrics."""
    if _boolean(body, "refresh"):
        service.store(refresh=True)
    return _json(service.overview())


def graph_nodes(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """List vertices with filters and cursor pagination."""
    items = service.nodes(filters=_filters(body))
    page_items, page = paginate(items, cursor=optional_str(body, "cursor"), limit=_limit(body))
    data = {"items": page_items, "page": page.as_dict()}
    return RouteResult(data, page=page, etag=compute_etag(data))


def graph_edges(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """List filtered edges with cursor pagination."""
    kinds = string_list(body.get("kinds"), field="kinds")
    items = service.edges(
        filters=_filters(body, include_kinds=False),
        kinds=kinds or ("parent", "link", "tag", "mention"),
    )
    page_items, page = paginate(items, cursor=optional_str(body, "cursor"), limit=_limit(body))
    data = {"items": page_items, "page": page.as_dict()}
    return RouteResult(data, page=page, etag=compute_etag(data))


def graph_neighbors(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return a bounded neighborhood around one vertex."""
    node_id = optional_int(body, "id")
    if node_id is None:
        raise _failure("id is required", field="id", code=V2ErrorCode.MISSING_FIELD)
    depth = _guard(
        lambda: positive_int(body.get("depth"), field="depth", default=1, maximum=5),
        field="depth",
    )
    kinds = string_list(body.get("kinds"), field="kinds")
    data = _guard(
        lambda: service.neighbors(
            node_id, depth=depth, kinds=kinds or ("parent", "link", "tag", "mention")
        ),
        field="id",
    )
    return _json(data)


def graph_backlinks(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return backlinks for one note."""
    note_id = optional_int(body, "id")
    if note_id is None:
        raise _failure("id is required", field="id", code=V2ErrorCode.MISSING_FIELD)
    links = service.links().backlinks(note_id)
    return _json({"node_id": note_id, "backlinks": [item.as_dict() for item in links]})


def graph_outlinks(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return outlinks and unresolved references for one note."""
    note_id = optional_int(body, "id")
    if note_id is None:
        raise _failure("id is required", field="id", code=V2ErrorCode.MISSING_FIELD)
    detail = service.links().detail(note_id)
    return _json(detail.as_dict())


def graph_dangling(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """List unresolved wikilinks in the vault."""
    limit = _guard(
        lambda: positive_int(body.get("limit"), field="limit", default=50, maximum=MAX_PAGE_SIZE),
        field="limit",
    )
    items = service.links().dangling()[:limit]
    return _json({"count": len(items), "items": [item.as_dict() for item in items]})


def graph_path(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Find a shortest path between two graph vertices."""
    source, target = _guard(
        lambda: endpoint_ids(body, resolve=service.resolve_label),
        field="source",
    )
    max_hops_value = optional_int(body, "max_hops")
    max_hops = None
    if max_hops_value is not None:
        max_hops = _guard(
            lambda: positive_int(
                max_hops_value, field="max_hops", default=1, maximum=MAX_PAGE_SIZE
            ),
            field="max_hops",
        )
    result = _guard(
        lambda: service.path(
            source,
            target,
            weighted=_boolean(body, "weighted"),
            directed=_boolean(body, "directed"),
            max_hops=max_hops,
        ),
        field="source",
    )
    if result is None:
        raise V2Error(404, V2ErrorCode.NOT_FOUND, "No path connects those vertices")
    return _json(result)


def graph_components(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """List connected components, largest first."""
    min_size = _guard(
        lambda: positive_int(
            body.get("min_size"), field="min_size", default=1, maximum=MAX_PAGE_SIZE
        ),
        field="min_size",
    )
    items = service.components(min_size=min_size)[: _limit(body, default=50)]
    return _json({"count": len(items), "items": items})


def graph_centrality(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Rank vertices by a centrality measure."""
    measure = (optional_str(body, "measure", default="degree") or "degree").casefold()
    items = _guard(lambda: service.centrality(measure, limit=_limit(body)), field="measure")
    return _json({"measure": measure, "items": items})


def graph_clustering(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return clustering coefficients."""
    payload = service.clustering()
    payload["scores"] = payload["scores"][: _limit(body, default=50)]
    return _json(payload)


def graph_communities(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return detected communities."""
    items = service.communities()[: _limit(body, default=50)]
    return _json({"count": len(items), "items": items})


def graph_cycles(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return simple cycles found in the graph."""
    items = service.cycles(limit=_limit(body, default=25))
    return _json({"count": len(items), "items": items})


def graph_recommend(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return recommendation signals for the graph view."""
    return _json(service.recommendations().dashboard(limit=_limit(body)))


def graph_related(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Recommend notes related to one note."""
    node_id = optional_int(body, "id")
    if node_id is None:
        raise _failure("id is required", field="id", code=V2ErrorCode.MISSING_FIELD)
    min_score = _score(body, "min_score", default=0.1)
    items = _guard(
        lambda: service.recommendations().related(
            node_id,
            limit=_limit(body),
            min_score=min_score,
        ),
        field="id",
    )
    return _json({"node_id": node_id, "items": [item.as_dict() for item in items]})


def graph_tags(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Suggest note pairs that share a tag."""
    tag = require_str(body, "tag", max_length=120).strip()
    if not tag:
        raise _failure("tag cannot be empty", field="tag")
    items = service.recommendations().by_tag(tag, limit=_limit(body))
    return _json({"tag": tag, "items": [item.as_dict() for item in items]})


def graph_resolve(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Resolve a wikilink label to a note id."""
    label = require_str(body, "label", max_length=200).strip()
    node_id = service.resolve_label(label)
    if node_id is None:
        raise V2Error(
            404, V2ErrorCode.NOT_FOUND, "Label does not resolve", details={"label": label}
        )
    return _json({"label": label, "id": node_id, "key": normalize_reference(label)})


def graph_layout(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return a payload shaped for frontend layout algorithms."""
    return _json(service.layout(filters=_filters(body)))


def graph_insights(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return the combined intelligence dashboard."""
    return _json(service.insights(limit=_limit(body)))


def graph_snapshot_create(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Capture and return a graph snapshot."""
    label = optional_str(body, "label", default="", max_length=120) or ""
    source = optional_str(body, "source", default="vault", max_length=80) or "vault"
    snapshot = service.capture(label=label, source=source)
    return _json(snapshot.as_dict(include_records=True), status=201)


def graph_snapshot_list(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """List stored snapshots."""
    return _json(service.snapshots(limit=_limit(body, default=20)))


def graph_snapshot_get(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return one snapshot with its node and edge records."""
    snapshot_id = require_str(body, "id", max_length=160)
    snapshot = _guard(lambda: service.snapshot(snapshot_id), field="id")
    return _json(snapshot.as_dict(include_records=True))


def graph_snapshot_restore(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Return the model held in one snapshot."""
    snapshot_id = require_str(body, "id", max_length=160)
    snapshot = _guard(lambda: service.snapshot(snapshot_id), field="id")
    return _json(snapshot.to_model().as_dict())


def graph_snapshot_diff(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Diff two snapshots by node and edge identity."""
    left = require_str(body, "left", max_length=160)
    right = require_str(body, "right", max_length=160)
    return _json(_guard(lambda: service.diff(left, right), field="left"))


def graph_snapshot_delete(service: GraphIntelligenceService, body: dict[str, Any]) -> RouteResult:
    """Remove one snapshot from history."""
    snapshot_id = require_str(body, "id", max_length=160)
    deleted = _guard(lambda: service.delete_snapshot(snapshot_id), field="id")
    return _json({"deleted": deleted})


_HANDLERS: dict[str, NamespaceHandler] = {
    "graph.overview": graph_overview,
    "graph.nodes": graph_nodes,
    "graph.edges": graph_edges,
    "graph.neighbors": graph_neighbors,
    "graph.backlinks": graph_backlinks,
    "graph.outlinks": graph_outlinks,
    "graph.dangling": graph_dangling,
    "graph.path": graph_path,
    "graph.components": graph_components,
    "graph.centrality": graph_centrality,
    "graph.clustering": graph_clustering,
    "graph.communities": graph_communities,
    "graph.cycles": graph_cycles,
    "graph.recommend": graph_recommend,
    "graph.related": graph_related,
    "graph.tags": graph_tags,
    "graph.resolve": graph_resolve,
    "graph.layout": graph_layout,
    "graph.insights": graph_insights,
    "graph.snapshot.create": graph_snapshot_create,
    "graph.snapshot.list": graph_snapshot_list,
    "graph.snapshot.get": graph_snapshot_get,
    "graph.snapshot.restore": graph_snapshot_restore,
    "graph.snapshot.diff": graph_snapshot_diff,
    "graph.snapshot.delete": graph_snapshot_delete,
}


def register(api: ApiV2) -> None:
    """Register every graph route on an API v2 registry."""
    service = get_service(api)
    existing = api.routes
    for name, description, required, optional, mutating, entity_type in _ROUTE_SPECS:
        if name in existing:
            continue
        handler = _HANDLERS[name]
        api._register(
            name,
            _bind(service, handler),
            description,
            required=required,
            optional=optional,
            mutating=mutating,
            entity_type=entity_type,
        )
