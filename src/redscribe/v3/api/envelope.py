"""Stable success and error envelopes for the V3 API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

API_VERSION = "3.0"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_REQUEST_ID_LENGTH = 128

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Pagination metadata attached to list responses."""

    page: int = 1
    page_size: int = 50
    total: int = 0
    has_next: bool = False
    has_previous: bool = False

    def __post_init__(self) -> None:
        if self.page < 1 or self.page_size < 1:
            raise ValueError("Page and page_size must be positive")
        if self.total < 0:
            raise ValueError("Total cannot be negative")

    @classmethod
    def for_window(cls, offset: int, size: int, total: int) -> PageMeta:
        """Build metadata from a slice window."""
        page = offset // size + 1 if size else 1
        return cls(
            page=page,
            page_size=size,
            total=total,
            has_next=offset + size < total,
            has_previous=offset > 0,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
        }


@dataclass(frozen=True, slots=True)
class ResponseMeta:
    """Common response metadata."""

    request_id: str = ""
    api_version: str = API_VERSION
    etag: str = ""
    page: PageMeta | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "api_version": self.api_version,
        }
        if self.etag:
            payload["etag"] = self.etag
        if self.page is not None:
            payload["page"] = self.page.as_dict()
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True, slots=True)
class Envelope(Generic[T]):
    """One consistent success envelope for every V3 endpoint."""

    data: T
    meta: ResponseMeta = field(default_factory=ResponseMeta)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        rendered: Any = self.data
        if hasattr(rendered, "as_dict"):
            rendered = rendered.as_dict()
        elif isinstance(rendered, (list, tuple)):
            rendered = [item.as_dict() if hasattr(item, "as_dict") else item for item in rendered]
        return {"data": rendered, "meta": self.meta.as_dict()}


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """Structured detail attached to an error response."""

    code: str
    message: str
    field_name: str = ""
    retryable: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field_name,
            "retryable": self.retryable,
            "context": dict(self.context),
        }


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    """One consistent error envelope for every V3 endpoint."""

    error: ErrorDetail
    meta: ResponseMeta = field(default_factory=ResponseMeta)
    status: int = 400

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"error": self.error.as_dict(), "meta": self.meta.as_dict()}


def success(
    data: T,
    *,
    request_id: str = "",
    etag: str = "",
    page: PageMeta | None = None,
) -> Envelope[T]:
    """Build a success envelope."""
    return Envelope(data=data, meta=ResponseMeta(request_id=request_id, etag=etag, page=page))


def failure(
    code: str,
    message: str,
    *,
    status: int = 400,
    field: str = "",
    retryable: bool = False,
    request_id: str = "",
    context: dict[str, Any] | None = None,
) -> ErrorEnvelope:
    """Build an error envelope."""
    detail = ErrorDetail(
        code=code,
        message=message,
        field_name=field,
        retryable=retryable,
        context=dict(context or {}),
    )
    return ErrorEnvelope(
        error=detail,
        meta=ResponseMeta(request_id=request_id),
        status=status,
    )


def is_envelope(payload: Any) -> bool:
    """Return whether a decoded JSON value has the V3 success shape."""
    return (
        isinstance(payload, dict)
        and "data" in payload
        and "meta" in payload
        and isinstance(payload["meta"], dict)
    )


def unwrap(payload: dict[str, Any]) -> Any:
    """Return the data portion of a success envelope."""
    if not is_envelope(payload):
        raise ValueError("Payload is not a V3 envelope")
    return payload["data"]
