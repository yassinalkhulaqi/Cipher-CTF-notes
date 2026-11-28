"""HTTP-facing v4 accessibility routes.

The endpoint is a thin, typed adapter over the a11y/i18n services. Every reply
is a v4 envelope, every mutation is gated on capability and feature flags, and
every preference change emits a redacted ``PREFERENCE_CHANGED`` event through
the shared event bus.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from redscribe.v4.a11y_i18n.service import (
    A11yAuditor,
    A11yServiceError,
    I18nCatalog,
    MotionPolicyResolver,
    TourEngine,
)
from redscribe.v4.a11y_i18n.storage import CatalogIndex, PreferenceSnapshotStore, StorageError
from redscribe.v4.a11y_i18n.types import (
    EmptyStateSpec,
    MessageId,
    MotionPreference,
    UiDescriptor,
)
from redscribe.v4.api_v4 import RouteRegistry, register_routes
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
from redscribe.v4.events import DomainEvent, EventBus, EventKind, default_redactor
from redscribe.v4.preferences import PreferenceStore

ROUTE_PREFIX = "/accessibility"
ROUTE_NAME = "a11y-i18n"

SAFE_EVENT_KEYS = frozenset(
    {
        "action",
        "density",
        "direction",
        "feature",
        "locale",
        "motion",
        "snapshot_name",
        "theme",
        "version",
    }
)

EMPTY_STATES: dict[str, EmptyStateSpec] = {
    "issues": EmptyStateSpec(
        "No accessibility issues",
        "Run the audit again after adjusting your content.",
        "Run audit",
    ),
    "snapshots": EmptyStateSpec(
        "No saved preferences",
        "Save a snapshot to restore this setup later.",
        "Save snapshot",
    ),
    "tour": EmptyStateSpec(
        "Tour complete",
        "Restart the tour to review the controls again.",
        "Restart tour",
    ),
}


class AccessibilityEndpoint:
    """Stateful handler for the ``/accessibility`` GET and PATCH surface."""

    def __init__(
        self,
        store: PreferenceSnapshotStore | None = None,
        auditor: A11yAuditor | None = None,
        catalog: I18nCatalog | None = None,
        catalog_index: CatalogIndex | None = None,
        resolver: MotionPolicyResolver | None = None,
        tour: TourEngine | None = None,
        preferences: PreferenceStore | None = None,
        capabilities: CapabilitySet | None = None,
        gate: FeatureGate | None = None,
        bus: EventBus | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store or PreferenceSnapshotStore()
        self.auditor = auditor or A11yAuditor()
        self.catalog = catalog or I18nCatalog()
        self.catalog_index = catalog_index or CatalogIndex()
        self.resolver = resolver or MotionPolicyResolver()
        self.tour = tour or TourEngine()
        self.preferences = preferences or PreferenceStore()
        self.capabilities = capabilities or CapabilitySet.full()
        self.gate = gate or FeatureGate(self.capabilities)
        self.bus = bus or EventBus()
        self.id_factory = id_factory or new_entity_id
        self.reduce_motion = False
        self.high_contrast = False
        self._events = 0
        for locale in self.catalog.available_locales():
            if catalog_index is not None:
                continue
            self.catalog_index.register(self.catalog.catalog_for(locale))

    @property
    def actions(self) -> tuple[str, ...]:
        return (
            "audit",
            "motion",
            "preferences",
            "reset",
            "snapshot-delete",
            "snapshot-load",
            "snapshot-save",
            "tour",
            "translate",
        )

    @property
    def event_count(self) -> int:
        return self._events

    def _meta(self) -> PageMeta:
        return PageMeta(request_id=self.id_factory(), version="v4")

    def describe(self) -> dict[str, Any]:
        """Return a complete, serializable view of current state."""
        preferences = self.preferences.current
        policy = self.resolver.resolve(preferences.motion, self.reduce_motion, self.high_contrast)
        directions = {
            locale: self.catalog.direction_for(locale).value
            for locale in self.catalog.available_locales()
        }
        return {
            "actions": list(self.actions),
            "capabilities": sorted(item.value for item in self.capabilities.granted),
            "catalogs": self.catalog_index.export(),
            "directions": directions,
            "empty_states": {key: value.to_dict() for key, value in EMPTY_STATES.items()},
            "event_count": self._events,
            "feature_enabled": self.gate.is_enabled(FeatureFlag.A11Y_I18N),
            "locales": list(self.catalog.available_locales()),
            "motion": policy.to_dict(),
            "preferences": preferences.to_dict(),
            "reduce_motion": self.reduce_motion,
            "rules": [rule.to_dict() for rule in self.auditor.rules()],
            "snapshots": self.store.index().to_dict(),
            "tour": self.tour.snapshot().to_dict(),
            "tour_step": self.tour.current().to_dict(),
        }

    def handle_get(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Handle ``GET /accessibility``."""
        del payload
        try:
            self._authorize(Capability.READ)
            return ok(self.describe(), self._meta())
        except ApiError as exc:
            return fail(exc)

    def handle_patch(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Handle ``PATCH /accessibility`` with an ``action`` discriminator."""
        meta = self._meta()
        try:
            self._authorize(Capability.WRITE)
            if not isinstance(payload, Mapping):
                raise ApiError(ErrorCode.INVALID_INPUT, "body must be an object")
            action = str(payload.get("action", "preferences"))
            handler = self._handlers().get(action)
            if handler is None:
                raise ApiError(ErrorCode.INVALID_INPUT, f"unknown action: {action}")
            result = handler(payload)
            return ok({"action": action, "result": result, "status": self.describe()}, meta)
        except (ApiError, A11yServiceError, StorageError, ValueError, TypeError) as exc:
            return fail(_as_api_error(exc))
        except KeyError as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, f"missing field: {exc}"))

    def dispatch(self, method: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch by HTTP verb for registration with generic route tables."""
        normalized = method.upper()
        if normalized == "GET":
            return self.handle_get(payload)
        if normalized == "PATCH":
            return self.handle_patch(payload)
        return fail(ApiError(ErrorCode.INVALID_INPUT, f"unsupported method: {method}"))

    def _authorize(self, capability: Capability) -> None:
        try:
            self.gate.require(FeatureFlag.A11Y_I18N)
        except PermissionError as exc:
            raise ApiError(ErrorCode.FORBIDDEN, str(exc)) from exc
        self.capabilities.require(capability)

    def _handlers(self) -> dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]]:
        return {
            "audit": self._action_audit,
            "motion": self._action_motion,
            "preferences": self._action_preferences,
            "reset": self._action_reset,
            "snapshot-delete": self._action_snapshot_delete,
            "snapshot-load": self._action_snapshot_load,
            "snapshot-save": self._action_snapshot_save,
            "tour": self._action_tour,
            "translate": self._action_translate,
        }

    # -- action handlers -------------------------------------------------

    def _action_preferences(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raw = body.get("preferences", dict(body))
        if not isinstance(raw, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "preferences must be an object")
        before = self.preferences.current
        updated = self.preferences.update(raw)
        self._emit(
            EventKind.PREFERENCE_CHANGED,
            {
                "action": "preferences",
                "density": updated.density,
                "direction": updated.direction,
                "locale": updated.locale,
                "motion": updated.motion,
                "theme": updated.theme,
                "version": self.preferences.revision,
            },
        )
        return {"changed": updated != before, "preferences": updated.to_dict()}

    def _action_motion(self, body: Mapping[str, Any]) -> dict[str, Any]:
        preference = MotionPreference.parse(str(body.get("motion", "full")))
        self.reduce_motion = bool(body.get("reduce_motion", False))
        self.high_contrast = bool(body.get("high_contrast", self.high_contrast))
        if not isinstance(body.get("reduce_motion", False), bool):
            raise ApiError(ErrorCode.INVALID_INPUT, "reduce_motion must be a boolean")
        self.preferences.update({"motion": preference.value})
        policy = self.resolver.resolve(preference, self.reduce_motion, self.high_contrast)
        self._emit(
            EventKind.PREFERENCE_CHANGED,
            {
                "action": "motion",
                "motion": preference.value,
                "version": self.preferences.revision,
            },
        )
        return {"motion": policy.to_dict(), "preference": preference.value}

    def _action_reset(self, body: Mapping[str, Any]) -> dict[str, Any]:
        self.preferences.reset()
        self.reduce_motion = False
        self.high_contrast = False
        self._emit(
            EventKind.PREFERENCE_CHANGED,
            {"action": "reset", "version": self.preferences.revision},
        )
        return {"preferences": self.preferences.current.to_dict(), "reset": True}

    def _action_snapshot_save(self, body: Mapping[str, Any]) -> dict[str, Any]:
        name = str(body.get("name", ""))
        snapshot = self.store.save(
            name,
            self.preferences.current,
            self.resolver.resolve(
                self.preferences.current.motion, self.reduce_motion, self.high_contrast
            ),
            self.preferences.current.locale,
            overwrite=bool(body.get("overwrite", False)),
        )
        self._emit(
            EventKind.PREFERENCE_CHANGED,
            {
                "action": "snapshot-save",
                "locale": snapshot.locale,
                "snapshot_name": snapshot.name,
                "version": snapshot.version,
            },
        )
        return {"snapshot": snapshot.to_dict(), "total": self.store.count()}

    def _action_snapshot_load(self, body: Mapping[str, Any]) -> dict[str, Any]:
        name = str(body.get("name", ""))
        snapshot = self.store.load(name)
        self.preferences.update(snapshot.preferences.to_dict())
        self._emit(
            EventKind.PREFERENCE_CHANGED,
            {
                "action": "snapshot-load",
                "locale": snapshot.locale,
                "snapshot_name": snapshot.name,
                "version": snapshot.version,
            },
        )
        return {"snapshot": snapshot.to_dict()}

    def _action_snapshot_delete(self, body: Mapping[str, Any]) -> dict[str, Any]:
        self.capabilities.require(Capability.DELETE)
        removed = self.store.remove(str(body.get("name", "")))
        return {"removed": removed.name, "total": self.store.count()}

    def _action_tour(self, body: Mapping[str, Any]) -> dict[str, Any]:
        operation = str(body.get("operation", "next"))
        operations: dict[str, Callable[[], Any]] = {
            "start": self.tour.start,
            "next": self.tour.next,
            "previous": self.tour.previous,
            "skip": self.tour.skip,
            "complete": self.tour.complete,
            "reset": self.tour.reset,
        }
        handler = operations.get(operation)
        if handler is None:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unknown tour operation: {operation}")
        state = handler()
        return {
            "operation": operation,
            "state": state.to_dict(),
            "step": self.tour.current().to_dict(),
        }

    def _action_audit(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raw = body.get("descriptors", [])
        if not isinstance(raw, list):
            raise ApiError(ErrorCode.INVALID_INPUT, "descriptors must be a list")
        descriptors = [UiDescriptor.from_dict(dict(item)) for item in raw]
        report = self.auditor.audit(descriptors)
        return {"report": report.to_dict()}

    def _action_translate(self, body: Mapping[str, Any]) -> dict[str, Any]:
        try:
            message = MessageId.parse(str(body.get("message", "")))
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, "unknown message id") from exc
        locale = str(body.get("locale", self.preferences.current.locale))
        raw_params = body.get("params", {})
        if not isinstance(raw_params, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "params must be an object")
        if bool(body.get("plural", False)):
            count = body.get("count", 1)
            if isinstance(count, bool) or not isinstance(count, int):
                raise ApiError(ErrorCode.INVALID_INPUT, "count must be an integer")
            result = self.catalog.translate_plural(message, count, locale, raw_params)
        else:
            result = self.catalog.translate(message, locale, raw_params)
        return {"translation": result.to_dict()}

    def _emit(self, kind: EventKind, payload: Mapping[str, Any]) -> DomainEvent:
        safe = {name: value for name, value in payload.items() if name in SAFE_EVENT_KEYS}
        sanitized = default_redactor(safe)
        event = DomainEvent(
            kind=kind,
            aggregate_id=str(safe.get("snapshot_name", "preferences")),
            aggregate_kind=EntityKind.NOTE,
            payload=sanitized,
        )
        self.bus.publish(event)
        self._events += 1
        return event


def _as_api_error(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, StorageError):
        message = str(exc)
        if "exists" in message:
            return ApiError(ErrorCode.CONFLICT, message)
        if "not found" in message or "not indexed" in message:
            return ApiError(ErrorCode.NOT_FOUND, message)
        return ApiError(ErrorCode.INVALID_INPUT, message)
    if isinstance(exc, (A11yServiceError, ValueError, TypeError)):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc))
    return ApiError(ErrorCode.INTERNAL, "accessibility request failed")


