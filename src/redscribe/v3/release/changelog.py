"""Deterministic changelog, migration-note, and release-note builders.

The builders emit Markdown strings only. They never write files: the release
documents propose their content in ``docs/v3/release.md`` so a maintainer can
review and copy it into ``README.md`` / ``CHANGELOG.md`` deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.release.models import ChangelogEntry, MigrationNote

RELEASE_DATE = "2026-11-24"
CHANGELOG_CATEGORIES: tuple[str, ...] = (
    "Added",
    "Changed",
    "Fixed",
    "Hardened",
    "Documentation",
)


@dataclass(slots=True)
class ChangelogBuilder:
    """Collect and render release-note entries."""

    version: str = "3.0.0"
    released_on: str = RELEASE_DATE
    _entries: list[ChangelogEntry] = field(default_factory=list)

    def add(
        self,
        category: str,
        title: str,
        detail: str,
        reference: str = "",
    ) -> ChangelogEntry:
        """Append one changelog entry."""
        if category not in CHANGELOG_CATEGORIES:
            raise ValueError(f"Unknown changelog category: {category}")
        entry = ChangelogEntry(
            version=self.version,
            category=category,
            title=title,
            detail=detail,
            reference=reference,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> tuple[ChangelogEntry, ...]:
        """Return entries in stable category order."""
        return tuple(
            sorted(
                self._entries,
                key=lambda entry: (
                    CHANGELOG_CATEGORIES.index(entry.category),
                    entry.title.casefold(),
                ),
            )
        )

    def by_category(self) -> dict[str, tuple[ChangelogEntry, ...]]:
        """Return entries grouped by category."""
        return {
            category: tuple(entry for entry in self.entries() if entry.category == category)
            for category in CHANGELOG_CATEGORIES
        }

    def render(self) -> str:
        """Render a Keep-a-Changelog-style section."""
        lines = [f"## [{self.version}] - {self.released_on}", ""]
        for category, entries in self.by_category().items():
            if not entries:
                continue
            lines.append(f"### {category}")
            lines.append("")
            for entry in entries:
                suffix = f" ({entry.reference})" if entry.reference else ""
                lines.append(f"- **{entry.title}** — {entry.detail}{suffix}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "version": self.version,
            "released_on": self.released_on,
            "entries": [entry.as_dict() for entry in self.entries()],
        }


@dataclass(slots=True)
class MigrationNoteBuilder:
    """Collect and render upgrade instructions."""

    _notes: list[MigrationNote] = field(default_factory=list)

    def add(
        self,
        from_version: str,
        to_version: str,
        title: str,
        action: str,
        *,
        automated: bool = True,
        note: str = "",
    ) -> MigrationNote:
        """Append one migration note."""
        item = MigrationNote(
            from_version=from_version,
            to_version=to_version,
            title=title,
            action=action,
            automated=automated,
            note=note,
        )
        self._notes.append(item)
        return item

    def notes(self) -> tuple[MigrationNote, ...]:
        """Return notes in declaration order."""
        return tuple(self._notes)

    def render(self) -> str:
        """Render numbered, reviewable upgrade steps."""
        lines = ["# V3 migration notes", ""]
        for index, note in enumerate(self._notes, start=1):
            mode = "automatic" if note.automated else "manual"
            lines.append(f"## {index}. {note.title} (`{note.from_version}` -> `{note.to_version}`)")
            lines.append("")
            lines.append(f"- Mode: {mode}")
            lines.append(f"- Action: `{note.action}`")
            if note.note:
                lines.append(f"- Note: {note.note}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"notes": [note.as_dict() for note in self.notes()]}


def build_release_changelog() -> ChangelogBuilder:
    """Build the proposed V3 changelog from the branch plan."""
    builder = ChangelogBuilder()
    builder.add(
        "Added",
        "Universal V3 contracts",
        "Entity ids, typed links, immutable records, domain events, and a stable API envelope.",
        "B00",
    )
    builder.add(
        "Added",
        "Feature workflows",
        "Findings, evidence vault, graph workbench, pivot navigation, playbooks, and reporting.",
        "B01-B07",
    )
    builder.add(
        "Added",
        "Operations and extensibility",
        "Activity, search, sync, security, performance, i18n, automation, and extension manifests.",
        "B08-B13",
    )
    builder.add(
        "Added",
        "Release toolkit",
        "Golden-path scenarios, smoke suite, docs, changelog builders, and gates.",
        "B14",
    )
    builder.add(
        "Changed",
        "First-run experience",
        "Onboarding, empty states, icons, labels, and responsive polish share v3.",
        "B14",
    )
    builder.add(
        "Fixed",
        "Cross-branch drift",
        "Namespaces register as data; no branch edits a central dispatch table or token file.",
        "B00-B14",
    )
    builder.add(
        "Hardened",
        "Offline guarantees",
        "No runtime dependencies, no network clients, no dynamic code execution paths.",
        "gates",
    )
    builder.add(
        "Hardened",
        "Schema safety",
        "Append-only checksummed migrations refuse silent downgrades from newer vaults.",
        "v5",
    )
    builder.add(
        "Documentation",
        "Release guide",
        "docs/v3/release.md consolidates quickstart, golden paths, gates, and file content.",
        "B14",
    )
    return builder


def build_migration_notes() -> MigrationNoteBuilder:
    """Build the proposed V3 migration notes."""
    builder = MigrationNoteBuilder()
    builder.add(
        "4.x",
        "5",
        "Schema v5 tables",
        "Run the checksummed, idempotent migration chain once at vault open.",
        note="All V3 tables use the v3_ prefix; existing V2 tables are untouched.",
    )
    builder.add(
        "5",
        "5.0.0",
        "API envelope clients",
        "Switch clients to read { data, meta } and stable error codes.",
        note="The V3 client helper performs envelope decoding and typed errors.",
    )
    builder.add(
        "5.0.0",
        "5.0.0-release",
        "Capability review",
        "Confirm enabled capabilities before enabling extensions or automation.",
        automated=False,
        note="Offline-only and redaction defaults remain enabled.",
    )
    builder.add(
        "5.0.0-release",
        "5.0.1",
        "Release telemetry check",
        "Run the release smoke suite on every branch ref and archive the report.",
        note="No network calls or telemetry are introduced by the release tooling.",
    )
    return builder


def build_release_note(router: V3Router | None = None) -> str:
    """Render a short release note with route coverage."""
    route_count = len(router.routes()) if router is not None else 0
    return "\n".join(
        [
            "# RedScribe V3 release note",
            "",
            "V3 is additive: V2 behaviour and routes are preserved.",
            "",
            "- Release: 3.0.0",
            f"- Registered routes in this run: {route_count}",
            "- Golden path: capture -> finding -> evidence -> report -> export -> import -> merge",
            "- Offline, local-first, and free of runtime dependencies",
        ]
    )
