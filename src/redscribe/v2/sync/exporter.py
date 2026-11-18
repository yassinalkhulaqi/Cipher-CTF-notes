"""Export pipelines for portable sync snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redscribe.services.exporter import export_vault_html, export_vault_markdown
from redscribe.storage.db import Vault
from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.checksums import checksum_file
from redscribe.v2.sync.errors import UnsupportedFormatError, ValidationError
from redscribe.v2.sync.manifest import SnapshotManifest
from redscribe.v2.sync.models import ExportPlan
from redscribe.v2.sync.progress import ProgressCallback, ProgressTracker


def _default_path(base: Path, fmt: str) -> Path:
    if base.suffix:
        return base
    if fmt == "json":
        return base.with_suffix(".json")
    if fmt == "markdown":
        return base
    if fmt == "html":
        return base.with_suffix(".html")
    return base


class ExportPipeline:
    """Export vault content to portable formats with manifests."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def plan(
        self,
        *,
        destination: str | Path,
        format_name: str = "json",
        format: str | None = None,  # noqa: A002
        include_deleted: bool = False,
        include_settings: bool = False,
        dry_run: bool = False,
        label: str = "",
    ) -> ExportPlan:
        fmt = (format if format is not None else format_name).strip().lower() or "json"
        if fmt not in {"json", "markdown", "html"}:
            raise UnsupportedFormatError(f"Unsupported export format: {fmt}")
        target = _default_path(Path(destination).expanduser(), fmt)
        return ExportPlan(
            destination=str(target),
            format=fmt,
            include_deleted=include_deleted,
            include_settings=include_settings,
            dry_run=dry_run,
            label=label.strip(),
        )

    def export(
        self,
        plan: ExportPlan,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        tracker = ProgressTracker("export", callback=progress)
        tracker.report("plan", 0, 4, "planning export")
        target = Path(plan.destination)
        journal = ChangeJournal()
        records = journal.capture_vault(self.vault, include_deleted=plan.include_deleted)
        manifest = SnapshotManifest.build(
            source=self.vault.display_path,
            format_name=plan.format,
            records=records,
            files={},
            metadata={
                "label": plan.label,
                "include_deleted": plan.include_deleted,
                "include_settings": plan.include_settings,
            },
        )
        if plan.dry_run:
            tracker.report("complete", 4, 4, "dry run complete", done=True)
            return {
                "plan": plan.as_dict(),
                "dry_run": True,
                "path": str(target),
                "manifest": manifest.as_dict(),
                "records": len(records),
                "progress": tracker.as_dicts(),
            }

        if plan.format == "json":
            tracker.report("write", 1, 4, "writing json export")
            payload = self._export_json(target, plan, records)
            manifest.files = {target.name: checksum_file(target)}
            manifest.metadata.update(payload.get("counts", {}))
        elif plan.format == "markdown":
            tracker.report("write", 1, 4, "writing markdown export")
            count = self._export_markdown(target)
            manifest.metadata["exported_notes"] = count
            manifest.files = self._directory_checksums(target)
        elif plan.format == "html":
            tracker.report("write", 1, 4, "writing html export")
            count = self._export_html(target)
            manifest.metadata["exported_notes"] = count
            manifest.files = {target.name: checksum_file(target)}
        else:
            raise UnsupportedFormatError(f"Unsupported export format: {plan.format}")

        tracker.report("manifest", 3, 4, "writing export manifest")
        manifest.digest = manifest.compute_digest()
        manifest_path = self._manifest_path(target, plan.format)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tracker.report("complete", 4, 4, "export complete", done=True)
        return {
            "plan": plan.as_dict(),
            "dry_run": False,
            "path": str(target),
            "manifest_path": str(manifest_path),
            "manifest": manifest.as_dict(),
            "records": len(records),
            "progress": tracker.as_dicts(),
        }

    def _export_json(
        self, target: Path, plan: ExportPlan, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "format": "redscribe.snapshot.json",
            "source": self.vault.display_path,
            "records": records,
        }
        if plan.include_settings:
            rows = self.vault.connection.execute(
                "SELECT key, value FROM settings ORDER BY key"
            ).fetchall()
            payload["settings"] = {str(row["key"]): str(row["value"]) for row in rows}
        payload["counts"] = {
            "records": len(records),
            "notes": sum(1 for item in records if item.get("kind") == "note"),
            "folders": sum(1 for item in records if item.get("kind") == "folder"),
        }
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return payload

    def _export_markdown(self, target: Path) -> int:
        target.mkdir(parents=True, exist_ok=True)
        return export_vault_markdown(self.vault, target)

    def _export_html(self, target: Path) -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        return export_vault_html(self.vault, target)

    def _manifest_path(self, target: Path, fmt: str) -> Path:
        if fmt == "markdown":
            return target / "manifest.json"
        return target.with_suffix(target.suffix + ".manifest.json")

    def _directory_checksums(self, directory: Path) -> dict[str, str]:
        if not directory.is_dir():
            return {}
        files: dict[str, str] = {}
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(directory)).replace("\\", "/")
            files[relative] = checksum_file(path)
        return files

    def read_snapshot(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser()
        if source.is_dir():
            manifest = source / "manifest.json"
            return {
                "format": "markdown",
                "path": str(source),
                "manifest": json.loads(manifest.read_text(encoding="utf-8"))
                if manifest.is_file()
                else {},
            }
        if not source.is_file():
            raise ValidationError(f"Export path does not exist: {source}")
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValidationError("Snapshot JSON must be an object")
            return {"format": "json", "path": str(source), "payload": payload}
        if source.suffix.lower() == ".html":
            return {"format": "html", "path": str(source), "size": source.stat().st_size}
        raise UnsupportedFormatError(f"Cannot read export format: {source.suffix}")
