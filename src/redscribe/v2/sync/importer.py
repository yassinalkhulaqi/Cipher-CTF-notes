"""Import pipelines for sync snapshots and backups."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redscribe.services.importer import import_directory, import_markdown_file
from redscribe.storage.db import Vault
from redscribe.v2.sync.change_journal import ChangeJournal, normalize_record
from redscribe.v2.sync.errors import UnsupportedFormatError, ValidationError
from redscribe.v2.sync.merge import MergeEngine
from redscribe.v2.sync.models import ImportPlan
from redscribe.v2.sync.progress import ProgressCallback, ProgressTracker


class ImportPipeline:
    """Import portable snapshots into a vault."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def plan(
        self,
        *,
        source: str | Path,
        format_name: str = "auto",
        format: str | None = None,  # noqa: A002
        strategy: str = "merge",
        verify_checksums: bool = True,
        dry_run: bool = False,
        parent_id: int | None = None,
    ) -> ImportPlan:
        path = Path(source).expanduser()
        fmt = (format if format is not None else format_name).strip().lower() or "auto"
        if fmt == "auto":
            fmt = self.detect_format(path)
        if fmt not in {"json", "markdown"}:
            raise UnsupportedFormatError(f"Unsupported import format: {fmt}")
        if strategy not in {"merge", "skip", "prefer_local", "prefer_remote"}:
            raise ValidationError(f"Unsupported import strategy: {strategy}")
        return ImportPlan(
            source=str(path),
            format=fmt,
            strategy=strategy,
            verify_checksums=verify_checksums,
            dry_run=dry_run,
            parent_id=parent_id,
        )

    def detect_format(self, path: Path) -> str:
        if path.is_dir():
            return "markdown"
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".md", ".markdown", ".txt"}:
            return "markdown"
        raise UnsupportedFormatError(f"Cannot detect import format for: {path}")

    def load_records(self, plan: ImportPlan) -> list[dict[str, Any]]:
        source = Path(plan.source)
        if plan.format == "json":
            return self._load_json_records(source)
        if plan.format == "markdown":
            return self._load_markdown_records(source)
        raise UnsupportedFormatError(f"Unsupported import format: {plan.format}")

    def _load_json_records(self, source: Path) -> list[dict[str, Any]]:
        if not source.is_file():
            raise ValidationError(f"JSON import source does not exist: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records: list[Any] = payload
        elif isinstance(payload, dict):
            raw = payload.get("records", payload.get("notes", []))
            records = raw if isinstance(raw, list) else []
        else:
            raise ValidationError("Import JSON must be an array or object")
        if not isinstance(records, list):
            raise ValidationError("Import JSON records must be an array")
        return [normalize_record(item) for item in records if isinstance(item, dict)]

    def _load_markdown_records(self, source: Path) -> list[dict[str, Any]]:
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            return [
                normalize_record(
                    {
                        "id": 0,
                        "title": source.stem,
                        "kind": "note",
                        "content": text,
                        "path": source.name,
                    }
                )
            ]
        if source.is_dir():
            records: list[dict[str, Any]] = []
            for path in sorted(source.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in {".md", ".markdown", ".txt"}:
                    continue
                content = path.read_text(encoding="utf-8")
                records.append(
                    normalize_record(
                        {
                            "id": 0,
                            "title": path.stem,
                            "kind": "note",
                            "content": content,
                            "path": str(path.relative_to(source)).replace("\\", "/"),
                        }
                    )
                )
            return records
        raise ValidationError(f"Markdown import source does not exist: {source}")

    def preview(
        self,
        plan: ImportPlan,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        tracker = ProgressTracker("import", callback=progress)
        tracker.report("load", 0, 3, "loading import source")
        local = ChangeJournal().capture_vault(self.vault)
        remote = self.load_records(plan)
        tracker.report("diff", 1, 3, "computing differences")
        engine = MergeEngine(strategy=plan.strategy)
        merge = engine.preview(local, remote)
        tracker.report("complete", 3, 3, "import preview complete", done=True)
        return {
            "plan": plan.as_dict(),
            "dry_run": True,
            "local_records": len(local),
            "remote_records": len(remote),
            "merge": merge,
            "progress": tracker.as_dicts(),
        }

    def run(
        self,
        plan: ImportPlan,
        *,
        progress: ProgressCallback | None = None,
        resolutions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if plan.dry_run:
            return self.preview(plan, progress=progress)
        tracker = ProgressTracker("import", callback=progress)
        tracker.report("load", 0, 4, "loading import source")
        local = ChangeJournal().capture_vault(self.vault)
        remote = self.load_records(plan)
        tracker.report("merge", 1, 4, "merging records")
        engine = MergeEngine(strategy=plan.strategy)
        existing_keys = {str(item.get("path", "")).casefold() for item in local}

        def applier(change: Any, payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            if plan.format == "markdown" and Path(plan.source).is_dir():
                return
            if change.action == "delete":
                return
            self._apply_payload(payload, plan.parent_id, existing_keys)

        result = engine.apply(
            local,
            remote,
            resolutions=resolutions or {},
            dry_run=False,
            applier=applier,
        )
        if plan.format == "markdown":
            self._apply_markdown_source(plan)
        tracker.report("complete", 4, 4, "import complete", done=True)
        return {
            "plan": plan.as_dict(),
            "dry_run": False,
            "local_records": len(local),
            "remote_records": len(remote),
            "merge": result.as_dict(),
            "progress": tracker.as_dicts(),
        }

    def _apply_payload(
        self,
        payload: dict[str, Any],
        parent_id: int | None,
        existing_keys: set[str],
    ) -> None:
        kind = str(payload.get("kind", "note"))
        path_key = str(payload.get("path", "")).casefold()
        if kind != "note":
            return
        if path_key and path_key in existing_keys:
            return
        self.vault.create_node(
            str(payload.get("title", "Untitled")),
            parent_id,
            kind="note",
            content=str(payload.get("content", "")),
            tags=str(payload.get("tags", "")),
            target=str(payload.get("target", "")),
            status=str(payload.get("status", "todo")) if payload.get("status") else "todo",
            difficulty=str(payload.get("difficulty", "")),
            flag=str(payload.get("flag", "")),
            pinned=bool(payload.get("pinned", False)),
        )
        if path_key:
            existing_keys.add(path_key)

    def _apply_markdown_source(self, plan: ImportPlan) -> dict[str, Any]:
        source = Path(plan.source)
        if source.is_dir():
            folder, count = import_directory(self.vault, source, plan.parent_id)
            return {"folder": folder.id if folder is not None else None, "count": count}
        if source.is_file():
            node = import_markdown_file(self.vault, source, plan.parent_id)
            return {"node_id": node.id, "count": 1}
        raise ValidationError(f"Markdown import source does not exist: {source}")
