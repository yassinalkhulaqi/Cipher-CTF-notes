"""In-process transport that dispatches SDK calls through the B00 router."""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from typing import Any, Protocol

from redscribe.v3.api.envelope import MAX_BODY_BYTES, ErrorDetail, is_envelope, success
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.idempotency import (
    IdempotencyGuard,
    compute_etag,
    etag_matches,
)
from redscribe.v3.api.request_id import normalize_request_id
from redscribe.v3.api.router import V3Router, default_router
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.api_sdk.envelopes import decode_envelope
from redscribe.v3.api_sdk.errors import (
    ReadOnlyViolationError,
    SdkError,
    TransportError,
    from_v3_error,
)
from redscribe.v3.api_sdk.models import SdkRequest, SdkResponse

DEFAULT_WRITE_ACTIONS: tuple[tuple[str, str], ...] = (
    ("extensions", "install"),
    ("extensions", "remove"),
    ("extensions", "reset"),
)


class Transport(Protocol):
    """Transport contract used by the typed SDK client."""

    def call(self, request: SdkRequest) -> SdkResponse:
        """Execute one request and return a typed response."""
        ...


class InProcessTransport:
    """Local-only transport: no sockets, no subprocesses, no dynamic code."""

    def __init__(
        self,
        router: V3Router | None = None,
        negotiator: CapabilityNegotiator | None = None,
        guard: IdempotencyGuard | None = None,
        *,
        write_actions: tuple[tuple[str, str], ...] = DEFAULT_WRITE_ACTIONS,
        allow_write: bool = False,
    ) -> None:
        self.router: V3Router = router if router is not None else default_router()
        self.negotiator = negotiator or CapabilityNegotiator()
        self.guard = guard or IdempotencyGuard()
        self._write_actions = frozenset(write_actions)
        self._allow_write = allow_write

    @property
    def allow_write(self) -> bool:
        """Return whether this transport permits write actions."""
        return self._allow_write

    def call(self, request: SdkRequest) -> SdkResponse:
        """Validate, authorize, dispatch, and decode a single call."""
        try:
            request_id = normalize_request_id(request.header("X-Request-ID"))
        except V3Error as error:
            return self._error_response(request, from_v3_error(error))
        try:
            self._validate(request)
            capability = request.capability or request.header("X-Capability")
            if capability:
                self.negotiator.require(capability, required_for=request.route)
            self._check_write(request)
            result, cached = self._dispatch(request, request_id)
        except V3Error as error:
            return self._error_response(request, from_v3_error(error, request_id))
        except SdkError as error:
            if not error.request_id:
                error.request_id = request_id
            return self._error_response(request, error)
        return self._success_response(request, request_id, result, cached)

    def _validate(self, request: SdkRequest) -> None:
        try:
            encoded = json.dumps(request.body, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError) as error:
            raise V3Error(
                V3ErrorCode.INVALID_JSON, "Request body must be JSON-serializable"
            ) from error
        if len(encoded.encode("utf-8")) > MAX_BODY_BYTES:
            raise V3Error(V3ErrorCode.PAYLOAD_TOO_LARGE, "Request body exceeds the size limit")
        for key, value in request.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise V3Error(V3ErrorCode.INVALID_TYPE, "Headers must be string to string")

    def _check_write(self, request: SdkRequest) -> None:
        if (request.namespace, request.action) in self._write_actions and not self._allow_write:
            raise ReadOnlyViolationError(
                f"Write route is read-only by default: {request.route}",
                field="allow_write",
            )

    def _dispatch(self, request: SdkRequest, request_id: str) -> tuple[dict[str, Any], bool]:
        headers: MutableMapping[str, str] = dict(request.headers)
        headers.setdefault("X-Request-ID", request_id)
        if request.capability:
            headers.setdefault("X-Capability", request.capability)
        if request.etag:
            headers.setdefault("If-None-Match", request.etag)
        if request.idempotency_key:
            headers.setdefault("Idempotency-Key", request.idempotency_key)

        fingerprint = {
            "namespace": request.namespace,
            "action": request.action,
            "body": request.body,
        }

        def operation() -> dict[str, Any]:
            return self.router.dispatch(
                request.namespace,
                request.action,
                dict(request.body),
                dict(headers),
            )

        if request.idempotency_key:
            result, cached = self.guard.execute(request.idempotency_key, fingerprint, operation)
            return result, cached
        return operation(), False

    def _success_response(
        self,
        request: SdkRequest,
        request_id: str,
        result: dict[str, Any],
        cached: bool,
    ) -> SdkResponse:
        wrapped: Mapping[str, Any]
        if is_envelope(result):
            wrapped = result
        else:
            wrapped = success(result, request_id=request_id).as_dict()
        response = decode_envelope(
            wrapped,
            namespace=request.namespace,
            action=request.action,
            cached=cached,
        )
        if response.error is not None:
            return response
        etag = response.etag or compute_etag(response.data)
        if request.etag and etag_matches(request.etag, etag):
            return replace(response, status=304, data=None, etag=etag)
        return replace(response, etag=etag)

    def _error_response(self, request: SdkRequest, error: SdkError) -> SdkResponse:
        detail = ErrorDetail(
            code=error.code,
            message=error.message,
            field_name=error.field,
            retryable=error.retryable,
            context=error.context,
        )
        return SdkResponse(
            namespace=request.namespace,
            action=request.action,
            status=error.status,
            request_id=error.request_id,
            error=detail,
        )

    def describe(self) -> dict[str, Any]:
        """Return a description of this transport for diagnostics."""
        return {
            "kind": "in_process",
            "allow_write": self._allow_write,
            "write_actions": [f"{ns}.{action}" for ns, action in sorted(self._write_actions)],
            "route_count": self.router.size(),
            "capabilities": self.negotiator.as_dict(),
        }


def require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    """Read a mapping payload, rejecting other shapes."""
    if not isinstance(value, Mapping):
        raise TransportError(f"'{field_name}' must be a mapping", field=field_name)
    return dict(value)
