"""Graph-workbench namespace for the V3 API.

Routes are registered additively through ``router.add("graph", action, ...)``.
The module keeps one lazily created workbench per process and lets tests or
other branches replace it with ``set_workbench``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import Handler, V3Router
from redscribe.v3.capabilities import CAP_GRAPH, CapabilityError
from redscribe.v3.entities import EntityService
from redscribe.v3.graph_workbench.service import GraphWorkbench, WorkbenchFilters
from redscribe.v3.graph_workbench.snapshots import UnknownSnapshotError

WorkbenchHandler = Callable[[dict[str, Any], Mapping[str, str]], dict[str, Any]]

_workbench: GraphWorkbench | None = None


def set_workbench(workbench: GraphWorkbench | None) -> None:
    """Replace the namespace service, mostly useful for tests."""
    global _workbench
    _workbench = workbench


def current_workbench() -> GraphWorkbench:
    """Return the lazy default workbench, creating it on first use."""
    global _workbench
    if _workbench is None:
        _workbench = GraphWorkbench(EntityService())
    return _workbench


def reset_workbench() -> GraphWorkbench | None:
    """Drop the current service, returning the previous instance."""
    global _workbench
    previous = _workbench
    _workbench = None
    return previous


def _to_error(error: Exception) -> V3Error:
    """Translate domain validation failures into stable V3 errors."""
    if isinstance(error, V3Error):
        return error
    if isinstance(error, CapabilityError):
        return V3Error(V3ErrorCode.FORBIDDEN, str(error))
    if isinstance(error, UnknownSnapshotError):
        return V3Error.not_found("snapshot")
    if isinstance(error, KeyError):
        return V3Error.missing(str(error).strip("'\""))
    return V3Error.invalid("request", str(error))


def _guard(callback: WorkbenchHandler) -> Handler:
    """Wrap a handler so domain errors become V3 error envelopes."""

    def wrapped(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return callback(body, headers)
        except (V3Error, CapabilityError, UnknownSnapshotError, ValueError, KeyError) as error:
            raise _to_error(error) from error

    return wrapped


def _require(body: dict[str, Any], key: str) -> Any:
    """Read a required field with a stable missing-field error."""
    if key not in body or body[key] is None:
        raise V3Error.missing(key)
    return body[key]


def _text(body: dict[str, Any], key: str, *, default: str = "") -> str:
    """Read a required-or-default string field."""
    value = body.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise V3Error.invalid(key, "must be a string")
    return value.strip() or default


def _boolean(body: dict[str, Any], key: str, *, default: bool = False) -> bool:
    """Read a boolean field."""
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    raise V3Error.invalid(key, "must be a boolean")


def _number(body: dict[str, Any], key: str, *, default: float) -> float:
    """Read a numeric field."""
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise V3Error.invalid(key, "must be a number")
    return float(value)


def _optional_int(body: dict[str, Any], key: str) -> int | None:
    """Read an optional integer field."""
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise V3Error.invalid(key, "must be an integer")
    return value


def _check_capability_header(headers: Mapping[str, str]) -> None:
    """Respect the optional capability hint on V3 requests."""
    requested = headers.get("X-Capability", "")
    if requested and requested.strip().casefold() not in (CAP_GRAPH, "graph_workbench"):
        raise V3Error(
            V3ErrorCode.FORBIDDEN,
            f"This route requires the '{CAP_GRAPH}' capability",
            field="X-Capability",
        )


def _filters(body: dict[str, Any]) -> WorkbenchFilters:
    """Build filters from an optional nested payload."""
    raw = body.get("filters")
    if raw is None:
        raw = {
            key: body[key]
            for key in ("kinds", "tags", "severities", "query", "max_nodes")
            if key in body
        }
    if not isinstance(raw, dict):
        raise V3Error.invalid("filters", "must be an object")
    try:
        return WorkbenchFilters.from_dict(raw)
    except ValueError as error:
        raise V3Error.invalid("filters", str(error)) from error


def register(router: V3Router) -> None:
    """Register every graph-workbench route on a V3 router."""

    @_guard
    def overview(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().overview(filters=_filters(body))

    @_guard
    def entities(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        refs = current_workbench().entities.refs()
        needle = _text(body, "query").casefold()
        if needle:
            refs = tuple(ref for ref in refs if needle in str(ref).casefold())
        return {"refs": [ref.as_dict() for ref in refs], "count": len(refs)}

    @_guard
    def graph(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().graph(filters=_filters(body)).as_dict()

    @_guard
    def inspect(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().inspect(str(_require(body, "node")))

    @_guard
    def layout(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        from redscribe.v3.graph_workbench.layout import LayoutOptions

        option_data = body.get("options")
        options = LayoutOptions.from_dict(option_data if isinstance(option_data, dict) else body)
        return (
            current_workbench()
            .layout(
                _text(body, "strategy", default="force"),
                options=options,
                filters=_filters(body),
            )
            .as_dict()
        )

    @_guard
    def clusters(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return (
            current_workbench()
            .clusters(
                _text(body, "dimension", default="tag"),
                tag_prefix=_text(body, "tag_prefix"),
                filters=_filters(body),
            )
            .as_dict()
        )

    @_guard
    def cluster_dashboard(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().cluster_dashboard(filters=_filters(body))

    @_guard
    def path(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return (
            current_workbench()
            .path(
                str(_require(body, "source")),
                str(_require(body, "target")),
                directed=_boolean(body, "directed"),
                weighted=_boolean(body, "weighted"),
                max_hops=_optional_int(body, "max_hops"),
                filters=_filters(body),
            )
            .as_dict()
        )

    @_guard
    def articulation(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().articulation(filters=_filters(body))

    @_guard
    def neighbors(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        depth = body.get("depth", 1)
        if isinstance(depth, bool) or not isinstance(depth, int):
            raise V3Error.invalid("depth", "must be an integer")
        return current_workbench().neighborhood(
            str(_require(body, "node")), depth=depth, filters=_filters(body)
        )

    @_guard
    def connect(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        record = current_workbench().connect(
            str(_require(body, "source")),
            str(_require(body, "target")),
            kind=_text(body, "kind", default="relates"),
            label=_text(body, "label"),
            weight=_number(body, "weight", default=1.0),
            actor=_text(body, "actor", default="local"),
        )
        return record.as_dict()

    @_guard
    def disconnect(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        record = current_workbench().disconnect(
            str(_require(body, "source")),
            str(_require(body, "target")),
            kind=_text(body, "kind", default="relates"),
            label=_text(body, "label"),
            weight=_number(body, "weight", default=1.0),
            actor=_text(body, "actor", default="local"),
        )
        return record.as_dict()

    @_guard
    def update_relationship(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        changes: dict[str, Any] = {"kind": _text(body, "kind", default="relates")}
        if "label" in body:
            changes["label"] = _text(body, "label")
        if "weight" in body:
            changes["weight"] = _number(body, "weight", default=1.0)
        record = current_workbench().update_relationship(
            str(_require(body, "source")),
            str(_require(body, "target")),
            **changes,
        )
        return record.as_dict()

    @_guard
    def undo(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        record = current_workbench().undo()
        return {"applied": record is not None, "record": record.as_dict() if record else None}

    @_guard
    def redo(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        record = current_workbench().redo()
        return {"applied": record is not None, "record": record.as_dict() if record else None}

    @_guard
    def history(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().history()

    @_guard
    def snapshot(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        snap = current_workbench().capture(
            label=_text(body, "label"), source=_text(body, "source", default="workbench")
        )
        return snap.as_dict(include_records=True)

    @_guard
    def snapshots(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        limit = body.get("limit", 20)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise V3Error.invalid("limit", "must be an integer")
        return current_workbench().snapshots.payload(limit=limit)

    @_guard
    def diff(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return (
            current_workbench()
            .compare(str(_require(body, "left")), str(_require(body, "right")))
            .as_dict()
        )

    @_guard
    def restore(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return current_workbench().snapshots.restore(str(_require(body, "id"))).as_dict()

    @_guard
    def export(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        result = current_workbench().export(
            _text(body, "format", default="json"),
            filters=_filters(body),
            pretty=_boolean(body, "pretty"),
            include_metadata=_boolean(body, "include_metadata", default=True),
            direction=_text(body, "direction", default="LR"),
        )
        return result.as_dict()

    @_guard
    def tag_index(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability_header(headers)
        return {"tags": current_workbench().tag_index(filters=_filters(body))}

    routes: tuple[tuple[str, WorkbenchHandler], ...] = (
        ("overview", overview),
        ("entities", entities),
        ("graph", graph),
        ("inspect", inspect),
        ("layout", layout),
        ("clusters", clusters),
        ("cluster-dashboard", cluster_dashboard),
        ("path", path),
        ("articulation", articulation),
        ("neighbors", neighbors),
        ("connect", connect),
        ("disconnect", disconnect),
        ("update-relationship", update_relationship),
        ("undo", undo),
        ("redo", redo),
        ("history", history),
        ("snapshot", snapshot),
        ("snapshots", snapshots),
        ("diff", diff),
        ("restore", restore),
        ("export", export),
        ("tag-index", tag_index),
    )
    for action, handler in routes:
        router.add("graph", action, handler)
