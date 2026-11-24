"""Exception hierarchy for the V3 automation package."""

from __future__ import annotations

from typing import Any


class AutomationError(Exception):
    """Base class for errors that are safe to show in an API envelope."""

    code = "automation_error"

    def __init__(self, message: str, *, path: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.path = path

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without leaking values."""
        return {"code": self.code, "message": self.message, "path": self.path}


class PlaybookValidationError(AutomationError):
    """A playbook or variable set failed structural validation."""

    code = "invalid_playbook"


class CycleDetectedError(AutomationError):
    """The dependency graph contains a cycle."""

    code = "cycle_detected"


class VariableResolutionError(AutomationError):
    """A variable or interpolation could not be resolved."""

    code = "invalid_variable"


class UnsupportedStepError(AutomationError):
    """A step requested an operation that is not data-only."""

    code = "unsupported_step"


class RunNotFoundError(AutomationError):
    """A run id was not present in the store."""

    code = "run_not_found"


class ReplayMismatchError(AutomationError):
    """A replay produced a different trace than the original run."""

    code = "replay_mismatch"


class RecurrenceError(AutomationError):
    """A recurrence rule is invalid or cannot be expanded."""

    code = "invalid_recurrence"


class DryRunWriteAttemptedError(AutomationError):
    """Internal guard fired: a dry run tried to perform a real mutation."""

    code = "dry_run_write_attempted"


class RollbackError(AutomationError):
    """A rollback could not be completed or verified."""

    code = "rollback_failed"
