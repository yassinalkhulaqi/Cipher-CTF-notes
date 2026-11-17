"""Retention and maintenance helpers for the SQLite vault."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

_AUTO_BACKUP_RE = re.compile(r"vault-(\d{8}T\d{6}Z)(?:-(\d+))?\.db")
_CHECKPOINT_MODES = frozenset({"PASSIVE", "FULL", "RESTART", "TRUNCATE"})


class AutoBackup(NamedTuple):
    """An automatic backup file with a sortable timestamp key."""

    path: Path
    stamp: str
    sequence: int

    @property
    def sort_key(self) -> tuple[str, int]:
        return self.stamp, self.sequence


def parse_auto_backup(path: Path) -> AutoBackup | None:
    match = _AUTO_BACKUP_RE.fullmatch(path.name)
    if match is None:
        return None
    return AutoBackup(
        path=path,
        stamp=str(match.group(1)),
        sequence=int(match.group(2) or 0),
    )


def list_auto_backups(directory: Path) -> list[AutoBackup]:
    if not directory.is_dir():
        return []
    entries = (parse_auto_backup(path) for path in directory.iterdir())
    return sorted(
        (entry for entry in entries if entry is not None), key=lambda entry: entry.sort_key
    )


def rotate_auto_backups(directory: Path, *, keep: int, exclude: Path | None = None) -> list[Path]:
    backups = list_auto_backups(directory)
    if len(backups) <= keep:
        return []
    keepers = {entry.path.name for entry in backups[-keep:]} if keep else set()
    protected = exclude.name if exclude is not None else None
    removed: list[Path] = []
    for entry in backups:
        if entry.path.name in keepers or entry.path.name == protected:
            continue
        entry.path.unlink()
        removed.append(entry.path)
    return removed


@dataclass(frozen=True, slots=True)
class PruneResult:
    """Outcome of a version-history prune."""

    versions_removed: int = 0
    nodes_affected: int = 0
    orphan_versions_removed: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "versions_removed": self.versions_removed,
            "nodes_affected": self.nodes_affected,
            "orphan_versions_removed": self.orphan_versions_removed,
        }


@dataclass(frozen=True, slots=True)
class CheckpointResult:
    """Result of a SQLite WAL checkpoint request."""

    mode: str
    busy: int
    log: int
    checkpointed: int

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "busy": self.busy,
            "log": self.log,
            "checkpointed": self.checkpointed,
        }


def validate_checkpoint_mode(mode: str) -> str:
    normalized = mode.upper()
    if normalized not in _CHECKPOINT_MODES:
        raise ValueError(f"Unsupported checkpoint mode: {mode}")
    return normalized
