"""Portability helpers for cross-device snapshot exchange."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redscribe.v2.sync.change_journal import normalize_record
from redscribe.v2.sync.checksums import checksum_file
from redscribe.v2.sync.errors import UnsupportedFormatError, ValidationError
from redscribe.v2.sync.manifest import SnapshotManifest


@dataclass(slots=True)
class PortabilityProfile:
    """A named portability profile describing export/import preferences."""

    name: str
    format: str
    include_deleted: bool = False
    include_settings: bool = False
    include_history: bool = False
    verify_checksums: bool = True
    strategy: str = "merge"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "format": self.format,
            "include_deleted": self.include_deleted,
            "include_settings": self.include_settings,
            "include_history": self.include_history,
            "verify_checksums": self.verify_checksums,
            "strategy": self.strategy,
            "description": self.description,
        }


DEFAULT_PROFILES: tuple[PortabilityProfile, ...] = (
    PortabilityProfile(
        name="quick-json",
        format="json",
        include_deleted=False,
        include_settings=False,
        verify_checksums=True,
        strategy="merge",
        description="Fast portable JSON snapshot for note transfer.",
    ),
    PortabilityProfile(
        name="full-backup",
        format="sqlite",
        include_deleted=False,
        include_settings=True,
        include_history=False,
        verify_checksums=True,
        strategy="prefer_remote",
        description="SQLite backup for full vault restore.",
    ),
    PortabilityProfile(
        name="markdown-archive",
        format="markdown",
        include_deleted=False,
        include_settings=False,
        verify_checksums=False,
        strategy="skip",
        description="Human-readable Markdown export tree.",
    ),
    PortabilityProfile(
        name="safe-import",
        format="json",
        include_deleted=False,
        include_settings=False,
        verify_checksums=True,
        strategy="skip",
        description="Conservative import that avoids overwriting local edits.",
    ),
)


def list_profiles() -> list[dict[str, Any]]:
    """Return built-in portability profiles."""
    return [profile.as_dict() for profile in DEFAULT_PROFILES]


def get_profile(name: str) -> PortabilityProfile:
    needle = name.strip().lower()
    for profile in DEFAULT_PROFILES:
        if profile.name == needle:
            return profile
    raise ValidationError(f"Unknown portability profile: {name}")


def detect_bundle(path: str | Path) -> dict[str, Any]:
    """Inspect a path and summarize its portability format."""
    source = Path(path).expanduser()
    if not source.exists():
        raise ValidationError(f"Portable path does not exist: {source}")
    if source.is_dir():
        manifest = source / "manifest.json"
        files = [p for p in source.rglob("*") if p.is_file()]
        return {
            "path": str(source),
            "kind": "directory",
            "format": "markdown",
            "files": len(files),
            "manifest": manifest.is_file(),
            "manifest_path": str(manifest) if manifest.is_file() else "",
        }
    suffix = source.suffix.lower()
    info: dict[str, Any] = {
        "path": str(source),
        "kind": "file",
        "size": source.stat().st_size,
        "checksum": checksum_file(source),
    }
    if suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        info.update(
            {
                "format": "json",
                "records": len(records) if isinstance(records, list) else 0,
                "portable": isinstance(payload, dict),
            }
        )
        return info
    if suffix == ".db":
        info.update({"format": "sqlite", "portable": True})
        return info
    if suffix == ".html":
        info.update({"format": "html", "portable": True})
        return info
    if suffix in {".md", ".markdown", ".txt"}:
        info.update({"format": "markdown", "portable": True})
        return info
    raise UnsupportedFormatError(f"Unsupported portable format: {suffix}")


def read_portable_records(path: str | Path) -> list[dict[str, Any]]:
    """Read portable JSON or markdown records from a source path."""
    source = Path(path).expanduser()
    if source.is_dir():
        records: list[dict[str, Any]] = []
        for file_path in sorted(source.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in {
                ".md",
                ".markdown",
                ".txt",
            }:
                continue
            records.append(
                normalize_record(
                    {
                        "id": 0,
                        "title": file_path.stem,
                        "kind": "note",
                        "content": file_path.read_text(encoding="utf-8"),
                        "path": str(file_path.relative_to(source)).replace("\\", "/"),
                    }
                )
            )
        return records
    if source.suffix.lower() != ".json":
        raise UnsupportedFormatError(
            "Portable record loading supports JSON or markdown directories"
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("records", [])
    else:
        items = []
    return [normalize_record(item) for item in items if isinstance(item, dict)]


def portability_summary(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize a collection of portable records."""
    items = [dict(item) for item in records]
    notes = [item for item in items if str(item.get("kind", "note")) == "note"]
    folders = [item for item in items if str(item.get("kind", "")) == "folder"]
    tags: set[str] = set()
    targets: set[str] = set()
    for item in notes:
        tags.update(part.strip() for part in str(item.get("tags", "")).split(",") if part.strip())
        target = str(item.get("target", "")).strip()
        if target:
            targets.add(target)
    return {
        "total": len(items),
        "notes": len(notes),
        "folders": len(folders),
        "tags": len(tags),
        "targets": len(targets),
        "with_flags": sum(1 for item in notes if str(item.get("flag", "")).strip()),
        "with_content": sum(1 for item in notes if str(item.get("content", "")).strip()),
    }


def build_portable_manifest(
    source: str,
    records: Iterable[Mapping[str, Any]],
    *,
    format_name: str = "json",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a manifest for a portable record collection."""
    items = [dict(item) for item in records]
    manifest = SnapshotManifest.build(
        source=source,
        format_name=format_name,
        records=items,
        metadata=dict(metadata or {}),
    )
    return manifest.as_dict()


def compatibility_matrix() -> dict[str, Any]:
    """Describe supported import/export combinations."""
    return {
        "export": ["json", "markdown", "html"],
        "backup": ["sqlite", "json"],
        "import": ["json", "markdown"],
        "restore": ["sqlite", "json"],
        "profiles": list_profiles(),
        "notes": [
            "SQLite backups are best for full fidelity restores.",
            "JSON snapshots preserve record metadata and checksums.",
            "Markdown exports are human-readable but may lose some structured metadata.",
        ],
    }
