"""Best-effort adapters for optional v2 storage modules.

Storage is owned by a parallel change. The API v2 layer must remain importable
and testable before those modules exist, so this bridge resolves them at import
time through :mod:`importlib` and silently falls back to in-memory behavior when
they are unavailable.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any, cast

LOGGER = logging.getLogger(__name__)


def _load(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


_IDEMPOTENCY = _load("redscribe.storage.idempotency")
_EVENTS = _load("redscribe.storage.events")


def _function(module: ModuleType | None, name: str) -> Callable[..., Any] | None:
    if module is None:
        return None
    value = getattr(module, name, None)
    return cast(Callable[..., Any], value) if callable(value) else None


def _invoke(
    function: Callable[..., Any],
    positional: list[Any],
    candidates: Mapping[str, Any],
) -> Any:
    """Call ``function`` with only the keyword names it actually accepts."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return function(*positional)

    parameters = signature.parameters
    kwargs: dict[str, Any] = {}
    if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
        kwargs = dict(candidates)
    else:
        for name, param in parameters.items():
            if (
                param.kind
                in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
                and name in candidates
            ):
                kwargs[name] = candidates[name]
    return function(*positional, **kwargs)


def request_hash(method: str, body: object) -> str:
    """Hash a request using the storage helper when available."""
    function = _function(_IDEMPOTENCY, "hash_request")
    if function is not None:
        try:
            return str(function(method, body))
        except Exception:  # pragma: no cover - defensive around optional storage
            LOGGER.debug("Storage hash_request failed; using local hash", exc_info=True)
    raw = json.dumps(
        {"method": method, "body": body},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Normalized view of one stored idempotent response."""

    method: str
    request_hash: str
    status: int
    response: dict[str, Any]


def _record_value(record: object, *names: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        for name in names:
            if name in record:
                return record[name]
    for name in names:
        if hasattr(record, name):
            return getattr(record, name)
    return default


def load_idempotency(connection: object, key: str) -> IdempotencyRecord | None:
    """Load and normalize one idempotency record, if storage provides it."""
    function = _function(_IDEMPOTENCY, "get_record")
    if function is None:
        return None
    try:
        record = function(connection, key)
    except Exception:  # pragma: no cover - defensive around optional storage
        LOGGER.debug("Storage get_record failed", exc_info=True)
        return None
    if record is None:
        return None

    response = _record_value(record, "response", "body", "payload")
    if isinstance(response, (str, bytes)):
        try:
            response = json.loads(response)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    if not isinstance(response, dict):
        return None

    method = str(_record_value(record, "method", "route", default=""))
    request_digest = str(_record_value(record, "request_hash", "hash", default=""))
    raw_status = _record_value(record, "status", "status_code", default=200)
    status = raw_status if isinstance(raw_status, int) and not isinstance(raw_status, bool) else 200
    return IdempotencyRecord(
        method=method,
        request_hash=request_digest,
        status=status,
        response=dict(response),
    )


def save_idempotency(
    connection: object,
    key: str,
    *,
    method: str,
    request_hash_value: str,
    status: int,
    response: Mapping[str, Any],
) -> bool:
    """Persist one idempotent response, returning whether storage accepted it."""
    function = _function(_IDEMPOTENCY, "put_record")
    if function is None:
        return False
    try:
        function(
            connection,
            key=key,
            method=method,
            request_hash=request_hash_value,
            status=status,
            response=dict(response),
        )
        return True
    except Exception:  # pragma: no cover - defensive around optional storage
        LOGGER.debug("Storage put_record failed", exc_info=True)
        return False


def prune_idempotency(connection: object) -> None:
    """Prune expired idempotency rows when storage supports it."""
    function = _function(_IDEMPOTENCY, "prune_expired")
    if function is None:
        return
    try:
        function(connection)
    except Exception:  # pragma: no cover - defensive around optional storage
        LOGGER.debug("Storage prune_expired failed", exc_info=True)


def _event_dict(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        result = as_dict()
        if isinstance(result, Mapping):
            return {str(key): item for key, item in result.items()}
    keys = getattr(value, "keys", None)
    if callable(keys):
        try:
            return {str(key): value[key] for key in keys()}  # type: ignore[index]
        except (TypeError, KeyError, IndexError):
            pass
    return {"value": value}


def record_event(
    vault: object,
    *,
    route: str,
    action: str,
    entity_type: str,
    entity_id: object,
    payload: Mapping[str, Any],
    request_id: str,
) -> None:
    """Record one entity event, ignoring any storage failure."""
    function = _function(_EVENTS, "record_event")
    if function is None:
        fallback = getattr(vault, "record_event", None)
        function = cast(Callable[..., Any], fallback) if callable(fallback) else None
    if function is None:
        return
    connection = getattr(vault, "connection", vault)
    candidates: dict[str, Any] = {
        "event_type": route,
        "type": route,
        "kind": route,
        "action": action,
        "verb": action,
        "entity_type": entity_type,
        "entity": entity_type,
        "entity_id": entity_id,
        "aggregate_type": entity_type,
        "aggregate_id": entity_id,
        "payload": dict(payload),
        "data": dict(payload),
        "details": dict(payload),
        "metadata": dict(payload),
        "request_id": request_id,
        "actor": "api",
        "source": "api",
        "route": route,
        "method": route,
    }
    try:
        _invoke(function, [connection], candidates)
    except Exception:  # pragma: no cover - best-effort audit path
        LOGGER.debug("Storage record_event failed", exc_info=True)


def list_events(
    vault: object,
    *,
    since_id: int,
    limit: int,
    entity_type: str | None = None,
    entity_id: object = None,
) -> list[dict[str, Any]]:
    """Return normalized entity events from storage, or an empty list."""
    function = _function(_EVENTS, "list_events")
    if function is None:
        fallback = getattr(vault, "list_events", None)
        function = cast(Callable[..., Any], fallback) if callable(fallback) else None
    if function is None:
        return []
    connection = getattr(vault, "connection", vault)
    candidates: dict[str, Any] = {
        "since_id": since_id,
        "after_id": since_id,
        "limit": limit,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }
    try:
        result = _invoke(function, [connection], candidates)
    except Exception:  # pragma: no cover - defensive around optional storage
        LOGGER.debug("Storage list_events failed", exc_info=True)
        return []
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, (list, tuple)):
        return []
    return [_event_dict(item) for item in result]


def record_request_audit(
    vault: object,
    *,
    request_id: str,
    route: str,
    status: int,
    ok: bool,
    code: str | None,
    duration_ms: float,
) -> None:
    """Record one request audit row, ignoring any storage failure."""
    function = _function(_EVENTS, "record_request_audit")
    if function is None:
        fallback = getattr(vault, "record_request_audit", None)
        function = cast(Callable[..., Any], fallback) if callable(fallback) else None
    if function is None:
        return
    connection = getattr(vault, "connection", vault)
    candidates: dict[str, Any] = {
        "request_id": request_id,
        "route": route,
        "method": route,
        "path": route,
        "status": status,
        "status_code": status,
        "ok": ok,
        "success": ok,
        "code": code,
        "error_code": code,
        "duration_ms": duration_ms,
        "duration": duration_ms,
    }
    try:
        _invoke(function, [connection], candidates)
    except Exception:  # pragma: no cover - best-effort audit path
        LOGGER.debug("Storage record_request_audit failed", exc_info=True)


def list_request_audit(vault: object, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return normalized request audit rows from storage, or an empty list."""
    function = _function(_EVENTS, "list_request_audit")
    if function is None:
        fallback = getattr(vault, "list_request_audit", None)
        function = cast(Callable[..., Any], fallback) if callable(fallback) else None
    if function is None:
        return []
    connection = getattr(vault, "connection", vault)
    try:
        result = _invoke(function, [connection], {"limit": limit})
    except Exception:  # pragma: no cover - defensive around optional storage
        LOGGER.debug("Storage list_request_audit failed", exc_info=True)
        return []
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, (list, tuple)):
        return []
    return [_event_dict(item) for item in result]
