"""Validation and serialization helpers for graph API payloads."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from redscribe.v2.graph.model import GraphEdge, GraphNode

MAX_ITEMS = 200


def positive_int(
    value: object,
    *,
    field: str,
    default: int,
    minimum: int = 1,
    maximum: int = MAX_ITEMS,
) -> int:
    """Validate an optional bounded integer field."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def string_list(value: object, *, field: str) -> tuple[str, ...]:
    """Validate an optional list of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} must be a list of strings")
        if item.strip():
            result.append(item.strip())
    return tuple(result)


def int_list(value: object, *, field: str) -> tuple[int, ...]:
    """Validate an optional list of integer ids."""
    if value is None:
        return ()
    if isinstance(value, int) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{field} must be a list of integers")
        result.append(item)
    return tuple(result)


def endpoint_ids(
    body: Mapping[str, Any],
    *,
    resolve: Callable[[str], int | None] | None = None,
) -> tuple[int, int]:
    """Resolve source/target fields from ids or wikilink-style labels."""
    source = body.get("source")
    target = body.get("target")
    if source is None:
        source = body.get("from")
    if target is None:
        target = body.get("to")
    if source is None or target is None:
        raise ValueError("source and target are required")

    def one(value: object, field: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field} must be an id or label")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip() and resolve is not None:
            result = resolve(value)
            if isinstance(result, int):
                return result
        raise ValueError(f"{field} must be an id or label")

    return one(source, "source"), one(target, "target")


def node_payload(node: GraphNode) -> dict[str, Any]:
    """Serialize one graph vertex."""
    return node.as_dict()


def edge_payload(edge: GraphEdge) -> dict[str, Any]:
    """Serialize one graph edge."""
    return edge.as_dict()


def collection_payload(items: Sequence[dict[str, Any]], *, key: str) -> dict[str, Any]:
    """Wrap a serialized collection with a stable count field."""
    return {"count": len(items), key: list(items)}


def metric_payload(metrics: Mapping[str, float]) -> dict[str, Any]:
    """Serialize numeric graph metrics with stable key ordering."""
    return {key: metrics[key] for key in sorted(metrics)}
