"""Domain errors for the playbooks V2 feature."""

from __future__ import annotations

from enum import Enum
from typing import Any

from redscribe.v2.playbooks.types import Issue


class PlaybookErrorCode(str, Enum):
    """Stable error codes mapped to the v2 API error envelope."""

    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    DUPLICATE_KEY = "duplicate_key"
    INVALID_STATE = "invalid_state"
    CYCLE_DETECTED = "cycle_detected"
    MISSING_VARIABLE = "missing_variable"
    UNKNOWN_STEP = "unknown_step"
    UNKNOWN_SNIPPET = "unknown_snippet"
    UNKNOWN_TEMPLATE = "unknown_template"
    IMPORT_FAILED = "import_failed"
    VERSION_CONFLICT = "version_conflict"
    EXPRESSION_ERROR = "expression_error"
    INTERPOLATION_ERROR = "interpolation_error"
    REPOSITORY_ERROR = "repository_error"


class PlaybookError(Exception):
    """Base error carrying a stable code and structured details."""

    code = PlaybookErrorCode.VALIDATION_FAILED
    status = 400

    def __init__(
        self,
        message: str,
        *,
        code: PlaybookErrorCode | None = None,
        status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or type(self).code
        self.status = status if status is not None else type(self).status
        self.details: dict[str, Any] = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "status": self.status,
            "details": dict(self.details),
        }


class ValidationError(PlaybookError):
    """Raised when an entity fails structural validation."""

    code = PlaybookErrorCode.VALIDATION_FAILED

    def __init__(self, message: str, issues: tuple[Issue, ...] = (), **kwargs: Any) -> None:
        details = dict(kwargs.pop("details", {}))
        details["issues"] = [issue.as_dict() for issue in issues]
        super().__init__(message, details=details, **kwargs)
        self.issues = issues


class NotFoundError(PlaybookError):
    """Raised when a requested entity key or id does not exist."""

    code = PlaybookErrorCode.NOT_FOUND
    status = 404


class DuplicateKeyError(PlaybookError):
    """Raised when a unique key is already present in a repository."""

    code = PlaybookErrorCode.DUPLICATE_KEY
    status = 409


class InvalidStateError(PlaybookError):
    """Raised when a lifecycle transition is not permitted."""

    code = PlaybookErrorCode.INVALID_STATE
    status = 409


class CycleDetectedError(PlaybookError):
    """Raised when step dependencies contain a cycle."""

    code = PlaybookErrorCode.CYCLE_DETECTED


class MissingVariableError(PlaybookError):
    """Raised when a required variable has no value."""

    code = PlaybookErrorCode.MISSING_VARIABLE

    def __init__(self, *keys: str, **kwargs: Any) -> None:
        details = dict(kwargs.pop("details", {}))
        details["keys"] = list(keys)
        super().__init__(
            f"Missing required variables: {', '.join(keys)}", details=details, **kwargs
        )
        self.keys = keys


class UnknownStepError(NotFoundError):
    """Raised when a step id is absent from a playbook."""

    code = PlaybookErrorCode.UNKNOWN_STEP


class UnknownSnippetError(NotFoundError):
    """Raised when a snippet key is absent from every library."""

    code = PlaybookErrorCode.UNKNOWN_SNIPPET


class UnknownTemplateError(NotFoundError):
    """Raised when a template key is unknown."""

    code = PlaybookErrorCode.UNKNOWN_TEMPLATE


class BundleError(PlaybookError):
    """Raised when an import payload is malformed or incompatible."""

    code = PlaybookErrorCode.IMPORT_FAILED


class VersionConflictError(PlaybookError):
    """Raised when a version constraint cannot be satisfied."""

    code = PlaybookErrorCode.VERSION_CONFLICT
    status = 409


class ExpressionError(PlaybookError):
    """Raised when a conditional expression cannot be parsed or evaluated."""

    code = PlaybookErrorCode.EXPRESSION_ERROR


class InterpolationError(PlaybookError):
    """Raised when a template expression is invalid."""

    code = PlaybookErrorCode.INTERPOLATION_ERROR


class RepositoryError(PlaybookError):
    """Raised for repository-level failures that are not validation errors."""

    code = PlaybookErrorCode.REPOSITORY_ERROR
