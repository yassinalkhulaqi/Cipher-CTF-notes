"""Keyboard shortcut registry, parsing, validation, and conflict detection."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.a11y.models import (
    FocusMode,
    Shortcut,
    ShortcutConflict,
    ShortcutReport,
)

MODIFIER_KEYS: tuple[str, ...] = ("ctrl", "alt", "shift", "meta")
KEY_ALIASES: dict[str, str] = {
    "control": "ctrl",
    "command": "meta",
    "cmd": "meta",
    "option": "alt",
    "escape": "esc",
    "esc": "esc",
    "return": "enter",
    "del": "delete",
    "spacebar": "space",
    " ": "space",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
}
KEY_PATTERN = re.compile(
    r"^[a-z0-9]$|^f([1-9]|1[0-2])$|^(up|down|left|right|home|end|pageup|pagedown|enter|esc|tab|space|delete|backspace|insert|pause|capslock)$"
)


@dataclass(frozen=True, slots=True)
class ParsedBinding:
    """A normalized keyboard binding."""

    keys: tuple[str, ...]
    modifiers: tuple[str, ...]
    key: str
    sequence: int = 0

    @property
    def binding(self) -> str:
        return "+".join(self.keys)

    def as_dict(self) -> dict[str, Any]:
        return {
            "keys": list(self.keys),
            "modifiers": list(self.modifiers),
            "key": self.key,
            "sequence": self.sequence,
            "binding": self.binding,
        }


def normalize_key(value: str) -> str:
    """Normalize one key token to its canonical lowercase name."""
    lowered = value.strip().lower()
    return KEY_ALIASES.get(lowered, lowered)


def normalize_binding(value: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize a binding string or token list."""
    parts = re.split(r"\s*\+\s*|\s+", value.strip()) if isinstance(value, str) else list(value)
    normalized: list[str] = []
    for part in parts:
        key = normalize_key(part)
        if key and key not in normalized:
            normalized.append(key)
    ordered_modifiers = [key for key in MODIFIER_KEYS if key in normalized]
    other_keys = [key for key in normalized if key not in MODIFIER_KEYS]
    return (*ordered_modifiers, *other_keys)


def parse_binding(value: str | Sequence[str]) -> ParsedBinding:
    """Parse a binding into modifiers and a primary key."""
    keys = normalize_binding(value)
    if not keys:
        raise ValueError("Shortcut binding cannot be empty")
    modifiers = tuple(key for key in keys if key in MODIFIER_KEYS)
    others = tuple(key for key in keys if key not in MODIFIER_KEYS)
    if not others:
        raise ValueError("Shortcut binding needs a non-modifier key")
    return ParsedBinding(keys=keys, modifiers=modifiers, key=others[-1])


def unknown_keys(binding: ParsedBinding) -> tuple[str, ...]:
    """Return keys in a binding that are not recognized."""
    return tuple(
        key for key in binding.keys if key not in MODIFIER_KEYS and not KEY_PATTERN.match(key)
    )


def format_binding(value: str | Sequence[str], *, platform: str = "desktop") -> str:
    """Format a binding for display in the UI."""
    parsed = parse_binding(value)
    labels = {
        "ctrl": "Ctrl" if platform != "mac" else "⌘",
        "meta": "⌘" if platform == "mac" else "Win",
        "alt": "Alt" if platform != "mac" else "⌥",
        "shift": "Shift" if platform != "mac" else "⇧",
    }
    parts = [
        labels.get(key, key.upper() if len(key) == 1 else key.capitalize()) for key in parsed.keys
    ]
    return "+".join(parts)


def binding_conflict(first: Shortcut, second: Shortcut) -> bool:
    """Return whether two active shortcuts conflict."""
    if not first.enabled or not second.enabled or first.sequence != second.sequence:
        return False
    if first.scope != second.scope and FocusMode.GLOBAL not in (first.scope, second.scope):
        return False
    return parse_binding(first.keys).binding == parse_binding(second.keys).binding


