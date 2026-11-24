"""Stable machine-readable error codes for the V3 API."""

from __future__ import annotations

from enum import Enum

from redscribe.v3.api.envelope import ErrorEnvelope, failure


class V3ErrorCode(str, Enum):
    """Categories used by every V3 endpoint."""

    UNKNOWN_ROUTE = "unknown_route"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    INVALID_JSON = "invalid_json"
    INVALID_TYPE = "invalid_type"
    MISSING_FIELD = "missing_field"
    INVALID_CHOICE = "invalid_choice"
    FIELD_TOO_LONG = "field_too_long"
    INVALID_CURSOR = "invalid_cursor"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CONFLICT = "conflict"
    PRECONDITION_FAILED = "precondition_failed"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    INTERNAL = "internal"


_STATUS_BY_CODE: dict[V3ErrorCode, int] = {
    V3ErrorCode.UNKNOWN_ROUTE: 404,
    V3ErrorCode.NOT_FOUND: 404,
    V3ErrorCode.INVALID_REQUEST: 400,
    V3ErrorCode.INVALID_JSON: 400,
    V3ErrorCode.INVALID_TYPE: 400,
    V3ErrorCode.MISSING_FIELD: 400,
    V3ErrorCode.INVALID_CHOICE: 400,
    V3ErrorCode.FIELD_TOO_LONG: 400,
    V3ErrorCode.INVALID_CURSOR: 400,
    V3ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    V3ErrorCode.PAYLOAD_TOO_LARGE: 413,
    V3ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    V3ErrorCode.CONFLICT: 409,
    V3ErrorCode.PRECONDITION_FAILED: 412,
    V3ErrorCode.RATE_LIMITED: 429,
    V3ErrorCode.FORBIDDEN: 403,
    V3ErrorCode.INTERNAL: 500,
}


class V3Error(Exception):
    """An exception that renders as a stable V3 error envelope."""

    def __init__(
        self,
        code: V3ErrorCode,
        message: str,
        *,
        field: str = "",
        status: int | None = None,
        retryable: bool = False,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.status = status if status is not None else _STATUS_BY_CODE[code]
        self.retryable = retryable
        self.context = dict(context or {})

    def envelope(self, request_id: str = "") -> ErrorEnvelope:
        """Render the error as a V3 envelope."""
        return failure(
            code=self.code.value,
            message=self.message,
            status=self.status,
            field=self.field,
            retryable=self.retryable,
            request_id=request_id,
            context=self.context,
        )

    @classmethod
    def not_found(cls, resource: str) -> V3Error:
        """Build a not-found error."""
        return cls(V3ErrorCode.NOT_FOUND, f"Unknown {resource}")

    @classmethod
    def missing(cls, field_name: str) -> V3Error:
        """Build a missing-field error."""
        return cls(
            V3ErrorCode.MISSING_FIELD,
            f"Missing required field '{field_name}'",
            field=field_name,
        )

    @classmethod
    def invalid(cls, field_name: str, reason: str) -> V3Error:
        """Build an invalid-request error."""
        return cls(
            V3ErrorCode.INVALID_REQUEST,
            f"Invalid '{field_name}': {reason}",
            field=field_name,
        )


def status_for(code: V3ErrorCode) -> int:
    """Return the default HTTP status for an error code."""
    return _STATUS_BY_CODE[code]


def all_codes() -> tuple[str, ...]:
    """Return every error code in stable order."""
    return tuple(code.value for code in sorted(V3ErrorCode, key=lambda item: item.value))
