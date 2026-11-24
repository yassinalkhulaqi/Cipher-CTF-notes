"""Typed value objects for the local SDK. Envelope contracts come from B00."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from redscribe.v3.api.envelope import API_VERSION, ErrorDetail, PageMeta
from redscribe.v3.api.errors import V3Error, V3ErrorCode

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
T = TypeVar("T")


def require_name(value: object, field_name: str) -> str:
    """Validate a namespace or action token."""
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value):
        raise V3Error(
            V3ErrorCode.INVALID_REQUEST,
            f"'{field_name}' must be a lowercase token of 2-64 characters",
            field=field_name,
        )
    return value


def coerce_body(body: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy a request body into a plain JSON-safe mapping."""
    if body is None:
        return {}
    if not isinstance(body, Mapping):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "Request body must be a mapping", field="body")
    return dict(body)


@dataclass(frozen=True, slots=True)
class SdkRequest:
    """One fully described SDK call."""

    namespace: str
    action: str
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    capability: str = ""
    etag: str = ""
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        require_name(self.namespace, "namespace")
        require_name(self.action, "action")

    @property
    def route(self) -> str:
        """Canonical route path."""
        return f"/api/v3/{self.namespace}/{self.action}"

    def header(self, name: str) -> str:
        """Return a header value case-insensitively."""
        target = name.casefold()
        for key, value in self.headers.items():
            if key.casefold() == target:
                return value
        return ""

    def with_page(self, offset: int, size: int, *, cursor: str = "") -> SdkRequest:
        """Return a copy carrying pagination inputs."""
        body = dict(self.body)
        body.pop("cursor", None)
        body.pop("offset", None)
        body.pop("size", None)
        if cursor:
            body["cursor"] = cursor
        else:
            body["offset"] = offset
            body["size"] = size
        return SdkRequest(
            namespace=self.namespace,
            action=self.action,
            body=body,
            headers=dict(self.headers),
            capability=self.capability,
            etag=self.etag,
            idempotency_key=self.idempotency_key,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "namespace": self.namespace,
            "action": self.action,
            "body": dict(self.body),
            "headers": dict(self.headers),
            "capability": self.capability,
            "etag": self.etag,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True, slots=True)
class SdkResponse:
    """Typed result of an SDK call, success or failure."""

    namespace: str
    action: str
    data: Any = None
    status: int = 200
    request_id: str = ""
    api_version: str = API_VERSION
    etag: str = ""
    page: PageMeta | None = None
    warnings: tuple[str, ...] = ()
    error: ErrorDetail | None = None
    cached: bool = False

    @property
    def ok(self) -> bool:
        """Return whether the call succeeded or was a conditional miss."""
        return self.error is None and self.status < 400

    @property
    def not_modified(self) -> bool:
        """Return whether the conditional request matched the ETag."""
        return self.status == 304

    @property
    def code(self) -> str:
        """Return the stable error code, if any."""
        return self.error.code if self.error is not None else ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload: dict[str, Any] = {
            "namespace": self.namespace,
            "action": self.action,
            "status": self.status,
            "request_id": self.request_id,
            "api_version": self.api_version,
            "data": self.data,
            "etag": self.etag,
            "warnings": list(self.warnings),
            "cached": self.cached,
        }
        if self.page is not None:
            payload["page"] = self.page.as_dict()
        if self.error is not None:
            payload["error"] = self.error.as_dict()
        return payload


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """One page of a typed list response."""

    items: tuple[T, ...]
    page: PageMeta | None = None
    next_cursor: str = ""
    etag: str = ""
    request_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "items": list(self.items),
            "page": self.page.as_dict() if self.page is not None else None,
            "next_cursor": self.next_cursor,
            "etag": self.etag,
            "request_id": self.request_id,
        }
