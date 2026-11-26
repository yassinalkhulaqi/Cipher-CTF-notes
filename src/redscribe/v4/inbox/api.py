"""HTTP-facing v4 routes for the capture inbox.

Handlers return standard v4 envelopes and structured errors. They own request
validation, pagination, capability checks, and error translation; domain rules
stay in :mod:`redscribe.v4.inbox.service`. Route registration is additive and
idempotent so the namespace discovery in ``redscribe.v4`` can call it safely.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, TypeVar

from redscribe.v4.api_v4 import Route, global_registry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.inbox.service import (
    CaptureNotFoundError,
    InboxService,
    TemplateError,
    TransitionError,
)
from redscribe.v4.inbox.types import CaptureItem, CaptureSource, TriageState, normalize_tags
from redscribe.v4.pagination import (
    PageResult,
    PaginationError,
    apply_cursor,
    etag_matches,
    paginate,
    weak_etag,
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
ROUTE_SPECS: tuple[tuple[str, str], ...] = (
    ("/inbox", "inbox.list"),
    ("/inbox/capture", "inbox.create"),
    ("/inbox/triage", "inbox.triage"),
)

F = TypeVar("F", bound=Callable[..., dict[str, Any]])


def require_str(body: Mapping[str, Any], key: str) -> str:
    """Read a required, non-blank string from a request mapping."""
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be a non-empty string", (key,))
    return value.strip()


def optional_str(body: Mapping[str, Any], key: str, limit: int = 240) -> str | None:
    """Read an optional string, rejecting oversized or mistyped values."""
    value = body.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be a string", (key,))
    result = value.strip()
    if len(result) > limit:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} exceeds {limit} characters", (key,))
    return result or None


def optional_int(body: Mapping[str, Any], key: str, default: int, low: int, high: int) -> int:
    """Read a bounded integer query parameter."""
    value = body.get(key)
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an integer", (key,))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an integer", (key,)) from exc
    if not low <= parsed <= high:
        raise ApiError(
            ErrorCode.INVALID_INPUT,
            f"{key} must be between {low} and {high}",
            (key,),
        )
    return parsed


def optional_enum(
    body: Mapping[str, Any],
    key: str,
    enum_type: type[CaptureSource] | type[TriageState],
) -> CaptureSource | TriageState | None:
    """Read an optional enum value from a request mapping."""
    value = optional_str(body, key, 60)
    if value is None:
        return None
    try:
        return enum_type.parse(value)
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, str(exc), (key,)) from exc


def optional_tags(body: Mapping[str, Any]) -> tuple[str, ...]:
    """Read and canonicalize an optional list of tags."""
    value = body.get("tags")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(tag, str) for tag in value):
        raise ApiError(ErrorCode.INVALID_INPUT, "tags must be a list of strings", ("tags",))
    try:
        return normalize_tags(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, str(exc), ("tags",)) from exc


def optional_confidence(body: Mapping[str, Any]) -> float | None:
    """Read an optional confidence score in the 0.0–1.0 range."""
    value = body.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(ErrorCode.INVALID_INPUT, "confidence must be a number", ("confidence",))
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ApiError(
            ErrorCode.INVALID_INPUT,
            "confidence must be between 0.0 and 1.0",
            ("confidence",),
        )
    return score


def error_envelope(exc: Exception) -> dict[str, Any]:
    """Translate a domain or validation error into a v4 error envelope."""
    if isinstance(exc, ApiError):
        return fail(exc)
    if isinstance(exc, CaptureNotFoundError):
        return fail(ApiError(ErrorCode.NOT_FOUND, str(exc), (exc.item_id,)))
    if isinstance(exc, TransitionError):
        details = tuple(state.value for state in exc.legal)
        return fail(ApiError(ErrorCode.CONFLICT, str(exc), details))
    if isinstance(exc, (TemplateError, PaginationError, ValueError, TypeError)):
        return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))
    return fail(ApiError(ErrorCode.INTERNAL, "unexpected inbox error"))


def as_api_error(exc: Exception) -> ApiError:
    """Convert any handler exception into a structured v4 API error."""
    payload = error_envelope(exc)
    error = payload["error"]
    assert isinstance(error, dict)
    return ApiError(
        code=ErrorCode(str(error["code"])),
        message=str(error["message"]),
        details=tuple(str(item) for item in error["details"]),
    )


def guard(handler: F) -> F:
    """Translate domain errors into API errors while preserving validation errors."""

    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except ApiError:
            raise
        except Exception as exc:
            raise as_api_error(exc) from exc

    return wrapped  # type: ignore[return-value]


class InboxRoutes:
    """Stateless handlers bound to one service and capability set."""

    def __init__(
        self,
        service: InboxService | None = None,
        capabilities: CapabilitySet | None = None,
        request_id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.service = service or InboxService()
        self.capabilities = capabilities or CapabilitySet.full()
        self.gate = FeatureGate(self.capabilities)
        self.request_id_factory = request_id_factory

    def _meta(
        self,
        headers: Mapping[str, str],
        page: int,
        page_size: int,
        etag: str = "",
        next_cursor: str = "",
    ) -> PageMeta:
        request_id = headers.get("X-Request-ID") or self.request_id_factory()
        return PageMeta(
            request_id=request_id,
            page=page,
            page_size=page_size,
            etag=etag,
            next_cursor=next_cursor,
        )

    def _require(self, capability: Capability) -> None:
        try:
            self.gate.require(FeatureFlag.INBOX)
            self.capabilities.require(capability)
        except PermissionError as exc:
            raise ApiError(ErrorCode.FORBIDDEN, str(exc)) from exc

    @guard
    def list(
        self,
        query: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """List captures with filters, pagination, and a weak ETag."""
        head = headers or {}
        self._require(Capability.READ)
        page = optional_int(query, "page", 1, 1, 10000)
        page_size = optional_int(query, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        state = optional_enum(query, "state", TriageState)
        source = optional_enum(query, "source", CaptureSource)
        tag = optional_str(query, "tag", 80)
        needle = optional_str(query, "query", 240)
        cursor = optional_str(query, "cursor", 500)
        items = self.service.list(state=state, source=source, tag=tag, query=needle)
        if cursor:
            try:
                items = tuple(apply_cursor(items, cursor))
            except PaginationError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc), ("cursor",)) from exc
        if state is not None and not isinstance(state, TriageState):
            raise ApiError(ErrorCode.INVALID_INPUT, "invalid state filter")
        if source is not None and not isinstance(source, CaptureSource):
            raise ApiError(ErrorCode.INVALID_INPUT, "invalid source filter")
        result: PageResult[CaptureItem] = paginate(items, page, page_size)
        data = result.to_dict(serialize=lambda item: item.to_dict())
        data["filters"] = {
            "state": state.value if state is not None else "",
            "source": source.value if source is not None else "",
            "tag": tag or "",
            "query": needle or "",
        }
        fingerprint = "|".join(
            [item.content_hash for item in result.items]
            + [str(data["filters"]), str(page), str(page_size)]
        )
        etag = weak_etag(fingerprint)
        if etag_matches(head.get("If-None-Match", ""), etag):
            data["not_modified"] = True
            data["items"] = []
        meta = self._meta(head, page, page_size, etag, result.next_cursor)
        return ok(data, meta)

    @guard
    def create(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Capture raw text; duplicates return the stored item with created=false."""
        head = headers or {}
        self._require(Capability.WRITE)
        raw = require_str(body, "raw")
        source_value = optional_str(body, "source", 60)
        source: CaptureSource | None = None
        if source_value is not None:
            try:
                source = CaptureSource.parse(source_value)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc), ("source",)) from exc
        result = self.service.capture(
            raw=raw,
            source=source,
            tags=optional_tags(body),
            confidence=optional_confidence(body),
        )
        data = {
            "capture": result.item.to_dict(),
            "created": result.created,
            "duplicate": not result.created,
        }
        meta = self._meta(head, 1, DEFAULT_PAGE_SIZE, weak_etag(result.item.content_hash))
        return ok(data, meta)

    @guard
    def triage(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Move one capture to a legal triage state."""
        head = headers or {}
        self._require(Capability.WRITE)
        item_id = require_str(body, "id")
        previous = self.service.get(item_id)
        state_value = optional_str(body, "state", 60)
        action = optional_str(body, "action", 60)
        if state_value is None and action is None:
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                "either state or action is required",
                ("state", "action"),
            )
        if state_value is not None:
            try:
                target = TriageState.parse(state_value)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc), ("state",)) from exc
        else:
            assert action is not None
            try:
                target = self.service.machine.target_for(action)
            except ValueError as exc:
                raise ApiError(ErrorCode.INVALID_INPUT, str(exc), ("action",)) from exc
        actor = head.get("X-Actor", "local")[:120] or "local"
        updated = self.service.triage(item_id, target, actor)
        data = {
            "capture": updated.to_dict(),
            "from_state": previous.state.value,
            "to_state": updated.state.value,
        }
        meta = self._meta(head, 1, DEFAULT_PAGE_SIZE, weak_etag(updated.content_hash))
        return ok(data, meta)


def register(api: object | None = None) -> tuple[Route, ...]:
    """Register inbox routes on ``api`` (or the global registry), idempotently.

    Namespace discovery may pass an arbitrary shell object that does not expose
    a v4 route registry; in that case the route descriptors are still returned
    but nothing is registered.
    """
    target = api if api is not None else global_registry()
    register_hook = getattr(target, "register", None)
    lookup_hook = getattr(target, "get", None)
    hooks: tuple[Callable[..., Any], Callable[..., Any]] | None = None
    if callable(register_hook) and callable(lookup_hook):
        hooks = (register_hook, lookup_hook)
    registered: list[Route] = []
    for prefix, name in ROUTE_SPECS:
        route = Route(prefix=prefix, name=name)
        if hooks is not None and hooks[1](route.full_path) is None:
            route = hooks[0](prefix, name)
        registered.append(route)
    return tuple(registered)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ROUTE_SPECS",
    "InboxRoutes",
    "as_api_error",
    "error_envelope",
    "guard",
    "optional_confidence",
    "optional_enum",
    "optional_int",
    "optional_str",
    "optional_tags",
    "register",
    "require_str",
]
