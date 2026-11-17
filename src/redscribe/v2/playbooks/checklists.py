"""Checklist tracking and progress calculations for playbook runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.playbooks.errors import InvalidStateError
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    ChecklistStateValue,
    Values,
)

_VALID_STATES = frozenset(item.value for item in ChecklistStateValue)
_SETTLED = frozenset({ChecklistStateValue.DONE.value, ChecklistStateValue.SKIPPED.value})


@dataclass(frozen=True, slots=True)
class ChecklistProgress:
    """Aggregate completion statistics for a checklist."""

    total: int
    done: int
    skipped: int
    blocked: int
    required_total: int
    required_done: int
    percent: int

    @property
    def complete(self) -> bool:
        return self.required_done >= self.required_total

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "done": self.done,
            "skipped": self.skipped,
            "blocked": self.blocked,
            "required_total": self.required_total,
            "required_done": self.required_done,
            "percent": self.percent,
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class ChecklistTracker:
    """An immutable checklist state snapshot with pure update helpers."""

    items: tuple[ChecklistItem, ...] = ()
    states: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "states", {**self.states})
        object.__setattr__(self, "notes", {**self.notes})

    @classmethod
    def from_items(
        cls,
        items: tuple[ChecklistItem, ...] | list[ChecklistItem],
        state: dict[str, str] | None = None,
        notes: dict[str, str] | None = None,
    ) -> ChecklistTracker:
        """Build a tracker with default pending states."""
        initial = {item.id: ChecklistStateValue.PENDING.value for item in items}
        if state:
            for key, value in state.items():
                if key in initial and value in _VALID_STATES:
                    initial[key] = value
        return cls(tuple(items), initial, dict(notes or {}))

    @classmethod
    def from_dict(
        cls, payload: Any, *, items: tuple[ChecklistItem, ...] | list[ChecklistItem] = ()
    ) -> ChecklistTracker:
        """Restore a tracker from an API payload."""
        if not isinstance(payload, dict):
            return cls.from_items(items)
        raw_state = payload.get("states", payload.get("checklist", {}))
        raw_notes = payload.get("notes", {})
        state = (
            {str(key): str(value) for key, value in raw_state.items()}
            if isinstance(raw_state, dict)
            else {}
        )
        notes = (
            {str(key): str(value) for key, value in raw_notes.items()}
            if isinstance(raw_notes, dict)
            else {}
        )
        return cls.from_items(items, state=state, notes=notes)

    def item(self, item_id: str) -> ChecklistItem | None:
        """Return an item by id."""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def state(self, item_id: str) -> str:
        """Return the current state of an item."""
        return self.states.get(item_id, ChecklistStateValue.PENDING.value)

    def set_state(self, item_id: str, value: ChecklistStateValue | str) -> ChecklistTracker:
        """Return a tracker with one item state updated."""
        normalized = value.value if isinstance(value, ChecklistStateValue) else str(value)
        if normalized not in _VALID_STATES:
            raise InvalidStateError(f"Unknown checklist state: {normalized}")
        if self.item(item_id) is None:
            raise InvalidStateError(f"Unknown checklist item: {item_id}")
        states = dict(self.states)
        states[item_id] = normalized
        return ChecklistTracker(self.items, states, self.notes)

    def toggle(self, item_id: str) -> ChecklistTracker:
        """Toggle an item between done and pending."""
        next_state = (
            ChecklistStateValue.PENDING
            if self.state(item_id) == ChecklistStateValue.DONE.value
            else ChecklistStateValue.DONE
        )
        return self.set_state(item_id, next_state)

    def set_note(self, item_id: str, note: str) -> ChecklistTracker:
        """Return a tracker with one item note updated."""
        if self.item(item_id) is None:
            raise InvalidStateError(f"Unknown checklist item: {item_id}")
        notes = dict(self.notes)
        notes[item_id] = note
        return ChecklistTracker(self.items, self.states, notes)

    def apply_conditions(self, values: Values) -> ChecklistTracker:
        """Block items whose conditions are not satisfied."""
        states = dict(self.states)
        for item in self.items:
            if item.condition is not None and not item.condition.matches(values):
                if states.get(item.id) == ChecklistStateValue.PENDING.value:
                    states[item.id] = ChecklistStateValue.BLOCKED.value
            elif states.get(item.id) == ChecklistStateValue.BLOCKED.value:
                states[item.id] = ChecklistStateValue.PENDING.value
        return ChecklistTracker(self.items, states, self.notes)

    def progress(self) -> ChecklistProgress:
        """Compute completion statistics."""
        done = 0
        skipped = 0
        blocked = 0
        required_total = 0
        required_done = 0
        for item in self.items:
            state = self.state(item.id)
            if state == ChecklistStateValue.DONE.value:
                done += 1
            elif state == ChecklistStateValue.SKIPPED.value:
                skipped += 1
            elif state == ChecklistStateValue.BLOCKED.value:
                blocked += 1
            if item.required:
                required_total += 1
                if state in _SETTLED:
                    required_done += 1
        percent = round(done / len(self.items) * 100) if self.items else 100
        return ChecklistProgress(
            total=len(self.items),
            done=done,
            skipped=skipped,
            blocked=blocked,
            required_total=required_total,
            required_done=required_done,
            percent=percent,
        )

    def incomplete_required(self) -> tuple[str, ...]:
        """Return ids of required items that are not settled."""
        return tuple(
            item.id for item in self.items if item.required and self.state(item.id) not in _SETTLED
        )

    def visible_items(self) -> tuple[ChecklistItem, ...]:
        """Return items sorted by their current state for display."""
        order = {
            ChecklistStateValue.PENDING.value: 0,
            ChecklistStateValue.BLOCKED.value: 1,
            ChecklistStateValue.DONE.value: 2,
            ChecklistStateValue.SKIPPED.value: 3,
        }
        return tuple(sorted(self.items, key=lambda item: (order[self.state(item.id)], item.id)))

    def as_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "states": dict(self.states),
            "notes": dict(self.notes),
            "progress": self.progress().as_dict(),
        }
        if include_items:
            data["items"] = [item.as_dict() for item in self.items]
        return data


def merge_trackers(primary: ChecklistTracker, secondary: ChecklistTracker) -> ChecklistTracker:
    """Merge two trackers, preferring settled primary states."""
    states = dict(secondary.states)
    for key, value in primary.states.items():
        if value in _SETTLED or key not in states:
            states[key] = value
    notes = {**secondary.notes, **primary.notes}
    return ChecklistTracker(primary.items, states, notes)


def required_ids(items: tuple[ChecklistItem, ...] | list[ChecklistItem]) -> tuple[str, ...]:
    """Return the ids of all required checklist items."""
    return tuple(item.id for item in items if item.required)


def checklist_summary(items: tuple[ChecklistItem, ...] | list[ChecklistItem]) -> dict[str, Any]:
    """Return compact metadata for a checklist."""
    return {
        "total": len(items),
        "required": len(required_ids(items)),
        "item_ids": [item.id for item in items],
    }
