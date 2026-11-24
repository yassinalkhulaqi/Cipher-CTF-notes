"""Additive registry for entity kinds and their display metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from redscribe.v3.entities.types import ENTITY_KINDS, EntityKind

_UNREGISTERED_COLOR: Final[str] = "#64748b"


@dataclass(frozen=True, slots=True)
class KindSpec:
    """Presentation metadata for one entity kind."""

    kind: EntityKind | str
    label: str
    plural: str
    color: str
    icon: str
    order: int


_DEFAULT_SPECS: tuple[KindSpec, ...] = (
    KindSpec(EntityKind.NOTE, "Note", "Notes", "#38bdf8", "file-text", 10),
    KindSpec(EntityKind.FOLDER, "Folder", "Folders", "#a78bfa", "folder", 20),
    KindSpec(EntityKind.TARGET, "Target", "Targets", "#f472b6", "crosshair", 30),
    KindSpec(EntityKind.FINDING, "Finding", "Findings", "#fb7185", "alert", 40),
    KindSpec(EntityKind.EVIDENCE, "Evidence", "Evidence", "#34d399", "paperclip", 50),
    KindSpec(EntityKind.PLAYBOOK, "Playbook", "Playbooks", "#fbbf24", "list", 60),
    KindSpec(EntityKind.RUN, "Run", "Runs", "#f59e0b", "play", 70),
    KindSpec(EntityKind.REPORT, "Report", "Reports", "#60a5fa", "book", 80),
    KindSpec(EntityKind.SECTION, "Section", "Sections", "#94a3b8", "layout", 90),
    KindSpec(EntityKind.ACTIVITY, "Activity", "Activity", "#22d3ee", "activity", 100),
    KindSpec(EntityKind.EXTENSION, "Extension", "Extensions", "#c084fc", "puzzle", 110),
    KindSpec(EntityKind.SNIPPET, "Snippet", "Snippets", "#4ade80", "terminal", 120),
)


def _key(kind: EntityKind | str) -> str:
    """Normalize a kind to its registry key."""
    return kind.value if isinstance(kind, EntityKind) else kind.strip().casefold()


class EntityKindRegistry:
    """Immutable-by-convention registry that can be extended additively.

    Feature branches may register additional kinds; they never edit a central
    switch statement. Lookups fall back to a generated spec so an early branch
    can render a kind introduced by a later branch.
    """

    def __init__(self, specs: tuple[KindSpec, ...] = _DEFAULT_SPECS) -> None:
        self._specs: dict[str, KindSpec] = {_key(spec.kind): spec for spec in specs}

    def register(self, spec: KindSpec) -> None:
        """Register or replace a kind specification."""
        self._specs[_key(spec.kind)] = spec

    def get(self, kind: EntityKind | str) -> KindSpec:
        """Return a spec for a kind, generating a fallback when missing."""
        key = _key(kind)
        existing = self._specs.get(key)
        if existing is not None:
            return existing
        return KindSpec(
            kind=key,
            label=key.title(),
            plural=f"{key.title()}s",
            color=_UNREGISTERED_COLOR,
            icon="circle",
            order=999,
        )

    def has(self, kind: EntityKind | str) -> bool:
        """Return whether a kind has an explicitly registered spec."""
        return _key(kind) in self._specs

    def all(self) -> tuple[KindSpec, ...]:
        """Return all specs in display order."""
        return tuple(sorted(self._specs.values(), key=lambda spec: (spec.order, _key(spec.kind))))

    def labels(self) -> dict[str, str]:
        """Return a wire-friendly kind to label mapping."""
        return {key: spec.label for key, spec in self._specs.items()}

    def colors(self) -> dict[str, str]:
        """Return a wire-friendly kind to color mapping."""
        return {key: spec.color for key, spec in self._specs.items()}

    def known_kinds(self) -> tuple[str, ...]:
        """Return every registered kind key."""
        return tuple(sorted(self._specs))

    def validate(self) -> tuple[str, ...]:
        """Return problems detected in the registry."""
        problems: list[str] = []
        for kind in ENTITY_KINDS:
            if kind not in self._specs:
                problems.append(f"missing spec for {kind}")
        return tuple(problems)


default_registry = EntityKindRegistry()
