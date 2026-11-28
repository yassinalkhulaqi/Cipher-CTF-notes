"""v4 HTTP handlers for the report designer surface.

Handlers always return v4 success or error envelopes: validation, capability,
theme and store errors never escape across the API boundary. Rendering emits a
``REPORT_RENDERED`` domain event with an injected clock and id factory so tests
stay deterministic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from redscribe.v4.api_v4 import Route, RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.clock import SYSTEM_CLOCK, Clock
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
from redscribe.v4.events import DomainEvent, EventBus, EventKind
from redscribe.v4.pagination import PaginationError, paginate
from redscribe.v4.report_designer.service import (
    PaginationConfig,
    PaginationEngine,
    RenderedReport,
    ReportBuilder,
    ReportRenderer,
    ReportSource,
    ThemeError,
    ThemeResolver,
)
from redscribe.v4.report_designer.storage import LayoutStore, StoreError
from redscribe.v4.report_designer.types import ExportFormat, ReportSection, text_of


class Action(str, Enum):
    """Stable actions exposed by the report routes."""

    DESCRIBE = "describe"
    THEMES = "themes"
    THEME = "theme"
    LAYOUTS = "layouts"
    LAYOUT = "layout"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    PAGES = "pages"
    BUILD = "build"
    RENDER = "render"
    EXPORT = "export"
    MANIFEST = "manifest"
    STATS = "stats"

    @classmethod
    def parse(cls, value: str) -> Action:
        normalized = value.strip().casefold()
        for action in cls:
            if action.value == normalized:
                return action
        raise ApiError(ErrorCode.INVALID_INPUT, f"unknown action: {value}")


class PageLike(Protocol):
    """Structural view of pagination metadata used in envelopes."""

    @property
    def page(self) -> int: ...

    @property
    def page_size(self) -> int: ...

    @property
    def etag(self) -> str: ...

    @property
    def next_cursor(self) -> str: ...


WRITE_ACTIONS = frozenset({Action.CREATE, Action.UPDATE, Action.DELETE, Action.BUILD})
EXPORT_ACTIONS = frozenset({Action.RENDER, Action.EXPORT, Action.MANIFEST})
ROUTE_PREFIXES = (
    "reports",
    "reports/layouts",
    "reports/themes",
    "reports/pages",
    "reports/render",
    "reports/export",
    "reports/manifest",
)


def _bounded_int(
    payload: Mapping[str, object], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be between {minimum} and {maximum}")
    return value


def _object(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = payload.get(key, {})
    if not isinstance(value, Mapping):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ReportRequest:
    """A decoded, typed request for one report action."""

    action: Action
    layout_id: str = ""
    theme: str = ""
    title: str = ""
    page: int = 1
    page_size: int = 50
    fmt: ExportFormat = ExportFormat.HTML
    source: Mapping[str, object] = field(default_factory=dict)
    changes: Mapping[str, object] = field(default_factory=dict)
    sections: tuple[Mapping[str, object], ...] = ()
    manifests: tuple[tuple[str, ExportFormat, str, int], ...] = ()
    manifest_id: str = ""
    request_id: str = ""
    trigger: str = "api"

    @classmethod
    def from_payload(
        cls, action: str, payload: Mapping[str, object] | None = None
    ) -> ReportRequest:
        payload = payload or {}
        fmt_value = text_of(payload.get("format")) or text_of(payload.get("export_format"))
        try:
            fmt = ExportFormat.parse(fmt_value) if fmt_value else ExportFormat.HTML
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, str(exc)) from exc
        raw_sections = payload.get("sections", ())
        if not isinstance(raw_sections, (list, tuple)):
            raise ApiError(ErrorCode.INVALID_INPUT, "sections must be an array")
        sections = tuple(dict(item) if isinstance(item, Mapping) else {} for item in raw_sections)
        raw_manifests = payload.get("manifests", ())
        if not isinstance(raw_manifests, (list, tuple)):
            raise ApiError(ErrorCode.INVALID_INPUT, "manifests must be an array")
        manifests: list[tuple[str, ExportFormat, str, int]] = []
        for item in raw_manifests:
            if not isinstance(item, Mapping):
                raise ApiError(ErrorCode.INVALID_INPUT, "manifest entries must be objects")
            entry_format = text_of(item.get("format")) or ExportFormat.HTML.value
            try:
                parsed_format = ExportFormat.parse(entry_format)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc)) from exc
            page_count = item.get("page_count", 0)
            if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0:
                raise ApiError(ErrorCode.INVALID_INPUT, "page_count must be a non-negative integer")
            manifests.append(
                (
                    text_of(item.get("layout_id")),
                    parsed_format,
                    text_of(item.get("checksum")),
                    page_count,
                )
            )
        return cls(
            action=Action.parse(action),
            layout_id=text_of(payload.get("layout_id")),
            theme=text_of(payload.get("theme")),
            title=text_of(payload.get("title")),
            page=_bounded_int(payload, "page", 1, 1, 10000),
            page_size=_bounded_int(payload, "page_size", 50, 1, 500),
            fmt=fmt,
            source=_object(payload, "source"),
            changes=_object(payload, "changes"),
            sections=sections,
            manifests=tuple(manifests),
            manifest_id=text_of(payload.get("manifest_id")),
            request_id=text_of(payload.get("request_id")),
            trigger=text_of(payload.get("trigger")) or "api",
        )


def as_api_error(exc: Exception) -> ApiError:
    """Translate domain and platform exceptions into structured API errors."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, PermissionError):
        return ApiError(ErrorCode.FORBIDDEN, str(exc))
    if isinstance(exc, StoreError):
        if "unsupported" in str(exc) or "immutable" in str(exc):
            return ApiError(ErrorCode.INVALID_INPUT, str(exc))
        return ApiError(ErrorCode.NOT_FOUND, str(exc))
    if isinstance(exc, ThemeError):
        code = ErrorCode.NOT_FOUND if "unknown" in str(exc) else ErrorCode.INVALID_INPUT
        return ApiError(code, str(exc))
    if isinstance(exc, (PaginationError, ValueError, TypeError)):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc))
    return ApiError(ErrorCode.INTERNAL, "unexpected report failure")


