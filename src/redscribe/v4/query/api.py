"""HTTP-facing handlers for the v4 query language.

Handlers are pure functions over parameter mappings: they validate input, check
capabilities, build v4 envelopes, and never touch a network socket. The route
registry only records their names; the shell decides how to bind them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict

from redscribe.v4.api_v4 import RouteRegistry, global_registry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import (
    ApiError,
    CapabilitySet,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.pagination import Cursor, PaginationError, apply_cursor, paginate, weak_etag
from redscribe.v4.query.service import (
    ClusteringEngine,
    Document,
    FacetEngine,
    QueryParser,
    SavedQueryService,
    SearchEvaluator,
)
from redscribe.v4.query.types import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    QUERY_CAPABILITIES,
    FieldName,
    QueryError,
    sequence_of,
)

DEFAULT_FACET_FIELDS: tuple[FieldName, ...] = (
    FieldName.KIND,
    FieldName.STATUS,
    FieldName.TAG,
    FieldName.TARGET,
)

_GET_ACTIONS = frozenset({"search", "list", "get"})
_POST_ACTIONS = frozenset({"search", "save", "rename", "delete", "export"})


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return default


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in ("1", "true", "yes", "on")
    return default


def _as_fields(value: object) -> tuple[FieldName, ...]:
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = [str(item) for item in sequence_of(value)]
    fields: list[FieldName] = []
    for part in parts:
        name = part.strip()
        if not name:
            continue
        field = FieldName.parse(name)
        if field is None:
            raise QueryError(f"unknown facet field: {name}", details=(f"field={name}",))
        if field not in fields:
            fields.append(field)
    return tuple(fields)


def _as_selections(value: object) -> dict[str, tuple[str, ...]]:
    selections: dict[str, tuple[str, ...]] = {}
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise QueryError("malformed facet selections", details=(str(exc),)) from exc
        value = decoded
    if not isinstance(value, Mapping):
        return selections
    for key, raw in value.items():
        field = FieldName.parse(str(key))
        if field is None:
            raise QueryError(f"unknown facet field: {key}")
        parts = [str(item) for item in sequence_of(raw)]
        if isinstance(raw, str):
            parts = raw.split(",")
        selections[field.value] = tuple(item.strip() for item in parts if item.strip())
    return selections


def _as_documents(value: object, fallback: Sequence[Document]) -> list[Document]:
    if value is None:
        return list(fallback)
    documents: list[Document] = []
    for item in sequence_of(value):
        if not isinstance(item, Mapping):
            raise QueryError("documents must be a list of objects")
        documents.append(dict(item))
    return documents


class QueryApi:
    """Stateless request handlers backed by injected domain services."""

    def __init__(
        self,
        service: SavedQueryService | None = None,
        parser: QueryParser | None = None,
        evaluator: SearchEvaluator | None = None,
        facets: FacetEngine | None = None,
        clusters: ClusteringEngine | None = None,
        capabilities: CapabilitySet | None = None,
        gate: FeatureGate | None = None,
        documents: Sequence[Document] | None = None,
        request_id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.service = service or SavedQueryService()
        self.parser = parser or self.service.parser
        self.evaluator = evaluator or SearchEvaluator()
        self.facets = facets or FacetEngine()
        self.clusters = clusters or ClusteringEngine()
        self.capabilities = capabilities or CapabilitySet.full()
        self.gate = gate or FeatureGate(self.capabilities)
        self.documents = list(documents or [])
        self.request_id_factory = request_id_factory

    def _meta(
        self,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        etag: str = "",
        next_cursor: str = "",
    ) -> PageMeta:
        return PageMeta(
            request_id=self.request_id_factory(),
            page=page,
            page_size=page_size,
            etag=etag,
            next_cursor=next_cursor,
        )

    def _authorize(self, action: str) -> None:
        self.capabilities.require(QUERY_CAPABILITIES[action])
        self.gate.require(FeatureFlag.QUERY_LANGUAGE)

    @staticmethod
    def _page_args(params: Mapping[str, object]) -> tuple[int, int]:
        page = _as_int(params.get("page"), 1)
        page_size = _as_int(params.get("page_size"), DEFAULT_PAGE_SIZE)
        if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise QueryError("invalid pagination arguments")
        return page, page_size

    def search(self, params: Mapping[str, object]) -> dict[str, object]:
        """Run a structured search and return hits, facets, and clusters."""
        self._authorize("search")
        expression = str(params.get("expression", params.get("q", "")))
        query = self.parser.parse(expression)
        page, page_size = self._page_args(params)

        documents = _as_documents(params.get("documents"), self.documents)
        matches = self.evaluator.filter_documents(documents, query)
        if _as_bool(params.get("rank")):
            matches = self.evaluator.rank_documents(matches, query)

        fields = _as_fields(params["facets"]) if "facets" in params else DEFAULT_FACET_FIELDS
        selections = _as_selections(params.get("facet_selections"))
        if selections:
            selected_fields = tuple(FieldName.parse(key) for key in selections)
            matches = self.facets.filter_by_facets(
                matches,
                {field: selections[field.value] for field in selected_fields if field},
            )

        cursor = str(params.get("cursor", ""))
        if cursor:
            matches = list(apply_cursor(matches, cursor))
            page = 1
        result = paginate(matches, page=page, page_size=page_size)

        facet_list = [facet.to_dict() for facet in self.facets.build(matches, fields, selections)]
        cluster_field_raw = str(params.get("cluster_field", ""))
        cluster_field = None
        if cluster_field_raw:
            cluster_field = FieldName.require(cluster_field_raw)
        cluster_list: list[dict[str, object]] = []
        cluster_summary: dict[str, object] = {}
        if cluster_field is not None:
            built = self.clusters.group(matches, cluster_field)
            cluster_list = [cluster.to_dict() for cluster in built]
            cluster_summary = self.clusters.summary(built)

        data: dict[str, object] = {
            "expression": expression,
            "normalized": query.normalized,
            "token_count": query.token_count,
            "hits": result.to_dict(serialize=lambda document: dict(document)),
            "facets": facet_list,
            "clusters": cluster_list,
            "cluster_summary": cluster_summary,
            "warnings": self.evaluator.validate(query),
            "cursor_applied": bool(cursor),
        }
        etag = weak_etag(f"{query.normalized}:{result.page}:{result.page_size}:{result.total}")
        return ok(
            data,
            self._meta(
                page=result.page,
                page_size=result.page_size,
                etag=etag,
                next_cursor=result.next_cursor,
            ),
        )

    def list_saved(self, params: Mapping[str, object]) -> dict[str, object]:
        """List saved queries with cursor pagination."""
        self._authorize("list")
        page, page_size = self._page_args(params)
        queries = self.service.list()
        cursor = str(params.get("cursor", ""))
        if cursor:
            queries = queries[Cursor.decode(cursor).offset :]
            page = 1
        result = paginate(queries, page=page, page_size=page_size)
        data: dict[str, object] = result.to_dict(serialize=lambda query: query.to_dict())
        etag = weak_etag(f"saved:{len(queries)}:{result.etag}")
        return ok(
            data,
            self._meta(
                page=result.page,
                page_size=result.page_size,
                etag=etag,
                next_cursor=result.next_cursor,
            ),
        )

    def get_saved(self, params: Mapping[str, object]) -> dict[str, object]:
        self._authorize("get")
        query = self.service.get(str(params.get("id", "")))
        return ok(query.to_dict(), self._meta(etag=weak_etag(str(asdict(query)))))

    def save(self, params: Mapping[str, object]) -> dict[str, object]:
        self._authorize("save")
        query = self.service.save(str(params.get("name", "")), str(params.get("expression", "")))
        return ok(query.to_dict(), self._meta(etag=weak_etag(query.id)))

    def rename(self, params: Mapping[str, object]) -> dict[str, object]:
        self._authorize("rename")
        query = self.service.rename(str(params.get("id", "")), str(params.get("name", "")))
        return ok(query.to_dict(), self._meta(etag=weak_etag(query.name)))

    def delete(self, params: Mapping[str, object]) -> dict[str, object]:
        self._authorize("delete")
        query = self.service.delete(str(params.get("id", "")))
        return ok({"deleted": query.to_dict()}, self._meta())

    def export(self, params: Mapping[str, object]) -> dict[str, object]:
        self._authorize("export")
        payload = self.service.export_json()
        return ok(
            {"json": payload, "count": self.service.store.count()},
            self._meta(etag=weak_etag(payload)),
        )

    def dispatch(self, method: str, params: Mapping[str, object]) -> dict[str, object]:
        """Route a method/action pair to the right handler."""
        action = str(params.get("action", "search")).strip().casefold()
        verb = method.strip().upper()
        if verb == "GET" and action in _GET_ACTIONS:
            handlers = {
                "search": self.search,
                "list": self.list_saved,
                "get": self.get_saved,
            }
            return handlers[action](params)
        if verb == "POST" and action in _POST_ACTIONS:
            handlers = {
                "search": self.search,
                "save": self.save,
                "rename": self.rename,
                "delete": self.delete,
                "export": self.export,
            }
            return handlers[action](params)
        raise QueryError(
            f"unsupported query route: {verb} {action}",
            details=(f"method={verb}", f"action={action}"),
        )

    def execute(self, method: str, params: Mapping[str, object]) -> dict[str, object]:
        """Dispatch and translate every expected exception into an envelope."""
        try:
            return self.dispatch(method, params)
        except QueryError as exc:
            return fail(exc.to_api_error())
        except PaginationError as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))
        except PermissionError as exc:
            return fail(ApiError(ErrorCode.FORBIDDEN, str(exc)))
        except ApiError as exc:
            return fail(exc)
        except ValueError as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))


def register_routes(registry: RouteRegistry | None = None) -> RouteRegistry:
    """Register the ``/query`` GET/POST route on a v4 registry (idempotent)."""
    target = registry if registry is not None else global_registry()
    definitions = (
        ("/query", "query"),
        ("/query/saved", "query_saved"),
    )
    for prefix, name in definitions:
        try:
            target.register(prefix, name)
        except ValueError:
            continue
    return target