class ShortcutRegistry:
    """An ordered collection of shortcuts with validation helpers."""

    def __init__(self, shortcuts: Iterable[Shortcut] = ()) -> None:
        self._shortcuts: dict[str, Shortcut] = {}
        for shortcut in shortcuts:
            self.add(shortcut)

    def __len__(self) -> int:
        return len(self._shortcuts)

    def __contains__(self, action: str) -> bool:
        return action in self._shortcuts

    def __iter__(self) -> Iterable[Shortcut]:
        return iter(self.values())

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._shortcuts))

    def get(self, action: str) -> Shortcut | None:
        return self._shortcuts.get(action)

    def values(self) -> list[Shortcut]:
        return sorted(self._shortcuts.values(), key=lambda item: (item.scope.value, item.action))

    def add(self, shortcut: Shortcut) -> Shortcut:
        """Add or replace a shortcut."""
        self._shortcuts[shortcut.action] = shortcut
        return shortcut

    def remove(self, action: str) -> Shortcut | None:
        """Remove a shortcut by action name."""
        return self._shortcuts.pop(action, None)

    def update_keys(self, action: str, keys: str | Sequence[str], *, sequence: int = 0) -> Shortcut:
        """Update the binding for an existing shortcut."""
        current = self._shortcuts.get(action)
        if current is None:
            raise KeyError(f"Unknown shortcut action: {action}")
        replacement = Shortcut(
            action=current.action,
            keys=normalize_binding(keys),
            label=current.label,
            scope=current.scope,
            description=current.description,
            enabled=current.enabled,
            sequence=sequence,
        )
        self._shortcuts[action] = replacement
        return replacement

    def set_enabled(self, action: str, enabled: bool) -> Shortcut:
        """Enable or disable a shortcut."""
        current = self._shortcuts.get(action)
        if current is None:
            raise KeyError(f"Unknown shortcut action: {action}")
        replacement = Shortcut(
            action=current.action,
            keys=current.keys,
            label=current.label,
            scope=current.scope,
            description=current.description,
            enabled=enabled,
            sequence=current.sequence,
        )
        self._shortcuts[action] = replacement
        return replacement

    def find(
        self, pressed: str | Sequence[str], *, scope: FocusMode | None = None
    ) -> list[Shortcut]:
        """Return shortcuts matching a pressed binding."""
        normalized = normalize_binding(pressed)
        result: list[Shortcut] = []
        for shortcut in self.values():
            if not shortcut.enabled:
                continue
            if scope is not None and shortcut.scope not in (scope, FocusMode.GLOBAL):
                continue
            if normalize_binding(shortcut.keys) == normalized:
                result.append(shortcut)
        return result

    def conflicts(self) -> tuple[ShortcutConflict, ...]:
        """Find all binding conflicts in the registry."""
        result: list[ShortcutConflict] = []
        values = self.values()
        for index, first in enumerate(values):
            for second in values[index + 1 :]:
                if not binding_conflict(first, second):
                    continue
                result.append(
                    ShortcutConflict(
                        first=first.action,
                        second=second.action,
                        binding=format_binding(first.keys),
                        scope=first.scope if first.scope != FocusMode.GLOBAL else second.scope,
                        message=f"{first.label} conflicts with {second.label}",
                    )
                )
        return tuple(result)

    def validate(self) -> ShortcutReport:
        """Validate every shortcut and detect conflicts."""
        problems: dict[str, tuple[str, ...]] = {}
        for shortcut in self.values():
            parsed = parse_binding(shortcut.keys)
            missing = unknown_keys(parsed)
            if missing:
                problems[shortcut.action] = missing
        return ShortcutReport(
            shortcuts=tuple(self.values()),
            conflicts=self.conflicts(),
            unknown_keys=problems,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "shortcuts": [shortcut.as_dict() for shortcut in self.values()],
            "count": len(self._shortcuts),
        }

    def to_payload(self) -> dict[str, list[str]]:
        """Serialize shortcut bindings for preference storage."""
        return {action: list(shortcut.keys) for action, shortcut in sorted(self._shortcuts.items())}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ShortcutRegistry:
        """Build a registry from stored binding data."""
        registry = cls()
        for action, raw in payload.items():
            if isinstance(raw, Mapping):
                keys = raw.get("keys") or []
                label = str(raw.get("label") or action)
                scope_raw = str(raw.get("scope") or FocusMode.GLOBAL.value)
            else:
                keys = raw
                label = action
                scope_raw = FocusMode.GLOBAL.value
            if not isinstance(keys, Sequence) or isinstance(keys, str):
                continue
            try:
                scope = FocusMode(scope_raw)
            except ValueError:
                scope = FocusMode.GLOBAL
            registry.add(
                Shortcut(
                    action=str(action),
                    keys=normalize_binding(keys),
                    label=label,
                    scope=scope,
                )
            )
        return registry


