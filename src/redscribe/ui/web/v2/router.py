"""Dispatch, idempotency, auditing, and envelopes for API v2."""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.v2 import storage_bridge as storage
from redscribe.ui.web.v2.contracts import (
    Envelope,
    V2Error,
    V2ErrorCode,
    envelope,
    error_envelope,
)
from redscribe.ui.web.v2.routes import ApiV2, Route, RouteResult

LOGGER = logging.getLogger(__name__)


def _replay_envelope(record: storage.IdempotencyRecord) -> Envelope:
    stored = record.response
    payload: dict[str, Any] = {}
    for key in ("ok", "data", "error", "meta"):
        if key in stored:
            payload[key] = stored[key]
    for key, value in stored.items():
        if key not in payload:
            payload[key] = value
    meta = payload.get("meta")
    etag = meta.get("etag") if isinstance(meta, dict) else None
    return Envelope(
        payload,
        status=record.status,
        etag=etag if isinstance(etag, str) else None,
    )


class V2Router:
    """Route ``namespace.action`` calls through the v2 contract layer."""

    def __init__(self, vault: Vault, api: ApiV2 | None = None) -> None:
        self._vault = vault
        self._api = api if api is not None else ApiV2(vault)
        self._local_idempotency: dict[str, storage.IdempotencyRecord] = {}

    @property
    def api(self) -> ApiV2:
        return self._api

    def dispatch(
        self,
        method: str,
        body: dict[str, Any],
        *,
        request_id: str = "",
        idempotency_key: str | None = None,
    ) -> Envelope:
        """Dispatch one route and always return a v2 envelope."""
        if not request_id:
            request_id = f"req_{secrets.token_urlsafe(16)}"
        route_name = method[3:] if method.startswith("v2:") else method
        started = time.monotonic()
        route: Route | None = None
        try:
            if not route_name or "." not in route_name:
                raise V2Error(
                    404,
                    V2ErrorCode.UNKNOWN_ROUTE,
                    f"Unknown API v2 route '{route_name}'",
                    details={"route": route_name},
                )
            if not isinstance(body, dict):
                raise V2Error(
                    400,
                    V2ErrorCode.INVALID_REQUEST,
                    "JSON body must be an object",
                )
            route = self._api.route(route_name)
            request_digest: str | None = None
            if route.mutating and idempotency_key:
                request_digest = storage.request_hash(route.name, body)
                replay = self._load_replay(idempotency_key)
                if replay is not None:
                    if replay.method != route.name or replay.request_hash != request_digest:
                        raise V2Error(
                            409,
                            V2ErrorCode.IDEMPOTENCY_CONFLICT,
                            "Idempotency-Key was already used for a different request",
                            details={"key": idempotency_key},
                        )
                    self._audit(
                        request_id=request_id,
                        route=route.name,
                        status=replay.status,
                        ok=True,
                        code=None,
                        started=started,
                    )
                    return _replay_envelope(replay)

            result = self._api.invoke(route.name, body)
            response = envelope(
                result.data,
                request_id=request_id,
                page=result.page,
                etag=result.etag,
            )
            response.status = result.status
            if route.mutating:
                self._save_replay(
                    idempotency_key,
                    route=route.name,
                    request_digest=request_digest or storage.request_hash(route.name, body),
                    response=response,
                )
                self._record_mutation(route, result, request_id)
            self._audit(
                request_id=request_id,
                route=route.name,
                status=response.status,
                ok=True,
                code=None,
                started=started,
            )
            return response
        except V2Error as exc:
            self._audit(
                request_id=request_id,
                route=route.name if route is not None else route_name,
                status=exc.status,
                ok=False,
                code=exc.code,
                started=started,
            )
            return error_envelope(exc, request_id=request_id)
        except (ValueError, TypeError) as exc:
            failure = V2Error(
                400,
                V2ErrorCode.INVALID_REQUEST,
                str(exc) or "Invalid request",
            )
            self._audit(
                request_id=request_id,
                route=route.name if route is not None else route_name,
                status=failure.status,
                ok=False,
                code=failure.code,
                started=started,
            )
            return error_envelope(failure, request_id=request_id)
        except Exception:
            LOGGER.exception("API v2 route %s failed", route_name)
            failure = V2Error(
                500,
                V2ErrorCode.INTERNAL,
                "Internal server error",
                retryable=True,
            )
            self._audit(
                request_id=request_id,
                route=route.name if route is not None else route_name,
                status=failure.status,
                ok=False,
                code=failure.code,
                started=started,
            )
            return error_envelope(failure, request_id=request_id)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def _connection(self) -> object:
        return getattr(self._vault, "connection", self._vault)

    def _load_replay(self, key: str) -> storage.IdempotencyRecord | None:
        record = storage.load_idempotency(self._connection(), key)
        if record is not None:
            return record
        return self._local_idempotency.get(key)

    def _save_replay(
        self,
        key: str | None,
        *,
        route: str,
        request_digest: str,
        response: Envelope,
    ) -> None:
        if not key:
            return
        record = storage.IdempotencyRecord(
            method=route,
            request_hash=request_digest,
            status=response.status,
            response=dict(response),
        )
        self._local_idempotency[key] = record
        storage.save_idempotency(
            self._connection(),
            key,
            method=route,
            request_hash_value=request_digest,
            status=response.status,
            response=dict(response),
        )
        storage.prune_idempotency(self._connection())

    # ------------------------------------------------------------------
    # Events and audit (best effort)
    # ------------------------------------------------------------------

    def _record_mutation(self, route: Route, result: RouteResult, request_id: str) -> None:
        entity_id: object = None
        if isinstance(result.data, dict):
            entity_id = result.data.get("id")
        entity_type = route.entity_type or route.name.split(".", 1)[0]
        payload: dict[str, Any] = {}
        if isinstance(result.data, dict):
            payload = {
                key: result.data[key]
                for key in ("id", "title", "kind", "status", "target")
                if key in result.data
            }
        try:
            storage.record_event(
                self._vault,
                route=route.name,
                action=route.name.split(".")[-1],
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                request_id=request_id,
            )
        except Exception:  # pragma: no cover - guarded by storage_bridge as well
            LOGGER.debug("Entity event recording failed", exc_info=True)

    def _audit(
        self,
        *,
        request_id: str,
        route: str,
        status: int,
        ok: bool,
        code: str | None,
        started: float,
    ) -> None:
        duration_ms = round((time.monotonic() - started) * 1000.0, 3)
        try:
            storage.record_request_audit(
                self._vault,
                request_id=request_id,
                route=route,
                status=status,
                ok=ok,
                code=code,
                duration_ms=duration_ms,
            )
        except Exception:  # pragma: no cover - guarded by storage_bridge as well
            LOGGER.debug("Request audit recording failed", exc_info=True)