class ReportApi:
    """Action dispatcher producing v4 envelopes for every report route."""

    SERVICE_NAME = "report-designer"

    def __init__(
        self,
        store: LayoutStore,
        resolver: ThemeResolver,
        builder: ReportBuilder,
        engine: PaginationEngine,
        renderer: ReportRenderer,
        gate: FeatureGate,
        capabilities: CapabilitySet,
        bus: EventBus,
        clock: Clock,
        id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.store = store
        self.resolver = resolver
        self.builder = builder
        self.engine = engine
        self.renderer = renderer
        self.gate = gate
        self.capabilities = capabilities
        self.bus = bus
        self.clock = clock
        self.id_factory = id_factory
        self._exports: list[RenderedReport] = []

    def actions(self) -> tuple[str, ...]:
        return tuple(action.value for action in Action)

    def register(self, registry: RouteRegistry) -> tuple[Route, ...]:
        """Register the report route family on a v4 route registry."""
        return tuple(
            registry.register(prefix, f"{self.SERVICE_NAME}:{prefix}") for prefix in ROUTE_PREFIXES
        )

    def _meta(self, request: ReportRequest, page: PageLike | None = None) -> PageMeta:
        return PageMeta(
            request_id=request.request_id or self.id_factory(),
            page=request.page if page is None else page.page,
            page_size=request.page_size if page is None else page.page_size,
            etag="" if page is None else page.etag,
            next_cursor="" if page is None else page.next_cursor,
        )

    def _authorize(self, action: Action) -> None:
        try:
            self.gate.require(FeatureFlag.REPORT_DESIGNER)
        except PermissionError as exc:
            raise ApiError(ErrorCode.FORBIDDEN, str(exc)) from exc
        self.capabilities.require(Capability.READ)
        if action in WRITE_ACTIONS:
            self.capabilities.require(Capability.WRITE)
        if action in EXPORT_ACTIONS:
            self.capabilities.require(Capability.EXPORT)

    def handle_payload(
        self, action: str, payload: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Decode a wire payload and always return an envelope."""
        try:
            return self.handle(ReportRequest.from_payload(action, payload))
        except Exception as exc:
            return fail(as_api_error(exc))

    def handle(self, request: ReportRequest) -> dict[str, object]:
        """Dispatch one authorized action to the domain services."""
        try:
            self._authorize(request.action)
            return self._dispatch(request)
        except Exception as exc:
            return fail(as_api_error(exc))

    def _dispatch(self, request: ReportRequest) -> dict[str, object]:
        action = request.action
        if action is Action.DESCRIBE:
            return ok(
                {
                    "service": self.SERVICE_NAME,
                    "actions": self.actions(),
                    "capabilities": sorted(item.value for item in self.capabilities.granted),
                    "routes": list(ROUTE_PREFIXES),
                    "formats": [item.value for item in ExportFormat],
                },
                self._meta(request),
            )
        if action is Action.THEMES:
            themes = self.resolver.describe()
            theme_page = paginate(themes, request.page, request.page_size)
            return ok(theme_page.to_dict(), self._meta(request, theme_page))
        if action is Action.THEME:
            name = request.theme or "classic"
            return ok(self.resolver.resolve(name).to_dict(), self._meta(request))
        if action is Action.LAYOUTS:
            layouts = self.store.all()
            if request.theme:
                layouts = self.store.by_theme(request.theme)
            layout_page = paginate(layouts, request.page, request.page_size)
            return ok(
                layout_page.to_dict(lambda layout: layout.to_dict()),
                self._meta(request, layout_page),
            )
        if action is Action.LAYOUT:
            return ok(self.store.require(request.layout_id).to_dict(), self._meta(request))
        if action is Action.CREATE:
            if not request.title:
                raise ApiError(ErrorCode.INVALID_INPUT, "title is required")
            sections = tuple(ReportSection.from_dict(item) for item in request.sections)
            created = self.store.create(
                request.title,
                theme=request.theme or "classic",
                sections=sections,
            )
            return ok(created.to_dict(), self._meta(request))
        if action is Action.UPDATE:
            updated = self.store.update(request.layout_id, request.changes)
            return ok(updated.to_dict(), self._meta(request))
        if action is Action.DELETE:
            deleted = self.store.delete(request.layout_id)
            return ok(deleted.to_dict(), self._meta(request))
        if action is Action.PAGES:
            layout = self.store.require(request.layout_id)
            pages = self.engine.paginate(layout)
            pages_page = paginate(pages, request.page, request.page_size)
            return ok(
                pages_page.to_dict(lambda item: item.to_dict()),
                self._meta(request, pages_page),
            )
        if action is Action.BUILD:
            source = ReportSource.from_dict(request.source)
            layout = self.builder.build(
                source,
                layout_id=request.layout_id or self.id_factory(),
                theme=request.theme or "classic",
                created_at=self.clock.iso(),
            )
            self.store.put(layout)
            return ok(layout.to_dict(), self._meta(request))
        if action in (Action.RENDER, Action.EXPORT):
            rendered = self._render(request)
            return ok(rendered.to_dict(), self._meta(request))
        if action is Action.MANIFEST:
            manifest = self.store.build_manifest(
                self._manifest_entries(request),
                manifest_id=request.manifest_id or self.id_factory(),
                generated_at=self.clock.iso(),
            )
            return ok(manifest.to_dict(), self._meta(request))
        if action is Action.STATS:
            stats: dict[str, object] = dict(self.store.stats().to_dict())
            stats["theme_index"] = self.store.theme_index()
            stats["page_size"] = PaginationConfig().to_dict()
            return ok(stats, self._meta(request))
        raise ApiError(ErrorCode.INVALID_INPUT, f"unhandled action: {action.value}")

    def _manifest_entries(
        self, request: ReportRequest
    ) -> tuple[tuple[str, ExportFormat, str, int], ...]:
        if request.manifests:
            return request.manifests
        export = self._exports[-1] if self._exports else None
        if export is None:
            raise ApiError(ErrorCode.CONFLICT, "no exports recorded for manifest")
        return ((export.layout_id, export.format, export.checksum, export.page_count),)

    def _render(self, request: ReportRequest) -> RenderedReport:
        layout = self.store.require(request.layout_id)
        rendered = self.renderer.render(layout, request.fmt)
        self._exports.append(rendered)
        event = DomainEvent(
            kind=EventKind.REPORT_RENDERED,
            aggregate_id=layout.id,
            aggregate_kind=EntityKind.REPORT,
            occurred_at=self.clock.iso(),
            event_id=self.id_factory(),
            payload={
                "layout_id": layout.id,
                "format": rendered.format.value,
                "page_count": rendered.page_count,
                "checksum": rendered.checksum,
                "trigger": request.trigger,
            },
        )
        self.bus.publish(event)
        return rendered

    def recent_exports(self) -> tuple[RenderedReport, ...]:
        return tuple(self._exports)


def build_api(
    store: LayoutStore | None = None,
    resolver: ThemeResolver | None = None,
    gate: FeatureGate | None = None,
    capabilities: CapabilitySet | None = None,
    bus: EventBus | None = None,
    clock: Clock | None = None,
    id_factory: Callable[[], str] = new_entity_id,
) -> ReportApi:
    """Construct the report API with injectable foundation services."""
    active_clock = clock or SYSTEM_CLOCK
    active_store = store or LayoutStore(id_factory=id_factory)
    active_resolver = resolver or ThemeResolver()
    engine = PaginationEngine()
    return ReportApi(
        store=active_store,
        resolver=active_resolver,
        builder=ReportBuilder(),
        engine=engine,
        renderer=ReportRenderer(active_resolver, engine),
        gate=gate or FeatureGate(CapabilitySet.full()),
        capabilities=capabilities or CapabilitySet.full(),
        bus=bus or EventBus(),
        clock=active_clock,
        id_factory=id_factory,
    )


def register(api: ReportApi, registry: RouteRegistry | None = None) -> tuple[Route, ...]:
    """Register report routes, defaulting to the process-wide registry."""
    from redscribe.v4.api_v4 import global_registry

    return api.register(registry if registry is not None else global_registry())


__all__ = [
    "EXPORT_ACTIONS",
    "ROUTE_PREFIXES",
    "WRITE_ACTIONS",
    "Action",
    "PageLike",
    "ReportApi",
    "ReportRequest",
    "as_api_error",
    "build_api",
    "register",
]
