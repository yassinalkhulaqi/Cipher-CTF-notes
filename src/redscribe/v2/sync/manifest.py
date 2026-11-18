"""Snapshot manifest creation and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redscribe import __version__
from redscribe.storage.migrations import SCHEMA_VERSION
from redscribe.v2.sync.checksums import ChecksumVerifier, canonical_json, checksum_json
from redscribe.v2.sync.errors import ValidationError

MANIFEST_VERSION = "1.0"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class SnapshotManifest:
    """Describes a portable snapshot and the files/records it contains."""

    manifest_version: str = MANIFEST_VERSION
    created_at: str = field(default_factory=utc_stamp)
    app_version: str = __version__
    schema_version: int = SCHEMA_VERSION
    source: str = ""
    format: str = "json"
    record_count: int = 0
    files: dict[str, str] = field(default_factory=dict)
    record_checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    digest: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SnapshotManifest:
        manifest = cls(
            manifest_version=str(data.get("manifest_version", MANIFEST_VERSION)),
            created_at=str(data.get("created_at", "")) or utc_stamp(),
            app_version=str(data.get("app_version", __version__)),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            source=str(data.get("source", "")),
            format=str(data.get("format", "json")),
            record_count=int(data.get("record_count", 0)),
            files={
                str(key): str(value)
                for key, value in dict(data.get("files", {})).items()
                if str(key)
            },
            record_checksums={
                str(key): str(value)
                for key, value in dict(data.get("record_checksums", {})).items()
                if str(key)
            },
            metadata=dict(data.get("metadata", {})),
            digest=str(data.get("digest", "")),
        )
        return manifest

    @classmethod
    def build(
        cls,
        *,
        source: str,
        format_name: str = "json",
        format: str | None = None,  # noqa: A002
        records: Sequence[Mapping[str, Any]],
        files: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> SnapshotManifest:
        record_checksums = {}
        for record in records:
            key = str(record.get("path") or record.get("title") or record.get("id") or "")
            checksum = str(record.get("checksum", ""))
            if key and checksum:
                record_checksums[key] = checksum
        fmt = format if format is not None else format_name
        manifest = cls(
            created_at=created_at or utc_stamp(),
            source=source,
            format=fmt,
            record_count=len(records),
            files={str(k): str(v) for k, v in dict(files or {}).items()},
            record_checksums=dict(sorted(record_checksums.items())),
            metadata=dict(metadata or {}),
        )
        manifest.digest = manifest.compute_digest()
        return manifest

    def compute_digest(self) -> str:
        payload = self.as_dict(include_digest=False)
        return checksum_json(payload)

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "manifest_version": self.manifest_version,
            "created_at": self.created_at,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "source": self.source,
            "format": self.format,
            "record_count": self.record_count,
            "files": dict(sorted(self.files.items())),
            "record_checksums": dict(sorted(self.record_checksums.items())),
            "metadata": dict(self.metadata),
        }
        if include_digest:
            payload["digest"] = self.digest or self.compute_digest()
        return payload

    def validate(self) -> SnapshotManifest:
        if self.manifest_version != MANIFEST_VERSION:
            raise ValidationError(
                f"Unsupported manifest version: {self.manifest_version}",
                details={"supported": [MANIFEST_VERSION]},
            )
        if self.record_count < 0:
            raise ValidationError("Manifest record_count cannot be negative")
        if self.schema_version < 1:
            raise ValidationError("Manifest schema_version must be positive")
        if not self.format:
            raise ValidationError("Manifest format is required")
        expected = self.compute_digest()
        if self.digest and self.digest != expected:
            raise ValidationError(
                "Manifest digest mismatch",
                details={"expected": expected, "actual": self.digest},
            )
        self.digest = expected
        return self

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            canonical_json(self.as_dict()) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def read(cls, path: str | Path) -> SnapshotManifest:
        source = Path(path)
        if not source.is_file():
            raise ValidationError(f"Manifest file does not exist: {source}")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Manifest is not valid JSON: {source}") from exc
        if not isinstance(data, dict):
            raise ValidationError("Manifest payload must be an object")
        return cls.from_dict(data).validate()

    def verify_files(
        self,
        root: str | Path,
        *,
        allow_extra: bool = True,
    ) -> dict[str, Any]:
        verifier = ChecksumVerifier()
        report = verifier.compare(
            self.files,
            verifier.file_map(root, self.files.keys()),
            allow_extra=allow_extra,
        )
        if not report.ok and not allow_extra:
            raise ValidationError("Manifest file checksums do not match", details=report.as_dict())
        return report.as_dict()
