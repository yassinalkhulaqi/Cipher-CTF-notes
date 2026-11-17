"""V2 API namespace for search, saved queries, and commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any
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
from redscribe.v2.search.filters import filters_from_dict
from redscribe.v2.search.service import SearchService

_SERVICES: WeakKeyDictionary[ApiV2, SearchService] = WeakKeyDictionary()
NamespaceHandler = Callable[[SearchService, dict[str, Any]], RouteResult]


def _bind(
    service: SearchService, handler: NamespaceHandler
) -> Callable[[dict[str, Any]], RouteResult]:
    def call(body: dict[str, Any]) -> RouteResult:
        return handler(service, body)

    return call


def get_service(api: ApiV2) -> SearchService:
    """Return the search service attached to one API registry."""
    service = _SERVICES.get(api)
    if service is None:
        service = SearchService(api.vault)
        _SERVICES[api] = service
    return service


def _limit(body: Mapping[str, Any], *, default: int = 20) -> int:
    value = optional_int(body, "limit")
    if value is None:
        return default
    if value < 1 or value > MAX_PAGE_SIZE:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            f"limit must be between 1 and {MAX_PAGE_SIZE}",
            details={"field": "limit"},
        )
    return value


def _width(body: Mapping[str, Any]) -> int:
    value = optional_int(body, "width")
    if value is None:
        return 180
    if value < 40 or value > 600:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            "width must be between 40 and 600",
            details={"field": "width"},
        )
    return value


def _filters(body: Mapping[str, Any]) -> tuple[Any, ...]:
    raw = body.get("filters", ())
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise V2Error(
            400,
            V2ErrorCode.INVALID_TYPE,
            "filters must be a list",
            details={"field": "filters"},
        )
    try:
        return filters_from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            f"Invalid filter: {exc}",
            details={"field": "filters"},
        ) from exc


def _saved_id(body: Mapping[str, Any]) -> str:
    value = require_str(body, "id", max_length=120).strip()
    if not value:
        raise V2Error(400, V2ErrorCode.MISSING_FIELD, "Saved query id is required")
    return value


def _json_result(data: Any, *, status: int = 200) -> RouteResult:
    return RouteResult(data, status=status, etag=compute_etag(data))


def search_query(service: SearchService, body: dict[str, Any]) -> RouteResult:
    """Run a ranked search and return a paginated envelope payload."""
    text = optional_str(body, "query", default="", max_length=500) or ""
    result = service.search(
        text,
        limit=MAX_PAGE_SIZE,
        sort=optional_str(body, "sort"),
        group_by=optional_str(body, "group_by", default="") or "",
        filters=_filters(body),
        facet_field=optional_str(body, "facet_field", default="") or "",
        width=_width(body),
    )
    payload = result.as_dict()
    items, page = paginate(
        payload["items"], cursor=optional_str(body, "cursor"), limit=_limit(body)
    )
    payload["items"] = items
    payload["total"] = page.total or 0
    data = {"result": payload, "page": page.as_dict()}
    return RouteResult(data, page=page, etag=compute_etag(data))


def search_suggest(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = optional_str(body, "query", default="", max_length=500) or ""
    suggestions = service.suggest(text, limit=_limit(body))
    return _json_result({"query": text, "suggestions": list(suggestions)})


def search_facets(service: SearchService, body: dict[str, Any]) -> RouteResult:
    field = require_str(body, "field", max_length=40).strip().casefold()
    if not field:
        raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "field cannot be empty")
    values = service.facets(field, limit=_limit(body))
    return _json_result({"field": field, "facets": [item.as_dict() for item in values]})


def search_snippet(service: SearchService, body: dict[str, Any]) -> RouteResult:
    node_id = optional_int(body, "id")
    if node_id is None:
        raise V2Error(400, V2ErrorCode.MISSING_FIELD, "id is required", details={"field": "id"})
    query = optional_str(body, "query", default="", max_length=500) or ""
    snippet = service.snippet(node_id, query, width=_width(body))
    if not snippet:
        raise V2Error(
            404, V2ErrorCode.NOT_FOUND, "Document is not indexed", details={"id": node_id}
        )
    return _json_result(snippet)


def search_terms(service: SearchService, body: dict[str, Any]) -> RouteResult:
    terms = service.term_dictionary(
        prefix=optional_str(body, "prefix", default="") or "",
        limit=_limit(body, default=50),
    )
    return _json_result({"terms": list(terms)})


def search_status(service: SearchService, body: dict[str, Any]) -> RouteResult:
    return _json_result(service.status())


def search_reindex(service: SearchService, body: dict[str, Any]) -> RouteResult:
    update = service.reindex()
    return _json_result(update.as_dict())


def search_describe(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = optional_str(body, "query", default="", max_length=500) or ""
    return _json_result(service.describe(text))


def saved_list(service: SearchService, body: dict[str, Any]) -> RouteResult:
    items = service.saved.list(
        search=optional_str(body, "search", default="") or "",
        tag=optional_str(body, "tag", default="") or "",
        limit=_limit(body, default=50),
    )
    return _json_result({"items": [item.as_dict() for item in items]})


def saved_get(service: SearchService, body: dict[str, Any]) -> RouteResult:
    item = service.saved.get(_saved_id(body))
    if item is None:
        raise V2Error(404, V2ErrorCode.NOT_FOUND, "Saved query does not exist")
    return _json_result(item.as_dict())


def saved_create(service: SearchService, body: dict[str, Any]) -> RouteResult:
    name = require_str(body, "name", max_length=80)
    query = require_str(body, "query", max_length=500)
    tags = body.get("tags", ())
    if isinstance(tags, str):
        tag_values: Sequence[str] | str = tags
    elif isinstance(tags, (list, tuple)):
        tag_values = [str(value) for value in tags]
    else:
        raise V2Error(400, V2ErrorCode.INVALID_TYPE, "tags must be a string or list")
    try:
        item = service.saved.create(
            name,
            query,
            description=optional_str(body, "description", default="", max_length=240) or "",
            tags=tag_values,
            pinned=bool(body.get("pinned", False)),
        )
    except ValueError as exc:
        raise V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc)) from exc
    return _json_result(item.as_dict(), status=201)


def saved_update(service: SearchService, body: dict[str, Any]) -> RouteResult:
    saved_id = _saved_id(body)
    changes: dict[str, Any] = {}
    for key in ("name", "query", "description"):
        if key in body:
            changes[key] = require_str(body, key, max_length=500)
    if "tags" in body:
        raw = body["tags"]
        if isinstance(raw, str):
            changes["tags"] = raw
        elif isinstance(raw, (list, tuple)):
            changes["tags"] = [str(value) for value in raw]
        else:
            raise V2Error(400, V2ErrorCode.INVALID_TYPE, "tags must be a string or list")
    if "pinned" in body:
        if not isinstance(body["pinned"], bool):
            raise V2Error(400, V2ErrorCode.INVALID_TYPE, "pinned must be a boolean")
        changes["pinned"] = body["pinned"]
    try:
        item = service.saved.update(saved_id, **changes)
    except ValueError as exc:
        raise V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc)) from exc
    if item is None:
        raise V2Error(404, V2ErrorCode.NOT_FOUND, "Saved query does not exist")
    return _json_result(item.as_dict())


def saved_delete(service: SearchService, body: dict[str, Any]) -> RouteResult:
    removed = service.saved.delete(_saved_id(body))
    if not removed:
        raise V2Error(404, V2ErrorCode.NOT_FOUND, "Saved query does not exist")
    return _json_result({"removed": True})


def saved_use(service: SearchService, body: dict[str, Any]) -> RouteResult:
    item = service.saved.record_use(_saved_id(body))
    if item is None:
        raise V2Error(404, V2ErrorCode.NOT_FOUND, "Saved query does not exist")
    result = service.search(item.query, limit=_limit(body))
    return _json_result({"saved": item.as_dict(), "result": result.as_dict()})


def commands_parse(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = require_str(body, "text", max_length=500)
    parsed = service.parse_command(text)
    data = parsed.as_dict()
    if parsed.node is not None:
        data["plan"] = service.commands.plan(parsed.node).as_dict()
    return _json_result(data)


def commands_suggest(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = require_str(body, "text", max_length=500)
    suggestions = service.command_suggestions(text, limit=_limit(body))
    return _json_result({"suggestions": [item.as_dict() for item in suggestions]})


def commands_complete(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = require_str(body, "text", max_length=500)
    cursor = optional_int(body, "cursor")
    completion = service.command_completion(text, cursor=cursor, limit=_limit(body))
    return _json_result(completion.as_dict())


def commands_list(service: SearchService, body: dict[str, Any]) -> RouteResult:
    data = service.command_help()
    if optional_str(body, "kind"):
        kind = str(body["kind"]).casefold()
        data["commands"] = [item for item in data["commands"] if item["kind"] == kind]
    return _json_result(data)


def commands_help(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = optional_str(body, "text", default="", max_length=200) or ""
    data = service.command_help()
    if text:
        needle = text.strip().lstrip("/:").casefold()
        data["commands"] = [
            item for item in data["commands"] if item["name"] == needle or needle in item["aliases"]
        ]
    return _json_result(data)


def commands_run(service: SearchService, body: dict[str, Any]) -> RouteResult:
    text = require_str(body, "text", max_length=500)
    result = service.run_command(
        text,
        limit=_limit(body),
        group_by=optional_str(body, "group_by", default="") or "",
    )
    return _json_result(result)


def register(api: ApiV2) -> None:
    """Register every search and command route on an API v2 registry."""
    service = get_service(api)
    existing = api.routes
    registrations: tuple[
        tuple[str, NamespaceHandler, str, tuple[str, ...], tuple[str, ...], bool, str], ...
    ] = (
        (
            "search.query",
            search_query,
            "Search notes with ranking, filters, and snippets.",
            (),
            ("query", "cursor", "limit", "sort", "group_by", "facet_field", "width", "filters"),
            False,
            "search",
        ),
        (
            "search.suggest",
            search_suggest,
            "Suggest indexed terms and saved query names.",
            (),
            ("query", "limit"),
            False,
            "search",
        ),
        (
            "search.facets",
            search_facets,
            "Return facet counts for one metadata field.",
            ("field",),
            ("limit",),
            False,
            "search",
        ),
        (
            "search.snippet",
            search_snippet,
            "Build a highlighted snippet for one note.",
            ("id",),
            ("query", "width"),
            False,
            "search",
        ),
        (
            "search.terms",
            search_terms,
            "List index vocabulary terms for completion.",
            (),
            ("prefix", "limit"),
            False,
            "search",
        ),
        (
            "search.status",
            search_status,
            "Report index statistics and service status.",
            (),
            (),
            False,
            "search",
        ),
        (
            "search.reindex",
            search_reindex,
            "Rebuild the incremental search index.",
            (),
            (),
            True,
            "search_index",
        ),
        (
            "search.describe",
            search_describe,
            "Describe a parsed query without executing it.",
            (),
            ("query",),
            False,
            "search",
        ),
        (
            "saved.list",
            saved_list,
            "List saved queries with optional filters.",
            (),
            ("search", "tag", "limit"),
            False,
            "saved_query",
        ),
        (
            "saved.get",
            saved_get,
            "Return one saved query by id.",
            ("id",),
            (),
            False,
            "saved_query",
        ),
        (
            "saved.create",
            saved_create,
            "Create a named saved query.",
            ("name", "query"),
            ("description", "tags", "pinned"),
            True,
            "saved_query",
        ),
        (
            "saved.update",
            saved_update,
            "Update a saved query's fields.",
            ("id",),
            ("name", "query", "description", "tags", "pinned"),
            True,
            "saved_query",
        ),
        ("saved.delete", saved_delete, "Delete one saved query.", ("id",), (), True, "saved_query"),
        (
            "saved.use",
            saved_use,
            "Run a saved query and record its use.",
            ("id",),
            ("limit",),
            True,
            "saved_query",
        ),
        (
            "commands.parse",
            commands_parse,
            "Parse a slash command into a plan.",
            ("text",),
            (),
            False,
            "command",
        ),
        (
            "commands.suggest",
            commands_suggest,
            "Suggest commands and saved queries.",
            ("text",),
            ("limit",),
            False,
            "command",
        ),
        (
            "commands.complete",
            commands_complete,
            "Complete a command at a cursor position.",
            ("text",),
            ("cursor", "limit"),
            False,
            "command",
        ),
        (
            "commands.list",
            commands_list,
            "List command grammar and registered commands.",
            (),
            ("kind",),
            False,
            "command",
        ),
        (
            "commands.help",
            commands_help,
            "Return help for all or one command.",
            (),
            ("text",),
            False,
            "command",
        ),
        (
            "commands.run",
            commands_run,
            "Parse and preview a slash command.",
            ("text",),
            ("limit", "group_by"),
            False,
            "command",
        ),
    )
    for name, handler, description, required, optional, mutating, entity_type in registrations:
        if name in existing:
            continue
        api._register(
            name,
            _bind(service, handler),
            description,
            required=required,
            optional=optional,
            mutating=mutating,
            entity_type=entity_type,
        )
