"""Search namespace routes for the V3 API (branch B05)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.capabilities import CAP_SEARCH_V2
from redscribe.v3.search_intel.grammar import grammar_summary
from redscribe.v3.search_intel.parser import parse_query
from redscribe.v3.search_intel.service import SearchIntelService

_service: SearchIntelService | None = None


def get_service() -> SearchIntelService:
    """Return the namespace-scoped search service."""
    global _service
    if _service is None:
        _service = SearchIntelService()
    return _service


def reset_service() -> SearchIntelService:
    """Reset the namespace service, primarily for isolated tests."""
    global _service
    _service = SearchIntelService()
    return _service


def _check_capability(headers: Mapping[str, str]) -> None:
    requested = headers.get("X-Capability", "").strip().casefold()
    if requested and requested != CAP_SEARCH_V2:
        raise V3Error(
            V3ErrorCode.FORBIDDEN,
            f"Search requires capability '{CAP_SEARCH_V2}'",
        )


def _require_str(body: Mapping[str, Any], name: str) -> str:
    if name not in body:
        raise V3Error.missing(name)
    value = body[name]
    if not isinstance(value, str):
        raise V3Error.invalid(name, "expected a string")
    return value


def _optional_str(body: Mapping[str, Any], name: str, default: str = "") -> str:
    value = body.get(name, default)
    if not isinstance(value, str):
        raise V3Error.invalid(name, "expected a string")
    return value


def _optional_int(body: Mapping[str, Any], name: str, default: int) -> int:
    value = body.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise V3Error.invalid(name, "expected an integer")
    return value


def _optional_str_tuple(body: Mapping[str, Any], name: str) -> tuple[str, ...] | None:
    value = body.get(name)
    if value is None:
        return None
    if isinstance(value, str):
        return tuple(part for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        if not all(isinstance(item, str) for item in value):
            raise V3Error.invalid(name, "expected a list of strings")
        return tuple(value)
    raise V3Error.invalid(name, "expected a list of strings")


def _optional_selection(
    body: Mapping[str, Any],
) -> dict[str, list[str]] | None:
    value = body.get("selected")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise V3Error.invalid("selected", "expected an object")
    result: dict[str, list[str]] = {}
    for name, values in value.items():
        if isinstance(values, str):
            result[str(name)] = [values]
        elif isinstance(values, (list, tuple)) and all(isinstance(item, str) for item in values):
            result[str(name)] = list(values)
        else:
            raise V3Error.invalid("selected", "expected string arrays")
    return result


def register(router: V3Router) -> None:
    """Register all search namespace routes on a V3 router."""

    def parse(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {"parsed": parse_query(_require_str(body, "query")).as_dict()}

    def grammar(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {"grammar": grammar_summary()}

    def search(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return get_service().search(
            _require_str(body, "query"),
            fields=_optional_str_tuple(body, "fields"),
            selected=_optional_selection(body),
            cluster_by=_optional_str(body, "cluster_by", "field"),
            cluster_field=_optional_str(body, "cluster_field", "kind"),
            limit=_optional_int(body, "limit", 50),
            facet_limit=_optional_int(body, "facet_limit", 20),
            pivot_limit=_optional_int(body, "pivot_limit", 6),
            now=float(body.get("now", 0.0)),
        )

    def facets(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "facets": get_service().facets(
                _require_str(body, "query"),
                fields=_optional_str_tuple(body, "fields"),
                selected=_optional_selection(body),
                limit=_optional_int(body, "limit", 20),
            )
        }

    def clusters(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "clusters": get_service().clusters(
                _require_str(body, "query"),
                strategy=_optional_str(body, "strategy", "field"),
                field=_optional_str(body, "field", "kind"),
                limit=_optional_int(body, "limit", 50),
            )
        }

    def pivots(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "context": get_service().pivots(
                _require_str(body, "ref"),
                limit=_optional_int(body, "limit", 8),
                depth=_optional_int(body, "depth", 1),
            )
        }

    def autocomplete(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        completions = get_service().autocomplete(
            _require_str(body, "text"),
            limit=_optional_int(body, "limit", 8),
        )
        return {"completions": [item.as_dict() for item in completions]}

    def templates(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "templates": [
                item.as_dict()
                for item in get_service().templates.list(category=_optional_str(body, "category"))
            ]
        }

    def template_render(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        values = body.get("values")
        if not isinstance(values, dict) or not all(isinstance(key, str) for key in values):
            raise V3Error.invalid("values", "expected an object")
        try:
            rendered = get_service().templates.render(_require_str(body, "template_id"), values)
        except KeyError as exc:
            raise V3Error.not_found("template") from exc
        except ValueError as exc:
            raise V3Error.invalid("values", str(exc)) from exc
        return {"query": rendered}

    def saved_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "items": [
                item.as_dict()
                for item in get_service().saved.list(
                    search=_optional_str(body, "search"),
                    tag=_optional_str(body, "tag"),
                    limit=_optional_int(body, "limit", 50),
                )
            ]
        }

    def saved_create(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        try:
            item = get_service().saved.create(
                _require_str(body, "name"),
                _require_str(body, "query"),
                description=_optional_str(body, "description"),
                tags=_optional_str_tuple(body, "tags") or (),
                pinned=bool(body.get("pinned", False)),
            )
        except ValueError as exc:
            raise V3Error.invalid("saved_search", str(exc)) from exc
        return {"item": item.as_dict()}

    def saved_update(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        saved_id = _require_str(body, "id")
        service = get_service()
        if service.saved.get(saved_id) is None:
            raise V3Error.not_found("saved search")
        tags = body.get("tags")
        try:
            item = service.saved.update(
                saved_id,
                name=body.get("name"),
                query=body.get("query"),
                description=body.get("description"),
                tags=tags,
                pinned=body.get("pinned"),
            )
        except (TypeError, ValueError) as exc:
            raise V3Error.invalid("saved_search", str(exc)) from exc
        return {"item": item.as_dict()}

    def saved_delete(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        deleted = get_service().saved.delete(_require_str(body, "id"))
        if not deleted:
            raise V3Error.not_found("saved search")
        return {"deleted": True}

    def facet_sets_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {
            "items": [
                item.as_dict()
                for item in get_service().facet_sets.list(limit=_optional_int(body, "limit", 50))
            ]
        }

    def facet_sets_create(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        fields = _optional_str_tuple(body, "fields") or ()
        try:
            item = get_service().facet_sets.create(
                _require_str(body, "name"),
                fields,
                description=_optional_str(body, "description"),
            )
        except ValueError as exc:
            raise V3Error.invalid("facet_set", str(exc)) from exc
        return {"item": item.as_dict()}

    def facet_sets_delete(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        deleted = get_service().facet_sets.delete(_require_str(body, "id"))
        if not deleted:
            raise V3Error.not_found("facet set")
        return {"deleted": True}

    def index_state(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {"state": get_service().index.state().as_dict()}

    def snapshot(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        return {"snapshot": get_service().snapshot()}

    def load(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _check_capability(headers)
        payload = body.get("snapshot")
        if not isinstance(payload, dict):
            raise V3Error.invalid("snapshot", "expected an object")
        return {"imported": get_service().load(payload)}

    router.add("search", "parse", parse)
    router.add("search", "grammar", grammar)
    router.add("search", "search", search)
    router.add("search", "facets", facets)
    router.add("search", "clusters", clusters)
    router.add("search", "pivots", pivots)
    router.add("search", "autocomplete", autocomplete)
    router.add("search", "templates", templates)
    router.add("search", "template_render", template_render)
    router.add("search", "saved_list", saved_list)
    router.add("search", "saved_create", saved_create)
    router.add("search", "saved_update", saved_update)
    router.add("search", "saved_delete", saved_delete)
    router.add("search", "facet_sets_list", facet_sets_list)
    router.add("search", "facet_sets_create", facet_sets_create)
    router.add("search", "facet_sets_delete", facet_sets_delete)
    router.add("search", "index_state", index_state)
    router.add("search", "snapshot", snapshot)
    router.add("search", "load", load)
