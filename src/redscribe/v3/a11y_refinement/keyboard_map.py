"""Complete keyboard map export for all V2 and V3 surfaces.

The V2 shortcut registry stays authoritative for bindings and validation.
This module adds V3 surface navigation entries, grouping, localized help text,
and a conflict-free export consumed by the refined keyboard UI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.a11y.models import FocusMode, Shortcut
from redscribe.v2.a11y.shortcuts import (
    default_shortcuts,
    format_binding,
    normalize_binding,
    parse_binding,
    suggest_binding,
)
from redscribe.v3.a11y_refinement.formatting import translate
from redscribe.v3.a11y_refinement.models import KeyboardBinding, KeyboardMap

V3_SHORTCUTS: tuple[tuple[str, tuple[str, ...], str, FocusMode, str], ...] = (
    (
        "command_center",
        ("Ctrl", "Shift", "K"),
        "Open command center",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "findings_studio",
        ("Ctrl", "Shift", "V"),
        "Open finding studio",
        FocusMode.GLOBAL,
        "navigation",
    ),
    ("evidence_lab", ("Ctrl", "Shift", "E"), "Open evidence lab", FocusMode.GLOBAL, "navigation"),
    (
        "graph_workbench",
        ("Ctrl", "Shift", "H"),
        "Open graph workbench",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "search_intelligence",
        ("Ctrl", "Shift", "R"),
        "Open search intelligence",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "playbook_automation",
        ("Ctrl", "Shift", "Y"),
        "Open playbook automation",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "report_designer",
        ("Ctrl", "Shift", "W"),
        "Open report designer",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "timeline_view",
        ("Ctrl", "Shift", "M"),
        "Open activity timeline",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "sync_view",
        ("Ctrl", "Shift", "U"),
        "Open sync and portability",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "security_view",
        ("Ctrl", "Shift", "O"),
        "Open security vault",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "performance_hud",
        ("Ctrl", "Shift", "2"),
        "Open performance HUD",
        FocusMode.GLOBAL,
        "navigation",
    ),
    (
        "a11y_refinement",
        ("Ctrl", "Shift", "A"),
        "Open accessibility refinement",
        FocusMode.GLOBAL,
        "navigation",
    ),
    ("next_pane", ("F6",), "Move to next pane", FocusMode.GLOBAL, "focus"),
    ("previous_pane", ("Shift", "F6"), "Move to previous pane", FocusMode.GLOBAL, "focus"),
    ("toggle_rtl", ("Ctrl", "Alt", "D"), "Toggle layout direction", FocusMode.GLOBAL, "display"),
    ("toggle_motion", ("Ctrl", "Alt", "M"), "Cycle motion mode", FocusMode.GLOBAL, "display"),
    (
        "toggle_high_contrast",
        ("Ctrl", "Alt", "H"),
        "Toggle high contrast",
        FocusMode.GLOBAL,
        "display",
    ),
    ("announce_status", ("Ctrl", "Alt", "S"), "Announce current status", FocusMode.GLOBAL, "focus"),
)

GROUP_LABELS: dict[str, str] = {
    "navigation": "Surface navigation",
    "focus": "Focus and announcements",
    "display": "Display and motion",
    "editing": "Editing",
    "global": "Global commands",
    "editor": "Editor",
    "sidebar": "Sidebar",
    "dialog": "Dialogs",
    "reading": "Reading view",
}


def group_for(action: str, scope: FocusMode, v3_actions: frozenset[str]) -> str:
    """Return the help group for one action."""
    if action in v3_actions:
        for item in V3_SHORTCUTS:
            if item[0] == action:
                return item[4]
    if scope == FocusMode.EDITOR:
        return "editing"
    return str(scope.value)


def complete_registry() -> Any:
    """Build a registry containing every V2 and V3 binding."""
    registry = default_shortcuts()
    for action, keys, label, scope, _group in V3_SHORTCUTS:
        registry.add(
            Shortcut(
                action=action,
                keys=normalize_binding(keys),
                label=label,
                scope=scope,
                description=f"V3 {scope.value} shortcut",
            )
        )
    return registry


def apply_overrides(registry: Any, overrides: Mapping[str, Any] | None) -> Any:
    """Apply requested key overrides to a copy of a registry."""
    if not overrides:
        return registry
    from copy import deepcopy

    updated = deepcopy(registry)
    for action, raw in overrides.items():
        name = str(action)
        if name not in updated:
            continue
        if isinstance(raw, Mapping):
            keys = raw.get("keys") or []
            enabled = bool(raw.get("enabled", True))
        else:
            keys = raw
            enabled = True
        if isinstance(keys, str) or not isinstance(keys, Sequence):
            continue
        updated.update_keys(name, normalize_binding(keys))
        if not enabled:
            updated.set_enabled(name, False)
    return updated


def export_keyboard_map(
    *,
    locale: str = "en",
    platform: str = "desktop",
    overrides: Mapping[str, Any] | None = None,
    registry: Any | None = None,
) -> KeyboardMap:
    """Export a complete, validated keyboard map."""
    source = registry if registry is not None else complete_registry()
    resolved = apply_overrides(source, overrides)
    report = resolved.validate()
    v3_actions = frozenset(item[0] for item in V3_SHORTCUTS)
    bindings: list[KeyboardBinding] = []
    for shortcut in report.shortcuts:
        bindings.append(
            KeyboardBinding(
                action=shortcut.action,
                keys=shortcut.keys,
                label=shortcut.label,
                group=group_for(shortcut.action, shortcut.scope, v3_actions),
                scope=shortcut.scope.value,
                display=format_binding(shortcut.keys, platform=platform),
                enabled=shortcut.enabled,
                sequence=shortcut.sequence,
                description=shortcut.description,
            )
        )
    bindings.sort(key=lambda item: (item.group, item.action))
    groups: dict[str, tuple[str, ...]] = {}
    for binding in bindings:
        groups.setdefault(binding.group, ())
        groups[binding.group] = (*groups[binding.group], binding.action)
    coverage = {group: len(actions) for group, actions in groups.items()}
    conflicts = [item.as_dict() for item in report.conflicts]
    allowed_punctuation = {",", ".", "/", ";", "'", "[", "]"}
    unknown = {
        key: [item for item in value if item not in allowed_punctuation]
        for key, value in report.unknown_keys.items()
    }
    unknown = {key: value for key, value in unknown.items() if value}
    if unknown:
        conflicts.extend(
            {
                "first": key,
                "second": "unknown_key",
                "binding": ",".join(keys),
                "scope": "global",
                "message": f"Unknown keys in {key}",
            }
            for key, keys in unknown.items()
        )
    return KeyboardMap(
        locale=locale,
        platform=platform,
        bindings=tuple(bindings),
        groups=groups,
        conflicts=tuple(conflicts),
        coverage=coverage,
    )


def help_lines(keyboard_map: KeyboardMap, *, locale: str = "en") -> tuple[str, ...]:
    """Return localized help lines for an exported keyboard map."""
    lines: list[str] = []
    for binding in keyboard_map.bindings:
        translated = translate(
            locale,
            "v3.keyboard.binding",
            {"action": binding.label, "binding": binding.display},
        )
        lines.append(translated["message"])
    return tuple(lines)


def find_binding(
    keyboard_map: KeyboardMap,
    pressed: str | Sequence[str],
    *,
    scope: str = "",
) -> tuple[KeyboardBinding, ...]:
    """Resolve a pressed binding against an exported map."""
    normalized = normalize_binding(pressed)
    return tuple(
        item
        for item in keyboard_map.bindings
        if item.enabled
        and item.keys == normalized
        and (not scope or item.scope in {scope, "global"})
    )


def bindings_for_group(keyboard_map: KeyboardMap, group: str) -> tuple[KeyboardBinding, ...]:
    """Return all bindings in one help group."""
    return tuple(item for item in keyboard_map.bindings if item.group == group)


def focus_sequence(keyboard_map: KeyboardMap, *, surface: str = "") -> tuple[str, ...]:
    """Return the logical action order for a keyboard pass."""
    ordered = sorted(
        keyboard_map.bindings,
        key=lambda item: (0 if item.group == "navigation" else 1, item.sequence, item.action),
    )
    if surface:
        ordered = [item for item in ordered if surface in item.action or surface in item.group]
    return tuple(item.action for item in ordered)


def next_available_binding(registry: Any, action: str, *, scope: FocusMode) -> str:
    """Suggest a free binding without mutating the supplied registry."""
    from copy import deepcopy

    probe = deepcopy(registry)
    return suggest_binding(probe, action, scope=scope)


def parse_map_binding(value: str | Sequence[str]) -> dict[str, Any]:
    """Return parsed metadata for a display binding."""
    parsed = parse_binding(value)
    return parsed.as_dict()


__all__ = [
    "GROUP_LABELS",
    "V3_SHORTCUTS",
    "apply_overrides",
    "bindings_for_group",
    "complete_registry",
    "export_keyboard_map",
    "find_binding",
    "focus_sequence",
    "group_for",
    "help_lines",
    "next_available_binding",
    "parse_map_binding",
]
