"""Read-only v4 HTTP handlers for the graph workbench.

Handlers return standard v4 envelopes, enforce capability checks, paginate
collections, and publish ``GRAPH_FILTERED`` domain events. The module never
executes code from request parameters: every value is parsed and validated into
a typed value before it reaches the domain layer.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EntityKind,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.events import DomainEvent, EventBus, EventKind, utc_now
from redscribe.v4.pagination import paginate, weak_etag

from .service import (
    DEFAULT_HEIGHT,
    DEFAULT_ITERATIONS,
    DEFAULT_SEED,
    DEFAULT_WIDTH,
    FilterEngine,
    GraphAnalyzer,
    GraphBuilder,
    compute_layout,
    relation_legend,
)
from .storage import GraphStore, GraphStoreError
from .types import GraphData, GraphFilter, LayoutKind

__all__ = [
    "GRAPH_ROUTES",
    "GraphApi",
    "GraphRequest",
    "register",
]


class RouteRegistrar(Protocol):
    """The slice of the v4 route registry needed by this feature."""

    def register(
        self, prefix: str, name: str, handler: Callable[..., object] | None = None
    ) -> object: ...


GRAPH_ROUTES: tuple[tuple[str, str], ...] = (
    ("graph", "graph-workbench-overview"),
    ("graph/nodes", "graph-workbench-nodes"),
    ("graph/edges", "graph-workbench-edges"),
    ("graph/metrics", "graph-workbench-metrics"),
    ("graph/layout", "graph-workbench-layout"),
    ("graph/path", "graph-workbench-path"),
    ("graph/filters", "graph-workbench-filters"),
    ("graph/snapshots", "graph-workbench-snapshots"),
    ("graph/snapshot", "graph-workbench-snapshot"),
    ("graph/export", "graph-workbench-export"),
)

MAX_PAGE_SIZE = 200
MAX_FILTER_VALUES = 32


class GraphRequest:
    """Validated view over a mapping of string query parameters."""

    def __init__(
        self,
        params: Mapping[str, str] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.params: Mapping[str, str] = dict(params or {})
        value = self.get("request_id").strip()
        self._request_id = value or (id_factory() if id_factory is not None else "")

    def get(self, key: str, default: str = "") -> str:
        return self.params.get(key, default)

    def request_id(self, fallback: Callable[[], str]) -> str:
        return self._request_id or fallback()

    def page(self) -> int:
        return _parse_int(self.params, "page", 1, 1, 10000)

    def page_size(self) -> int:
        return _parse_int(self.params, "page_size", 50, 1, MAX_PAGE_SIZE)

    def min_weight(self) -> float:
        return _parse_float(self.params, "min_weight", 0.0, 0.0, 1.0)

    def label_contains(self) -> str:
        return self.get("label_contains").strip()

    def kinds(self) -> tuple[EntityKind, ...]:
        result: list[EntityKind] = []
        for value in _parse_csv(self.params, "kinds"):
            try:
                kind = EntityKind.parse(value)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, f"invalid kind: {value}") from exc
            if kind not in result:
                result.append(kind)
        return tuple(result)

    def relations(self) -> tuple[str, ...]:
        return _parse_csv(self.params, "relations")

    def layout(self) -> LayoutKind:
        raw = self.get("layout") or LayoutKind.FORCE.value
        try:
            return LayoutKind.parse(raw)
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, f"invalid layout: {raw}") from exc

    def seed(self) -> int:
        return _parse_int(self.params, "seed", DEFAULT_SEED, 0, 1000000)

    def width(self) -> float:
        return _parse_float(self.params, "width", DEFAULT_WIDTH, 100.0, 4000.0)

    def height(self) -> float:
        return _parse_float(self.params, "height", DEFAULT_HEIGHT, 100.0, 4000.0)

    def iterations(self) -> int:
        return _parse_int(self.params, "iterations", DEFAULT_ITERATIONS, 0, 200)

    def node_id(self) -> str:
        return _required(self.params, "node_id")

    def source(self) -> str:
        return _required(self.params, "source")

    def target(self) -> str:
        return _required(self.params, "target")

    def snapshot_name(self) -> str:
        return _required(self.params, "name")

    def validate_all(self) -> None:
        """Validate every optional query parameter, regardless of route."""
        self.page()
        self.page_size()
        self.min_weight()
        self.label_contains()
        self.kinds()
        self.relations()
        self.layout()
        self.seed()
        self.width()
        self.height()
        self.iterations()

    def to_filter(self) -> GraphFilter:
        flt = GraphFilter()
        for kind in self.kinds():
            flt = flt.with_kind(kind)
        for relation in self.relations():
            try:
                flt = flt.with_relation(relation)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc)) from exc
        return flt.with_min_weight(self.min_weight()).with_label(self.label_contains())


@dataclass(slots=True)
class GraphApi:
    """Handler collection bound to a builder, store, and event bus."""

    builder: GraphBuilder = field(default_factory=GraphBuilder)
    store: GraphStore = field(default_factory=GraphStore)
    bus: EventBus = field(default_factory=EventBus)
    capabilities: CapabilitySet = field(default_factory=CapabilitySet.full)
    gate: FeatureGate = field(default_factory=lambda: FeatureGate(CapabilitySet.full()))
    id_factory: Callable[[], str] = new_entity_id
    clock: Callable[[], str] = utc_now

    def data(self) -> GraphData:
        return self.builder.build()

    def _require_read(self) -> None:
        self.gate.require(FeatureFlag.GRAPH_WORKBENCH)
        self.capabilities.require(Capability.READ)

    def _require_export(self) -> None:
        self._require_read()
        self.capabilities.require(Capability.EXPORT)

    def _meta(
        self,
        request: GraphRequest,
        page: int,
        page_size: int,
        etag: str,
        next_cursor: str = "",
    ) -> PageMeta:
        return PageMeta(
            request_id=request.request_id(self.id_factory),
            page=page,
            page_size=page_size,
            etag=weak_etag(etag),
            next_cursor=next_cursor,
        )

    def _filtered(self, request: GraphRequest, source: str) -> tuple[GraphData, GraphFilter, Any]:
        flt = request.to_filter()
        result = FilterEngine(flt).apply(self.data())
        payload = {
            "source": source,
            "filter": flt.describe(),
            "visible_nodes": len(result.nodes),
            "visible_edges": len(result.edges),
            "hidden_nodes": result.hidden_nodes,
            "hidden_edges": result.hidden_edges,
        }
        self.bus.publish(
            DomainEvent(
                kind=EventKind.GRAPH_FILTERED,
                aggregate_id="graph-workbench",
                aggregate_kind=EntityKind.GRAPH_FILTER,
                occurred_at=self.clock(),
                event_id=self.id_factory(),
                payload=payload,
            )
        )
        return result.to_data(), flt, result

    def handle_overview(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, flt, result = self._filtered(request, "overview")
        analyzer = GraphAnalyzer(data)
        metrics = analyzer.metrics()
        legend = relation_legend(data.edges)
        payload = {
            "node_count": metrics.node_count,
            "edge_count": metrics.edge_count,
            "component_count": metrics.component_count,
            "isolated_count": metrics.isolated_count,
            "density": metrics.density,
            "hidden_nodes": result.hidden_nodes,
            "hidden_edges": result.hidden_edges,
            "legend": [item.to_dict() for item in legend],
            "filter": flt.to_dict(),
        }
        return ok(
            payload,
            self._meta(request, request.page(), request.page_size(), str(payload)),
        )

    def handle_nodes(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, _, _ = self._filtered(request, "nodes")
        nodes = tuple(sorted(data.nodes, key=lambda node: node.id))
        page = paginate(nodes, request.page(), request.page_size())
        payload = page.to_dict(lambda node: node.to_dict())
        return ok(
            payload,
            self._meta(request, page.page, page.page_size, page.etag, page.next_cursor),
        )

    def handle_edges(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, _, _ = self._filtered(request, "edges")
        edges = tuple(sorted(data.edges, key=lambda edge: edge.key))
        page = paginate(edges, request.page(), request.page_size())
        payload = page.to_dict(lambda edge: edge.to_dict())
        return ok(
            payload,
            self._meta(request, page.page, page.page_size, page.etag, page.next_cursor),
        )

    def handle_metrics(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, _, _ = self._filtered(request, "metrics")
        metrics = GraphAnalyzer(data).metrics()
        return ok(metrics.to_dict(), self._meta(request, 1, 1, str(metrics.to_dict())))

    def handle_layout(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, _, _ = self._filtered(request, "layout")
        result = compute_layout(
            data,
            request.layout(),
            seed=request.seed(),
            width=request.width(),
            height=request.height(),
            iterations=request.iterations(),
        )
        return ok(result.to_dict(), self._meta(request, 1, 1, str(result.to_dict())))

    def handle_path(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        data, _, _ = self._filtered(request, "path")
        source, target = request.source(), request.target()
        path = GraphAnalyzer(data).shortest_path(source, target)
        payload = {
            "source": source,
            "target": target,
            "path": list(path),
            "hops": max(0, len(path) - 1),
            "found": bool(path),
        }
        return ok(payload, self._meta(request, 1, 1, str(payload)))

    def handle_filters(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        _, flt, result = self._filtered(request, "filters")
        all_data = self.data()
        kinds = sorted({node.kind.value for node in all_data.nodes})
        payload = {
            "current": flt.to_dict(),
            "description": flt.describe(),
            "available_kinds": kinds,
            "available_relations": [item.relation for item in relation_legend(all_data.edges)],
            "saved": {name: saved.to_dict() for name, saved in self.store.filters().items()},
            "hidden_node_ids": list(result.hidden_node_ids),
        }
        return ok(payload, self._meta(request, 1, 1, str(payload)))

    def handle_snapshots(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        names = tuple(self.store.names)
        page = paginate(names, request.page(), request.page_size())
        return ok(
            page.to_dict(),
            self._meta(request, page.page, page.page_size, page.etag, page.next_cursor),
        )

    def handle_snapshot(self, request: GraphRequest) -> dict[str, Any]:
        self._require_read()
        snapshot = self.store.load(request.snapshot_name())
        return ok(snapshot.to_dict(), self._meta(request, 1, 1, snapshot.name))

    def handle_export(self, request: GraphRequest) -> dict[str, Any]:
        self._require_export()
        name = request.get("name").strip()
        if name:
            payload = self.store.export(name)
        else:
            data, flt, _ = self._filtered(request, "export")
            payload = {
                "name": "current",
                "data": data.to_dict(),
                "filter": flt.to_dict(),
                "layout": request.layout().value,
                "created_at": self.clock(),
                "tags": [],
                "filter_index": {},
            }
        return ok(payload, self._meta(request, 1, 1, str(payload)))

    def handlers(self) -> dict[str, Callable[[GraphRequest], dict[str, Any]]]:
        return {
            "graph": self.handle_overview,
            "graph/nodes": self.handle_nodes,
            "graph/edges": self.handle_edges,
            "graph/metrics": self.handle_metrics,
            "graph/layout": self.handle_layout,
            "graph/path": self.handle_path,
            "graph/filters": self.handle_filters,
            "graph/snapshots": self.handle_snapshots,
            "graph/snapshot": self.handle_snapshot,
            "graph/export": self.handle_export,
        }

    def dispatch(self, route: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        handler = self.handlers().get(route)
        if handler is None:
            return fail(ApiError(ErrorCode.NOT_FOUND, f"unknown graph route: {route}"))
        request = GraphRequest(params, self.id_factory)
        try:
            request.validate_all()
            return handler(request)
        except ApiError as exc:
            return fail(exc)
        except PermissionError as exc:
            return fail(ApiError(ErrorCode.FORBIDDEN, str(exc)))
        except GraphStoreError as exc:
            code = ErrorCode.CONFLICT if "already exists" in str(exc) else ErrorCode.NOT_FOUND
            return fail(ApiError(code, str(exc)))
        except ValueError as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))


def _parse_int(params: Mapping[str, str], key: str, default: int, low: int, high: int) -> int:
    raw = params.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, f"invalid integer for {key}: {raw}") from exc
    if not low <= value <= high:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} out of range: {raw}")
    return value


def _parse_float(
    params: Mapping[str, str], key: str, default: float, low: float, high: float
) -> float:
    raw = params.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, f"invalid number for {key}: {raw}") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} out of range: {raw}")
    return value


def _parse_csv(params: Mapping[str, str], key: str) -> tuple[str, ...]:
    raw = params.get(key, "")
    if not raw.strip():
        return ()
    values = [item.strip().casefold() for item in raw.split(",") if item.strip()]
    if len(values) > MAX_FILTER_VALUES:
        raise ApiError(ErrorCode.INVALID_INPUT, f"too many values for {key}")
    return tuple(dict.fromkeys(values))


def _required(params: Mapping[str, str], key: str) -> str:
    value = params.get(key, "").strip()
    if not value:
        raise ApiError(ErrorCode.INVALID_INPUT, f"missing required parameter: {key}")
    return value


def register(api: RouteRegistry | object) -> None:
    """Register every graph workbench route on a v4 route registry.

    Objects without a ``register`` hook are ignored so dynamic namespace
    discovery stays safe with lightweight API stubs.
    """
    hook = getattr(api, "register", None)
    if not callable(hook):
        return
    registrar = cast(RouteRegistrar, api)
    for prefix, name in GRAPH_ROUTES:
        registrar.register(prefix, name, None)
