"""SDK-side errors mapped onto the stable B00 V3 error codes."""

from __future__ import annotations

from redscribe.v3.api.envelope import ErrorEnvelope, failure
from redscribe.v3.api.errors import V3Error
from redscribe.v3.api_sdk.models import SdkResponse

FORBIDDEN_CODE = "forbidden"
READ_ONLY_CODE = "read_only_violation"
SAFETY_CODE = "unsafe_manifest"


class SdkError(Exception):
    """Base class for errors raised by the local SDK."""

    code: str = "sdk_error"
    status: int = 400
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        field: str = "",
        retryable: bool | None = None,
        request_id: str = "",
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else type(self).code
        self.status = status if status is not None else type(self).status
        self.field = field
        self.retryable = retryable if retryable is not None else type(self).retryable
        self.request_id = request_id
        self.context = dict(context or {})

    @classmethod
    def from_response(cls, response: SdkResponse) -> SdkError:
        """Build the matching SDK error from a failed response."""
        detail = response.error
        message = detail.message if detail is not None else "API call failed"
        code = detail.code if detail is not None else "sdk_error"
        field = detail.field_name if detail is not None else ""
        retryable = detail.retryable if detail is not None else False
        context = dict(detail.context) if detail is not None else {}
        constructors: dict[str, type[SdkError]] = {
            FORBIDDEN_CODE: CapabilityDeniedError,
            READ_ONLY_CODE: ReadOnlyViolationError,
            SAFETY_CODE: SafetyViolationError,
        }
        constructor = constructors.get(code, SdkError)
        if response.status == 304:
            constructor = NotModifiedError
        return constructor(
            message,
            code=code,
            status=response.status,
            field=field,
            retryable=retryable,
            request_id=response.request_id,
            context=context,
        )

    def as_dict(self) -> dict[str, object]:
        """Return a compact, log-safe description."""
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "status": self.status,
            "retryable": self.retryable,
            "request_id": self.request_id,
        }

    def envelope(self) -> ErrorEnvelope:
        """Render the error with the B00 error envelope."""
        return failure(
            code=self.code,
            message=self.message,
            status=self.status,
            field=self.field,
            retryable=self.retryable,
            request_id=self.request_id,
            context=self.context,
        )


class TransportError(SdkError):
    """The in-process transport rejected a request."""

    code = "transport_error"
    status = 400


class CapabilityDeniedError(SdkError):
    """A required capability was not negotiated."""

    code = FORBIDDEN_CODE
    status = 403


class ReadOnlyViolationError(SdkError):
    """A write was attempted without an explicit opt-in."""

    code = READ_ONLY_CODE
    status = 403


class SafetyViolationError(SdkError):
    """A manifest or source tree failed the data-only invariant."""

    code = SAFETY_CODE
    status = 403


class ManifestError(SdkError):
    """A manifest document failed schema validation."""

    code = "invalid_manifest"
    status = 400


class ScriptError(SdkError):
    """A script plan failed validation or execution."""

    code = "invalid_script"
    status = 400


class NotModifiedError(SdkError):
    """The caller supplied a matching ETag."""

    code = "not_modified"
    status = 304


def from_v3_error(error: V3Error, request_id: str = "") -> SdkError:
    """Translate a B00 V3 error into an SDK error."""
    return SdkError(
        error.message,
        code=error.code.value,
        status=error.status,
        field=error.field,
        retryable=error.retryable,
        request_id=request_id,
        context=error.context,
    )
