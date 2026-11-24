"""Decode and render B00 API v3 envelopes without redefining their contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.envelope import (
    API_VERSION,
    Envelope,
    ErrorDetail,
    PageMeta,
    failure,
    success,
)
from redscribe.v3.api_sdk.models import SdkResponse


def _string(payload: Mapping[str, Any], key: str, *, default: str = "") -> str:
    value = payload.get(key, default)
    return value if isinstance(value, str) else default


def _page(payload: Mapping[str, Any]) -> PageMeta | None:
    raw = payload.get("page")
    if not isinstance(raw, Mapping):
        return None
    try:
        return PageMeta(
            page=int(raw.get("page", 1)),
            page_size=int(raw.get("page_size", 50)),
            total=int(raw.get("total", 0)),
            has_next=raw.get("has_next") is True,
            has_previous=raw.get("has_previous") is True,
        )
    except (TypeError, ValueError):
        return None


def _error(payload: Mapping[str, Any]) -> ErrorDetail | None:
    raw = payload.get("error")
    if not isinstance(raw, Mapping):
        return None
    context = raw.get("context", {})
    return ErrorDetail(
        code=_string(raw, "code", default="sdk_error"),
        message=_string(raw, "message", default="Request failed"),
        field_name=_string(raw, "field"),
        retryable=raw.get("retryable") is True,
        context=dict(context) if isinstance(context, Mapping) else {},
    )


def decode_envelope(
    payload: Mapping[str, Any],
    *,
    namespace: str,
    action: str,
    status: int = 200,
    cached: bool = False,
) -> SdkResponse:
    """Convert a decoded wire envelope into a typed SDK response."""
    meta = payload.get("meta")
    meta = meta if isinstance(meta, Mapping) else {}
    detail = _error(payload)
    error_status = status if status >= 400 else (400 if detail is not None else status)
    return SdkResponse(
        namespace=namespace,
        action=action,
        data=payload.get("data"),
        status=error_status,
        request_id=_string(meta, "request_id"),
        api_version=_string(meta, "api_version", default=API_VERSION),
        etag=_string(meta, "etag"),
        page=_page(meta),
        warnings=tuple(item for item in meta.get("warnings", ()) if isinstance(item, str)),
        error=detail,
        cached=cached,
    )


def render_envelope(response: SdkResponse) -> dict[str, Any]:
    """Render an SDK response using the B00 envelope shapes."""
    if response.error is not None:
        return failure(
            code=response.error.code,
            message=response.error.message,
            status=response.status,
            field=response.error.field_name,
            retryable=response.error.retryable,
            request_id=response.request_id,
            context=response.error.context,
        ).as_dict()
    envelope: Envelope[Any] = success(
        response.data,
        request_id=response.request_id,
        etag=response.etag,
        page=response.page,
    )
    rendered = envelope.as_dict()
    meta = rendered["meta"]
    if response.warnings:
        meta["warnings"] = list(response.warnings)
    return rendered