def default_shortcuts() -> ShortcutRegistry:
    """Return the built-in RedScribe shortcut registry."""
    definitions = (
        ("command_palette", ("Ctrl", "P"), "Quick switch", FocusMode.GLOBAL),
        ("search", ("Ctrl", "Shift", "F"), "Full-text search", FocusMode.GLOBAL),
        ("dashboard", ("Ctrl", "Shift", "D"), "Dashboard", FocusMode.GLOBAL),
        ("snippets", ("Ctrl", "Shift", "S"), "Snippet library", FocusMode.GLOBAL),
        ("graph", ("Ctrl", "Shift", "G"), "Vault graph", FocusMode.GLOBAL),
        ("timeline", ("Ctrl", "Shift", "T"), "Timeline", FocusMode.GLOBAL),
        ("quick_capture", ("Ctrl", "Shift", "Q"), "Quick capture", FocusMode.GLOBAL),
        ("flag_intel", ("Ctrl", "Shift", "I"), "Flag intelligence", FocusMode.GLOBAL),
        ("shortcut_help", ("F1",), "Keyboard shortcuts", FocusMode.GLOBAL),
        ("new_note", ("Ctrl", "N"), "New note", FocusMode.GLOBAL),
        ("new_folder", ("Ctrl", "Shift", "N"), "New folder", FocusMode.GLOBAL),
        ("save", ("Ctrl", "S"), "Save now", FocusMode.EDITOR),
        ("pin_note", ("Ctrl", "Shift", "P"), "Pin or unpin note", FocusMode.GLOBAL),
        ("properties", ("F2",), "Note properties", FocusMode.SIDEBAR),
        ("trash", ("Delete",), "Move to trash", FocusMode.SIDEBAR),
        ("view_mode", ("Ctrl", "E"), "Cycle view mode", FocusMode.GLOBAL),
        ("inspector", ("Ctrl", "Shift", "J"), "Toggle inspector", FocusMode.GLOBAL),
        ("sidebar", ("Ctrl", "Shift", "B"), "Toggle sidebar", FocusMode.GLOBAL),
        ("settings", ("Ctrl", ","), "Settings", FocusMode.GLOBAL),
        ("focus_mode", ("Ctrl", "Shift", "L"), "Toggle focus mode", FocusMode.GLOBAL),
        ("close_dialog", ("Esc",), "Close dialog", FocusMode.DIALOG),
        ("find", ("Ctrl", "F"), "Find in note", FocusMode.EDITOR),
        ("replace", ("Ctrl", "H"), "Find and replace", FocusMode.EDITOR),
        ("bold", ("Ctrl", "B"), "Bold", FocusMode.EDITOR),
        ("italic", ("Ctrl", "I"), "Italic", FocusMode.EDITOR),
        ("inline_code", ("Ctrl", "K"), "Inline code", FocusMode.EDITOR),
        ("strike", ("Ctrl", "Shift", "X"), "Strikethrough", FocusMode.EDITOR),
        ("indent", ("Tab",), "Indent selection", FocusMode.EDITOR),
        ("outdent", ("Shift", "Tab"), "Outdent selection", FocusMode.EDITOR),
    )
    return ShortcutRegistry(
        Shortcut(
            action=action,
            keys=normalize_binding(keys),
            label=label,
            scope=scope,
        )
        for action, keys, label, scope in definitions
    )


def suggest_binding(registry: ShortcutRegistry, action: str, *, scope: FocusMode) -> str:
    """Suggest an unused binding for an action."""
    existing = {parse_binding(shortcut.keys).binding for shortcut in registry.values()}
    candidates = (
        ("Ctrl", "Alt", "A"),
        ("Ctrl", "Alt", "B"),
        ("Ctrl", "Alt", "C"),
        ("Ctrl", "Shift", "Alt", "A"),
        ("Alt", "F1"),
        ("Alt", "F2"),
        ("Alt", "F3"),
        ("Ctrl", "Shift", "0"),
        ("Ctrl", "Shift", "1"),
        ("Ctrl", "Shift", "2"),
    )
    for candidate in candidates:
        binding = normalize_binding(candidate)
        if parse_binding(binding).binding not in existing:
            registry.add(
                Shortcut(
                    action=action,
                    keys=binding,
                    label=action.replace("_", " ").title(),
                    scope=scope,
                )
            )
            return format_binding(binding)
    raise ValueError(f"No free binding available for {action}")


def shortcut_groups(registry: ShortcutRegistry) -> dict[str, list[dict[str, Any]]]:
    """Group shortcuts by scope for settings display."""
    groups: dict[str, list[dict[str, Any]]] = {scope.value: [] for scope in FocusMode}
    for shortcut in registry.values():
        groups[shortcut.scope.value].append(shortcut.as_dict())
    return groups
