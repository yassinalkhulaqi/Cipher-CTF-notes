"""Append-only migration registry for schema v5."""

from __future__ import annotations

from dataclasses import dataclass

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.migrations.v5 import (
    MIGRATION_STEPS,
    PREVIOUS_SCHEMA_VERSION,
    SCHEMA_VERSION,
    MigrationStep,
    migration_checksum,
)


class MigrationError(RuntimeError):
    """Raised when a migration chain is invalid."""


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """Record of one applied migration."""

    version: int
    name: str
    checksum: str
    applied_at: float


class MigrationChain:
    """Validate and describe the ordered migration chain."""

    def __init__(self, steps: tuple[MigrationStep, ...] = MIGRATION_STEPS) -> None:
        self._steps = steps

    def steps(self) -> tuple[MigrationStep, ...]:
        """Return all migration steps."""
        return self._steps

    def names(self) -> tuple[str, ...]:
        """Return migration names in order."""
        return tuple(step.name for step in self._steps)

    def validate(self) -> tuple[str, ...]:
        """Return problems with the chain."""
        problems: list[str] = []
        seen: set[str] = set()
        for step in self._steps:
            if step.name in seen:
                problems.append(f"duplicate migration: {step.name}")
            seen.add(step.name)
            if not step.sql.strip():
                problems.append(f"empty migration: {step.name}")
            if not step.sql.upper().startswith(("CREATE TABLE", "CREATE INDEX")):
                problems.append(f"migration is not append-only: {step.name}")
        return tuple(problems)

    def require_valid(self) -> None:
        """Raise when the chain has problems."""
        problems = self.validate()
        if problems:
            raise MigrationError("; ".join(problems))

    def can_upgrade_from(self, version: int) -> bool:
        """Return whether the chain supports upgrading from a version."""
        return PREVIOUS_SCHEMA_VERSION <= version < SCHEMA_VERSION

    def plan(self, current: int, *, clock: Clock | None = None) -> tuple[AppliedMigration, ...]:
        """Build a plan of migrations to apply."""
        if current >= SCHEMA_VERSION:
            return ()
        if not self.can_upgrade_from(current):
            raise MigrationError(f"Cannot upgrade from schema version {current}")
        timer: Clock = clock or SystemClock()
        return tuple(
            AppliedMigration(
                version=SCHEMA_VERSION,
                name=step.name,
                checksum=step.checksum,
                applied_at=timer.now_timestamp(),
            )
            for step in self._steps
        )

    def refuse_downgrade(self, current: int) -> None:
        """Reject a silent downgrade attempt."""
        if current > SCHEMA_VERSION:
            raise MigrationError(
                f"Vault schema {current} is newer than supported {SCHEMA_VERSION}; "
                "open it with a newer RedScribe version"
            )

    def manifest(self) -> dict[str, object]:
        """Return a JSON-safe migration manifest."""
        return {
            "from": PREVIOUS_SCHEMA_VERSION,
            "to": SCHEMA_VERSION,
            "checksum": migration_checksum(),
            "steps": [{"name": step.name, "checksum": step.checksum} for step in self._steps],
        }


chain = MigrationChain()
