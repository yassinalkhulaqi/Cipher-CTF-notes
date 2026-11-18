"""Stable error codes for engagement-core services."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any


class EngagementErrorCode(str, Enum):
    """Machine-readable engagement failure categories."""

    NOT_FOUND = "engagement_not_found"
    VALIDATION = "engagement_validation_failed"
    CONFLICT = "engagement_conflict"
    TRANSITION = "engagement_transition_denied"
    OPERATION = "engagement_operation_failed"


class EngagementError(Exception):
    """An engagement failure with transport-neutral metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: EngagementErrorCode = EngagementErrorCode.OPERATION,
        status: int = 400,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details: dict[str, Any] = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "status": self.status,
            "details": dict(self.details),
        }


def validation_error(issues: list[dict[str, str]]) -> EngagementError:
    """Build a validation error from a serialized validation report."""
    return EngagementError(
        "Engagement payload failed validation",
        code=EngagementErrorCode.VALIDATION,
        status=400,
        details={"issues": issues},
    )


def not_found(entity: str, entity_id: int) -> EngagementError:
    """Build a not-found error."""
    return EngagementError(
        f"{entity.title()} {entity_id} does not exist",
        code=EngagementErrorCode.NOT_FOUND,
        status=404,
        details={"entity": entity, "id": entity_id},
    )
