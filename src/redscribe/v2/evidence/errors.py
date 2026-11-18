"""Typed errors raised by the evidence vault."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_STATUS = 400


class EvidenceError(Exception):
    """Base error carrying a stable code and optional field details."""

    code = "evidence_error"
    status = DEFAULT_STATUS

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.details: dict[str, Any] = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "status": self.status,
            "details": dict(self.details),
        }


class ValidationError(EvidenceError):
    """The request or stored value failed a validation rule."""

    code = "evidence_validation_error"


class NotFoundError(EvidenceError):
    """A referenced evidence item does not exist."""

    code = "evidence_not_found"
    status = 404


class ConflictError(EvidenceError):
    """A change conflicts with the current vault state."""

    code = "evidence_conflict"
    status = 409


class IngestError(EvidenceError):
    """A file could not be ingested."""

    code = "evidence_ingest_error"


class IntegrityError(EvidenceError):
    """Integrity verification found a blocking problem."""

    code = "evidence_integrity_error"
    status = 422


class ManifestError(EvidenceError):
    """A manifest is malformed or cannot be applied."""

    code = "evidence_manifest_error"


class RepositoryError(EvidenceError):
    """A repository operation failed."""

    code = "evidence_repository_error"
    status = 500


def as_error_dict(error: Exception) -> dict[str, Any]:
    """Normalize any exception into the evidence error shape."""
    if isinstance(error, EvidenceError):
        return error.as_dict()
    return {
        "code": "evidence_internal_error",
        "message": str(error) or error.__class__.__name__,
        "status": 500,
        "details": {},
    }
