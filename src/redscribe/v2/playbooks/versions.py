"""Semantic versions and history for playbooks, snippets, and templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.playbooks.errors import VersionConflictError


@dataclass(frozen=True, slots=True, order=True)
class Version:
    """A comparable semantic version."""

    major: int = 0
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, value: str) -> Version:
        """Parse a strict ``MAJOR.MINOR.PATCH`` string."""
        parts = value.strip().lstrip("vV").split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise VersionConflictError(f"Invalid semantic version: {value}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def bump(self, part: str = "patch") -> Version:
        """Return the next version after a semantic bump."""
        if part == "major":
            return Version(self.major + 1, 0, 0)
        if part == "minor":
            return Version(self.major, self.minor + 1, 0)
        if part == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise VersionConflictError(f"Unknown bump part: {part}")

    def compatible_with(self, other: Version) -> bool:
        """Return true when both versions share a major series."""
        return self.major == other.major


@dataclass(frozen=True, slots=True)
class VersionEntry:
    """One immutable entry in a version history."""

    version: str
    message: str = ""
    at: str = ""
    author: str = ""
    checksum: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "message": self.message,
            "at": self.at,
            "author": self.author,
            "checksum": self.checksum,
        }


@dataclass(frozen=True, slots=True)
class VersionHistory:
    """An append-only chain of version entries."""

    key: str
    entries: tuple[VersionEntry, ...] = ()

    @property
    def latest(self) -> VersionEntry | None:
        return self.entries[-1] if self.entries else None

    @property
    def versions(self) -> tuple[str, ...]:
        return tuple(entry.version for entry in self.entries)

    def append(
        self,
        version: str,
        message: str = "",
        *,
        author: str = "",
        checksum: str = "",
        at: str = "",
    ) -> VersionHistory:
        """Append a new entry after validating the version order."""
        parsed = Version.parse(version)
        if self.entries:
            current = Version.parse(self.entries[-1].version)
            if parsed <= current:
                raise VersionConflictError(
                    f"Version {version} must be newer than {current}",
                    details={"key": self.key, "current": str(current)},
                )
        entry = VersionEntry(
            version=version,
            message=message,
            at=at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            author=author,
            checksum=checksum,
        )
        return VersionHistory(self.key, (*self.entries, entry))

    def entry(self, version: str) -> VersionEntry | None:
        """Find one entry by exact version string."""
        for item in self.entries:
            if item.version == version:
                return item
        return None

    def between(self, start: str, end: str) -> tuple[VersionEntry, ...]:
        """Return entries in the inclusive version range."""
        lower, upper = Version.parse(start), Version.parse(end)
        if lower > upper:
            raise VersionConflictError("Range start is newer than its end")
        return tuple(item for item in self.entries if lower <= Version.parse(item.version) <= upper)

    def changelog(self) -> list[dict[str, Any]]:
        """Return entries as API-ready change records."""
        return [entry.as_dict() for entry in self.entries]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "latest": self.latest.version if self.latest else "0.0.0",
            "versions": list(self.versions),
            "entries": self.changelog(),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> VersionHistory:
        """Restore a history from an import payload."""
        if not isinstance(payload, dict):
            return cls(str(payload))
        entries: list[VersionEntry] = []
        raw_entries = payload.get("entries", [])
        if isinstance(raw_entries, list):
            for raw in raw_entries:
                if not isinstance(raw, dict):
                    continue
                entries.append(
                    VersionEntry(
                        version=str(raw.get("version", "0.0.0")),
                        message=str(raw.get("message", "")),
                        at=str(raw.get("at", "")),
                        author=str(raw.get("author", "")),
                        checksum=str(raw.get("checksum", "")),
                    )
                )
        return cls(str(payload.get("key", "")), tuple(entries))


def bump_version(version: str, part: str = "patch") -> str:
    """Return a bumped semantic version string."""
    return str(Version.parse(version).bump(part))


def versions_compatible(first: str, second: str) -> bool:
    """Return true when two versions share a major series."""
    return Version.parse(first).compatible_with(Version.parse(second))


@dataclass(frozen=True, slots=True)
class FieldDifference:
    """A single changed field in a version diff."""

    path: str
    kind: str
    before: Any = None
    after: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "before": self.before,
            "after": self.after,
        }


def diff_payloads(before: Any, after: Any, *, path: str = "") -> tuple[FieldDifference, ...]:
    """Compute a stable structural diff between two JSON-like payloads."""
    differences: list[FieldDifference] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before:
                differences.append(FieldDifference(child, "added", after=after[key]))
            elif key not in after:
                differences.append(FieldDifference(child, "removed", before=before[key]))
            else:
                differences.extend(diff_payloads(before[key], after[key], path=child))
        return tuple(differences)
    if isinstance(before, list) and isinstance(after, list):
        if before != after:
            differences.append(FieldDifference(path or "root", "changed", before, after))
        return tuple(differences)
    if before != after:
        differences.append(FieldDifference(path or "root", "changed", before, after))
    return tuple(differences)


def suggest_bump(history: VersionHistory, changes: tuple[FieldDifference, ...]) -> str:
    """Suggest a bump level based on the shape of a payload diff."""
    if not changes:
        return "patch"
    if any(change.kind in ("added", "removed") for change in changes):
        return "minor"
    if any("steps" in change.path or "variables" in change.path for change in changes):
        return "minor"
    current = history.latest.version if history.latest else "0.0.0"
    return str(Version.parse(current).bump("patch"))
