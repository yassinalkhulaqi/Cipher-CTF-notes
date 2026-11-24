"""Conflict-resistant registry of playbook documents."""

from __future__ import annotations

from redscribe.v3.automation.errors import PlaybookValidationError
from redscribe.v3.automation.types import PlaybookDefinition


class PlaybookRegistry:
    """In-memory registry with stable ordering and no global state."""

    def __init__(self) -> None:
        self._playbooks: dict[str, PlaybookDefinition] = {}

    def add(self, playbook: PlaybookDefinition) -> PlaybookDefinition:
        """Register a playbook, rejecting duplicate ids."""
        if playbook.id in self._playbooks:
            raise PlaybookValidationError(f"Playbook already registered: {playbook.id}", path="id")
        self._playbooks[playbook.id] = playbook
        return playbook

    def replace(self, playbook: PlaybookDefinition) -> PlaybookDefinition:
        """Replace a playbook with a new version."""
        if playbook.id not in self._playbooks:
            raise PlaybookValidationError(f"Unknown playbook: {playbook.id}", path="id")
        self._playbooks[playbook.id] = playbook
        return playbook

    def get(self, ref: str) -> PlaybookDefinition:
        """Look up a playbook by id or ``playbook:<id>`` reference."""
        key = ref.split(":", 1)[1] if ref.startswith("playbook:") else ref
        playbook = self._playbooks.get(key)
        if playbook is None:
            raise PlaybookValidationError(f"Unknown playbook: {ref}", path="playbook_ref")
        return playbook

    def find(self, ref: str) -> PlaybookDefinition | None:
        """Look up a playbook without raising."""
        key = ref.split(":", 1)[1] if ref.startswith("playbook:") else ref
        return self._playbooks.get(key)

    def remove(self, ref: str) -> bool:
        """Remove a playbook, returning whether it existed."""
        key = ref.split(":", 1)[1] if ref.startswith("playbook:") else ref
        return self._playbooks.pop(key, None) is not None

    def list(self) -> tuple[PlaybookDefinition, ...]:
        """Return all playbooks in stable order."""
        return tuple(
            self._playbooks[key]
            for key in sorted(self._playbooks, key=lambda item: item.casefold())
        )

    def snapshot(self) -> tuple[dict[str, object], ...]:
        """Return serializable playbook summaries."""
        return tuple(playbook.as_dict() for playbook in self.list())

    def __len__(self) -> int:
        """Return the number of registered playbooks."""
        return len(self._playbooks)
