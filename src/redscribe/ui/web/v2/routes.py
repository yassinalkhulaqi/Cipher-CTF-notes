"""Route registry and built-in handlers for API v2.

Routes are addressed as ``"namespace.action"`` and remain additive. The first
wave covers the platform kernel only: health, capabilities, schema, events,
version compatibility, and the note read surface plus a minimal create route
used to exercise idempotency and mutation auditing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from redscribe import __version__
from redscribe.content.markdown import render_markdown_body
from redscribe.domain.models import KINDS, STATUSES, Node
from redscribe.storage.db import Vault
from redscribe.ui.web.api_contract import (
    MAX_CONTENT_LENGTH,
    MAX_SHORT_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
)
from redscribe.ui.web.v2 import storage_bridge as storage
from redscribe.ui.web.v2.contracts import (
    API_VERSION,
    DEFAULT_PAGE_SIZE,
    MAX_BODY_BYTES,
    MAX_PAGE_SIZE,
    Page,
    V2Error,
    V2ErrorCode,
    compute_etag,
    decode_cursor,
    encode_cursor,
    optional_int,
    optional_str,
    paginate,
    require_int,
    require_str,
)

RouteHandler = Callable[[dict[str, Any]], "RouteResult"]


@dataclass(frozen=True, slots=True)
class RouteResult:
    """The data and transport metadata produced by one route."""

    data: Any
    page: Page | None = None
    etag: str | None = None
    status: int = 200


@dataclass(frozen=True, slots=True)
class Route:
    """One registered v2 route and its introspection metadata."""

    name: str
    handler: RouteHandler
    description: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    mutating: bool = False
    entity_type: str = ""

    def as_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": list(self.required),
            "optional": list(self.optional),
            "required_fields": list(self.required),
            "optional_fields": list(self.optional),
            "mutating": self.mutating,
        }


def _node_summary(node: Node, *, path: str = "") -> dict[str, Any]:
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "difficulty": node.difficulty,
        "flag": node.flag,
        "tags": node.tags,
        "tag_list": node.tag_list,
        "target": node.target,
        "pinned": node.pinned,
        "trashed": node.is_trashed,
        "path": path,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


def _node_detail(vault: Vault, node: Node) -> dict[str, Any]:
    data = _node_summary(node, path=vault.path_of(node.id, include_self=False))
    if node.is_folder:
        data["children"] = [
            _node_summary(child, path=vault.path_of(child.id, include_self=False))
            for child in vault.children(node.id)
        ]
        data["has_preview"] = False
        return data
    data["content"] = node.content
    data["preview_html"] = render_markdown_body(node.content)
    return data


def _page_limit(body: dict[str, Any], *, default: int = DEFAULT_PAGE_SIZE) -> int:
    limit = optional_int(body, "limit")
    if limit is None:
        return default
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            f"limit must be between 1 and {MAX_PAGE_SIZE}",
            details={"field": "limit"},
        )
    return limit


def _event_id(event: dict[str, Any]) -> int | None:
    for key in ("id", "event_id", "seq", "sequence"):
        value = event.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _event_cursor(body: dict[str, Any]) -> int:
    since = optional_int(body, "since_id")
    if since is not None:
        return max(0, since)
    cursor = optional_str(body, "cursor")
    if not cursor:
        return 0
    value = decode_cursor(cursor)
    if isinstance(value, bool):
        raise V2Error(400, V2ErrorCode.INVALID_CURSOR, "Invalid cursor")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, dict):
        raw = value.get("since_id")
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            return raw
    raise V2Error(400, V2ErrorCode.INVALID_CURSOR, "Invalid cursor")


class ApiV2:
    """Vault-backed route registry for the versioned API surface."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault
        self._routes: dict[str, Route] = {}
        self._register(
            "system.health",
            self._system_health,
            "Report vault health, versions, FTS availability, and note count.",
        )
        self._register(
            "system.capabilities",
            self._system_capabilities,
            "Report v2 namespaces, features, and request limits.",
        )
        self._register(
            "system.api_schema",
            self._system_api_schema,
            "Return the v2 route inventory with fields and mutation flags.",
        )
        self._register(
            "system.events",
            self._system_events,
            "List entity events, optionally after a sequence id and by entity.",
            optional=("since_id", "cursor", "limit", "entity_type", "entity_id"),
        )
        self._register(
            "api.version",
            self._api_version,
            "Report the API version and v1 compatibility information.",
        )
        self._register(
            "notes.list",
            self._notes_list,
            "List live notes with deterministic ordering and cursor pagination.",
            optional=("kind", "status", "target", "tag", "query", "cursor", "limit"),
        )
        self._register(
            "notes.get",
            self._notes_get,
            "Return one note or folder by id.",
            required=("id",),
        )
        self._register(
            "notes.create",
            self._notes_create,
            "Create a note and return its detail payload.",
            optional=("title", "content", "tags", "target", "parent_id"),
            mutating=True,
            entity_type="note",
        )

    @property
    def vault(self) -> Vault:
        return self._vault

    @property
    def routes(self) -> dict[str, Route]:
        return dict(self._routes)

    def route(self, name: str) -> Route:
        route = self._routes.get(name)
        if route is None:
            raise V2Error(
                404,
                V2ErrorCode.UNKNOWN_ROUTE,
                f"Unknown API v2 route '{name}'",
                details={"route": name},
            )
        return route

    def invoke(self, name: str, body: dict[str, Any]) -> RouteResult:
        route = self.route(name)
        result = route.handler(body)
        return result

    def _register(
        self,
        name: str,
        handler: RouteHandler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None:
        self._routes[name] = Route(
            name=name,
            handler=handler,
            description=description,
            required=required,
            optional=optional,
            mutating=mutating,
            entity_type=entity_type,
        )

    # ------------------------------------------------------------------
    # System routes
    # ------------------------------------------------------------------

    def _system_health(self, body: dict[str, Any]) -> RouteResult:
        stats = self._vault.basic_stats()
        data = {
            "ok": True,
            "version": __version__,
            "schema_version": self._vault.schema_version,
            "fts_enabled": bool(getattr(self._vault, "fts_enabled", False)),
            "note_count": stats.notes,
        }
        return RouteResult(data, etag=compute_etag(data))

    def _system_capabilities(self, body: dict[str, Any]) -> RouteResult:
        namespaces = sorted({route.name.split(".", 1)[0] for route in self._routes.values()})
        data = {
            "api_version": API_VERSION,
            "namespaces": namespaces,
            "features": [
                "request_ids",
                "idempotency",
                "pagination",
                "etags",
                "entity_events",
                "request_audit",
                "v1_compatibility",
            ],
            "limits": {
                "max_body_bytes": MAX_BODY_BYTES,
                "default_page_size": DEFAULT_PAGE_SIZE,
                "max_page_size": MAX_PAGE_SIZE,
            },
            "mutating_routes": sorted(
                route.name for route in self._routes.values() if route.mutating
            ),
        }
        return RouteResult(data, etag=compute_etag(data))

    def _system_api_schema(self, body: dict[str, Any]) -> RouteResult:
        routes = [self._routes[name].as_schema() for name in sorted(self._routes)]
        data = {
            "api_version": API_VERSION,
            "route_names": [route["name"] for route in routes],
            "routes": routes,
            "error_codes": [code.value for code in V2ErrorCode],
        }
        return RouteResult(data, etag=compute_etag(data))

    def _system_events(self, body: dict[str, Any]) -> RouteResult:
        since_id = _event_cursor(body)
        limit = _page_limit(body)
        entity_type = optional_str(body, "entity_type")
        raw_entity_id = body.get("entity_id")
        entity_id: object = raw_entity_id if isinstance(raw_entity_id, int) else None
        if isinstance(raw_entity_id, str) and raw_entity_id:
            entity_id = raw_entity_id

        events = storage.list_events(
            self._vault,
            since_id=since_id,
            limit=limit + 1,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        filtered: list[dict[str, Any]] = []
        for event in events:
            event_id = _event_id(event)
            if since_id and event_id is not None and event_id <= since_id:
                continue
            if entity_type is not None and event.get("entity_type") not in (None, entity_type):
                continue
            if entity_id is not None and event.get("entity_id") not in (None, entity_id):
                continue
            filtered.append(event)

        filtered.sort(key=lambda item: _event_id(item) or 0)
        has_more = len(filtered) > limit
        page_data = filtered[:limit]
        next_cursor: str | None = None
        if has_more and page_data:
            last_id = _event_id(page_data[-1])
            if last_id is not None:
                next_cursor = encode_cursor({"since_id": last_id})
        page = Page(
            cursor=encode_cursor({"since_id": since_id}),
            next=next_cursor,
            total=len(filtered),
            limit=limit,
            has_more=has_more,
        )
        return RouteResult(page_data, page=page, etag=compute_etag(page_data))

    def _api_version(self, body: dict[str, Any]) -> RouteResult:
        data = {
            "version": __version__,
            "api_version": API_VERSION,
            "compatible_api_versions": ["1.0", API_VERSION],
            "v1_compatible": True,
            "schema_version": self._vault.schema_version,
        }
        return RouteResult(data, etag=compute_etag(data))

    # ------------------------------------------------------------------
    # Notes routes
    # ------------------------------------------------------------------

    def _notes_list(self, body: dict[str, Any]) -> RouteResult:
        kind = optional_str(body, "kind")
        if kind is not None and kind not in KINDS:
            raise V2Error(
                400,
                V2ErrorCode.INVALID_CHOICE,
                f"Unknown kind: {kind}",
                details={"field": "kind"},
            )
        status = optional_str(body, "status")
        if status is not None and status not in STATUSES:
            raise V2Error(
                400,
                V2ErrorCode.INVALID_CHOICE,
                f"Unknown status: {status}",
                details={"field": "status"},
            )
        target = optional_str(body, "target")
        tag = optional_str(body, "tag")
        query = optional_str(body, "query")
        cursor = optional_str(body, "cursor")
        limit = _page_limit(body)

        nodes = self._vault.live_nodes()
        if kind is None:
            nodes = [node for node in nodes if node.is_note]
        else:
            nodes = [node for node in nodes if node.kind == kind]
        if status is not None:
            nodes = [node for node in nodes if node.status == status]
        if target:
            needle = target.casefold()
            nodes = [node for node in nodes if node.target.casefold() == needle]
        if tag:
            needle = tag.casefold()
            nodes = [
                node for node in nodes if needle in {value.casefold() for value in node.tag_list}
            ]
        if query:
            needle = query.casefold()
            nodes = [
                node
                for node in nodes
                if needle in f"{node.title}\n{node.content}\n{node.tags}\n{node.target}".casefold()
            ]

        nodes.sort(key=lambda node: node.id)
        page_nodes, page = paginate(nodes, cursor=cursor, limit=limit)
        data = [
            _node_summary(node, path=self._vault.path_of(node.id, include_self=False))
            for node in page_nodes
        ]
        etag = compute_etag({"items": data, "page": page.as_dict()})
        return RouteResult(data, page=page, etag=etag)

    def _notes_get(self, body: dict[str, Any]) -> RouteResult:
        node_id = require_int(body, "id")
        node = self._vault.get_node(node_id)
        if node is None:
            raise V2Error(
                404,
                V2ErrorCode.NOT_FOUND,
                "Note does not exist",
                details={"id": node_id},
            )
        data = _node_detail(self._vault, node)
        return RouteResult(data, etag=compute_etag(data))

    def _notes_create(self, body: dict[str, Any]) -> RouteResult:
        title = require_str(body, "title", default="", max_length=MAX_TITLE_LENGTH).strip()
        content = optional_str(body, "content", default="", max_length=MAX_CONTENT_LENGTH) or ""
        tags = optional_str(body, "tags", default="", max_length=MAX_TAG_LENGTH) or ""
        target = optional_str(body, "target", default="", max_length=MAX_SHORT_LENGTH) or ""
        parent_id = optional_int(body, "parent_id")
        if not title:
            title = content.splitlines()[0][:60].strip() if content.strip() else ""
        if not title and not content.strip():
            raise V2Error(
                400,
                V2ErrorCode.INVALID_REQUEST,
                "A title or content is required",
                details={"fields": ["title", "content"]},
            )
        node = self._vault.create_node(
            title or "Untitled",
            parent_id,
            content=content,
            tags=tags,
            target=target,
        )
        data = _node_detail(self._vault, node)
        return RouteResult(data, etag=compute_etag(data))