DEFAULT_ENDPOINT: AccessibilityEndpoint | None = None


def default_endpoint() -> AccessibilityEndpoint:
    """Return the lazily created process-wide endpoint."""
    global DEFAULT_ENDPOINT
    if DEFAULT_ENDPOINT is None:
        DEFAULT_ENDPOINT = AccessibilityEndpoint()
    return DEFAULT_ENDPOINT


def register_endpoint(
    registry: RouteRegistry, endpoint: AccessibilityEndpoint | None = None
) -> AccessibilityEndpoint:
    """Register the endpoint dispatcher on a v4 route registry."""
    handler = endpoint or default_endpoint()
    registry.register(ROUTE_PREFIX, ROUTE_NAME, handler.dispatch)
    return handler


def register_global(endpoint: AccessibilityEndpoint | None = None) -> AccessibilityEndpoint:
    """Register the endpoint on the process-wide v4 route registry."""
    handler = endpoint or default_endpoint()
    register_routes(ROUTE_PREFIX, ROUTE_NAME, handler.dispatch)
    return handler


def register(api: Any) -> None:
    """Register with a route registry, mapping, or opaque API object."""
    handler = default_endpoint().dispatch
    registrar = getattr(api, "register", None)
    if callable(registrar):
        registrar(ROUTE_PREFIX, ROUTE_NAME, handler)
        return
    if isinstance(api, MutableMapping):
        api[f"/api/v4{ROUTE_PREFIX}"] = handler


def empty_state(key: str) -> EmptyStateSpec:
    """Return an empty-state spec by name."""
    try:
        return EMPTY_STATES[key]
    except KeyError as exc:
        raise ValueError(f"unknown empty state: {key}") from exc


__all__ = [
    "EMPTY_STATES",
    "ROUTE_NAME",
    "ROUTE_PREFIX",
    "SAFE_EVENT_KEYS",
    "AccessibilityEndpoint",
    "default_endpoint",
    "empty_state",
    "register",
    "register_endpoint",
    "register_global",
]
