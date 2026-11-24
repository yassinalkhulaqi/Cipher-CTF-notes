"""Failure types raised by the evidence inspection lab.

All errors carry a stable machine code so namespace handlers can translate a
domain failure into a V3 error envelope without leaking internals.
"""

from __future__ import annotations

from typing import Any


class EvidenceLabError(Exception):
    """Base class for every evidence-lab failure."""

    code = "evidence_lab_error"

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context or {})

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable description of the failure."""
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class InvalidInputError(EvidenceLabError):
    """Raised when a caller supplies a malformed inspection parameter."""

    code = "invalid_input"


class InvalidRangeError(EvidenceLabError):
    """Raised when a byte-range request cannot be satisfied."""

    code = "invalid_range"


class PayloadTooLargeError(EvidenceLabError):
    """Raised when a request exceeds a configured memory budget."""

    code = "payload_too_large"


class EvidenceNotFoundError(EvidenceLabError):
    """Raised when a registered evidence record is unknown."""

    code = "evidence_not_found"


class CustodyCycleError(EvidenceLabError):
    """Raised when a custody graph contains a directed cycle."""

    code = "custody_cycle"


class CapabilityDisabledError(EvidenceLabError):
    """Raised when the evidence-lab capability is switched off."""

    code = "capability_disabled"


class UnsupportedEncodingError(EvidenceLabError):
    """Raised when a requested string encoding is not supported."""

    code = "unsupported_encoding"
