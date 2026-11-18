"""Migration compatibility checks for portable sync snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from redscribe import __version__
from redscribe.storage.migrations import MIGRATIONS, SCHEMA_VERSION
from redscribe.v2.sync.errors import MigrationCompatibilityError, ValidationError

SUPPORTED_MANIFEST_VERSIONS: tuple[str, ...] = ("1.0",)


@dataclass(slots=True)
class CompatibilityReport:
    """Compatibility evaluation for a manifest or snapshot."""

    compatible: bool
    source_schema_version: int
    target_schema_version: int
    manifest_version: str
    requires_migration: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "source_schema_version": self.source_schema_version,
            "target_schema_version": self.target_schema_version,
            "manifest_version": self.manifest_version,
            "requires_migration": self.requires_migration,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


class MigrationCompatibility:
    """Evaluate whether a snapshot can be imported into this runtime."""

    def __init__(
        self,
        *,
        current_schema: int = SCHEMA_VERSION,
        supported_manifest_versions: tuple[str, ...] = SUPPORTED_MANIFEST_VERSIONS,
    ) -> None:
        self.current_schema = current_schema
        self.supported_manifest_versions = supported_manifest_versions

    def check_manifest(self, manifest: Mapping[str, Any]) -> CompatibilityReport:
        manifest_version = str(manifest.get("manifest_version", ""))
        source_schema = int(manifest.get("schema_version", 0) or 0)
        if source_schema <= 0:
            raise ValidationError("Manifest schema_version is missing or invalid")
        warnings: list[str] = []
        errors: list[str] = []
        requires_migration = source_schema != self.current_schema
        if manifest_version not in self.supported_manifest_versions:
            errors.append(f"Manifest version {manifest_version or 'unknown'} is not supported")
        if source_schema > self.current_schema:
            errors.append(
                f"Snapshot schema {source_schema} is newer than runtime "
                f"schema {self.current_schema}"
            )
        elif source_schema < self.current_schema:
            warnings.append(
                f"Snapshot schema {source_schema} will be interpreted by "
                f"runtime schema {self.current_schema}"
            )
        app_version = str(manifest.get("app_version", ""))
        if app_version and app_version != __version__:
            warnings.append(
                f"Snapshot was created by RedScribe {app_version}, current runtime is {__version__}"
            )
        record_count = int(manifest.get("record_count", 0) or 0)
        if record_count < 0:
            errors.append("Manifest record_count cannot be negative")
        report = CompatibilityReport(
            compatible=not errors,
            source_schema_version=source_schema,
            target_schema_version=self.current_schema,
            manifest_version=manifest_version or "unknown",
            requires_migration=requires_migration,
            warnings=warnings,
            errors=errors,
        )
        return report

    def require(
        self, manifest: Mapping[str, Any], *, allow_incompatible: bool = False
    ) -> CompatibilityReport:
        report = self.check_manifest(manifest)
        if report.compatible:
            return report
        if allow_incompatible and all(
            "newer than runtime schema" not in error for error in report.errors
        ):
            return report
        raise MigrationCompatibilityError(
            "Snapshot is not compatible with this runtime",
            details=report.as_dict(),
        )

    def migration_plan(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        report = self.check_manifest(manifest)
        source = report.source_schema_version
        target = report.target_schema_version
        chain = [migration.name for migration in MIGRATIONS if source < migration.version <= target]
        return {
            "compatible": report.compatible,
            "from_version": source,
            "to_version": target,
            "steps": chain,
            "requires_migration": report.requires_migration,
            "warnings": report.warnings,
            "errors": report.errors,
        }

    def supported_versions(self) -> dict[str, Any]:
        return {
            "manifest_versions": list(self.supported_manifest_versions),
            "schema_version": self.current_schema,
            "migrations": [migration.name for migration in MIGRATIONS],
        }
