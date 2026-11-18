"""Errors for sync and portability operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SyncError(Exception):
    """Base error with machine-readable metadata for v2 API mapping."""

    message: str
    code: str = "sync_error"
    status: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload


class ValidationError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="validation_error", status=400, details=details or {})


class NotFoundError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="not_found", status=404, details=details or {})


class ConflictError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="conflict", status=409, details=details or {})


class ChecksumError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="checksum_mismatch", status=409, details=details or {})


class MigrationCompatibilityError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="migration_incompatible",
            status=409,
            details=details or {},
        )


class UnsupportedFormatError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="unsupported_format",
            status=400,
            details=details or {},
        )


class DryRunAbortedError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="dry_run", status=200, details=details or {})


class ProgressError(SyncError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="progress_error", status=400, details=details or {})
