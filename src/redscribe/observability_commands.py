"""Read-only diagnostics and maintenance commands for the RedScribe CLI."""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from redscribe.domain.utils import format_duration, format_number
from redscribe.observability import log_event
from redscribe.storage.db import Vault

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Check:
    """The outcome of a single doctor probe."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    """A structured report and the exit code it implies."""

    report: dict[str, object]
    exit_code: int = 0


def read_schema_version(path: Path) -> int | None:
    """Read ``user_version`` without creating or migrating the vault."""
    if not path.exists():
        return None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute("PRAGMA user_version").fetchone()
    except (OSError, sqlite3.Error):
        return None
    return int(row[0]) if row is not None else None


def _run_check(name: str, action: Callable[[], str]) -> Check:
    started = time.perf_counter()
    try:
        detail = action()
    except Exception as exc:
        return Check(name, False, f"{type(exc).__name__}: {exc}")
    elapsed = format_duration((time.perf_counter() - started) * 1000)
    return Check(name, True, f"{detail} ({elapsed})")


def _pragma_check(vault: Vault, pragma: str) -> str:
    row = vault.connection.execute(f"PRAGMA {pragma}").fetchone()
    value = str(row[0]) if row is not None else "no result"
    if value.casefold() != "ok":
        raise RuntimeError(f"{pragma}: {value}")
    return value


def run_doctor(vault: Vault, path: Path) -> CommandResult:
    """Run non-destructive probes against an open vault."""
    stats = vault.basic_stats()
    checks = (
        _run_check("open", lambda: vault.display_path),
        _run_check("schema", lambda: f"user_version={vault.schema_version}"),
        _run_check("search_index", lambda: "fts5" if vault.fts_enabled else "like fallback"),
        _run_check(
            "nodes",
            lambda: (
                f"{format_number(len(vault.live_nodes()))} live, "
                f"{format_number(stats.trashed)} trashed"
            ),
        ),
        _run_check("snippets", lambda: f"{len(vault.list_custom_snippets())} custom"),
        _run_check("integrity", lambda: _pragma_check(vault, "quick_check")),
        _run_check("backup", lambda: f"{format_number(len(vault.backup_bytes()))} bytes"),
    )
    ok = all(check.ok for check in checks)
    failed = sum(1 for check in checks if not check.ok)
    report: dict[str, object] = {
        "command": "doctor",
        "ok": ok,
        "vault": str(path),
        "checks": [
            {"name": check.name, "ok": check.ok, "detail": check.detail} for check in checks
        ],
        "summary": {"passed": len(checks) - failed, "failed": failed},
    }
    log_event(LOGGER, "cli.doctor", vault=str(path), ok=ok, failed=failed)
    return CommandResult(report, 0 if ok else 1)


def run_stats(vault: Vault, path: Path) -> CommandResult:
    """Collect vault counts and composition into a scriptable report."""
    stats = vault.stats()
    report: dict[str, object] = {
        "command": "stats",
        "vault": str(path),
        "schema_version": vault.schema_version,
        "search": "fts5" if vault.fts_enabled else "like",
        "counts": {
            "notes": stats.notes,
            "folders": stats.folders,
            "flags": stats.flags,
            "targets": stats.targets,
            "tags": stats.tags,
            "pinned": stats.pinned,
            "trashed": stats.trashed,
        },
        "snippets": len(vault.list_custom_snippets()),
        "top_tags": [{"tag": entry.tag, "count": entry.count} for entry in vault.tag_counts()[:10]],
        "recent_notes": [
            {"id": note.id, "title": note.title, "updated_at": note.updated_at}
            for note in vault.recent_notes(5)
        ],
    }
    log_event(
        LOGGER,
        "cli.stats",
        vault=str(path),
        notes=stats.notes,
        folders=stats.folders,
        flags=stats.flags,
    )
    return CommandResult(report)


def run_backup(vault: Vault, path: Path, *, destination: Path | None = None) -> CommandResult:
    """Write a portable snapshot and verify that it can be reopened."""
    started = time.perf_counter()
    target = vault.backup_to(destination) if destination is not None else vault.backup_to_auto()
    with Vault(target) as restored:
        restored_stats = restored.basic_stats()
    elapsed = format_duration((time.perf_counter() - started) * 1000)
    report: dict[str, object] = {
        "command": "backup",
        "vault": str(path),
        "destination": str(target),
        "bytes": target.stat().st_size,
        "notes": restored_stats.notes,
        "folders": restored_stats.folders,
        "duration": elapsed,
    }
    log_event(LOGGER, "cli.backup", vault=str(path), destination=str(target), duration=elapsed)
    return CommandResult(report)


def run_migrate(vault: Vault, path: Path, *, before: int | None) -> CommandResult:
    """Apply pending schema migrations and rebuild the search index."""
    started = time.perf_counter()
    vault.rebuild_search_index()
    after = vault.schema_version
    elapsed = format_duration((time.perf_counter() - started) * 1000)
    created = before is None
    applied = created or (before is not None and before < after)
    report: dict[str, object] = {
        "command": "migrate",
        "vault": str(path),
        "before": before,
        "after": after,
        "created": created,
        "applied": applied,
        "search": "fts5" if vault.fts_enabled else "like",
        "duration": elapsed,
    }
    log_event(
        LOGGER,
        "cli.migrate",
        vault=str(path),
        before=before,
        after=after,
        applied=applied,
    )
    return CommandResult(report)


def _display(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _render_doctor(report: Mapping[str, object]) -> str:
    lines = [f"Doctor: {report.get('vault', '')}"]
    checks = report.get("checks", [])
    if isinstance(checks, list):
        for raw in checks:
            if not isinstance(raw, dict):
                continue
            marker = "PASS" if raw.get("ok") else "FAIL"
            lines.append(f"  [{marker}] {raw.get('name', '')}: {raw.get('detail', '')}")
    lines.append(f"Result: {'passed' if report.get('ok') else 'failed'}")
    return "\n".join(lines) + "\n"


def _render_stats(report: Mapping[str, object]) -> str:
    lines = [f"Stats: {report.get('vault', '')}"]
    counts = report.get("counts", {})
    if isinstance(counts, dict):
        for name, value in counts.items():
            lines.append(f"  {name}: {value}")
    lines.append(f"  schema: {report.get('schema_version', '')}")
    lines.append(f"  search: {report.get('search', '')}")
    tags = report.get("top_tags", [])
    if isinstance(tags, list) and tags:
        lines.append("Top tags:")
        for raw in tags:
            if isinstance(raw, dict):
                lines.append(f"  {raw.get('tag', '')}: {raw.get('count', 0)}")
    return "\n".join(lines) + "\n"


def _render_generic(report: Mapping[str, object]) -> str:
    lines = [f"{str(report.get('command', 'report')).title()}:"]
    for key, value in report.items():
        if key == "command":
            continue
        lines.append(f"  {key}: {_display(value)}")
    return "\n".join(lines) + "\n"


def emit_report(
    report: Mapping[str, object],
    *,
    json_output: bool = False,
    stream: TextIO | None = None,
) -> None:
    """Write a command report as JSON or as a compact human-readable block."""
    output = stream or sys.stdout
    if json_output:
        output.write(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        return
    command = str(report.get("command", ""))
    if command == "doctor":
        text = _render_doctor(report)
    elif command == "stats":
        text = _render_stats(report)
    else:
        text = _render_generic(report)
    output.write(text)
