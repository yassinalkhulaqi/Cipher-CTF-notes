"""Complete keyboard map export and lookup tests."""

from __future__ import annotations

from redscribe.v2.a11y.models import FocusMode
from redscribe.v3.a11y_refinement.keyboard_map import (
    GROUP_LABELS,
    V3_SHORTCUTS,
    apply_overrides,
    bindings_for_group,
    complete_registry,
    export_keyboard_map,
    find_binding,
    focus_sequence,
    group_for,
    help_lines,
    next_available_binding,
    parse_map_binding,
)


def test_complete_registry_includes_v2_and_v3() -> None:
    registry = complete_registry()
    assert len(registry) >= 40
    assert "save" in registry
    assert "a11y_refinement" in registry
    assert "toggle_motion" in registry
    assert len(V3_SHORTCUTS) == 18


def test_export_contains_every_binding_without_conflicts() -> None:
    keyboard_map = export_keyboard_map()
    assert keyboard_map.complete is True
    assert keyboard_map.conflicts == ()
    assert len(keyboard_map.bindings) == len(complete_registry())
    assert all(item.display for item in keyboard_map.bindings)
    assert all(item.group for item in keyboard_map.bindings)


def test_export_groups_and_coverage() -> None:
    keyboard_map = export_keyboard_map()
    assert "navigation" in keyboard_map.groups
    assert "editing" in keyboard_map.groups
    assert sum(keyboard_map.coverage.values()) == len(keyboard_map.bindings)
    assert "command_center" in keyboard_map.groups["navigation"]
    assert "toggle_rtl" in keyboard_map.groups["display"]


def test_platform_display_formatting() -> None:
    desktop = export_keyboard_map(platform="desktop")
    mac = export_keyboard_map(platform="mac")
    save_desktop = next(item for item in desktop.bindings if item.action == "save")
    save_mac = next(item for item in mac.bindings if item.action == "save")
    assert save_desktop.display == "Ctrl+S"
    assert "⌘" in save_mac.display


def test_overrides_change_binding_and_can_disable() -> None:
    keyboard_map = export_keyboard_map(
        overrides={"save": {"keys": ["Ctrl", "Alt", "S"], "enabled": False}}
    )
    save = next(item for item in keyboard_map.bindings if item.action == "save")
    assert save.keys == ("ctrl", "alt", "s")
    assert save.enabled is False
    matches = find_binding(keyboard_map, ["ctrl", "alt", "s"])
    assert all(item.action != "save" for item in matches)


def test_override_ignores_unknown_actions() -> None:
    registry = complete_registry()
    updated = apply_overrides(registry, {"not_an_action": ["Ctrl", "Z"]})
    assert len(updated) == len(registry)


def test_find_binding_respects_scope() -> None:
    keyboard_map = export_keyboard_map()
    matches = find_binding(keyboard_map, ["ctrl", "s"], scope="editor")
    assert len(matches) == 1
    assert matches[0].action == "save"
    assert find_binding(keyboard_map, ["ctrl", "s"], scope="dialog") == ()
    assert find_binding(keyboard_map, ["ctrl", "shift", "a"])[0].action == "a11y_refinement"


def test_lookup_normalizes_alias_keys() -> None:
    keyboard_map = export_keyboard_map()
    matches = find_binding(keyboard_map, "Control+S")
    assert matches
    assert matches[0].action == "save"


def test_help_lines_are_localized_and_ordered() -> None:
    keyboard_map = export_keyboard_map(locale="pt-BR")
    lines = help_lines(keyboard_map, locale="pt-BR")
    assert len(lines) == len(keyboard_map.bindings)
    assert any(":" in line for line in lines)
    focus = focus_sequence(keyboard_map)
    assert focus[0] == "a11y_refinement"
    assert len(set(focus)) == len(focus)


def test_group_filtering_and_labels() -> None:
    keyboard_map = export_keyboard_map()
    navigation = bindings_for_group(keyboard_map, "navigation")
    assert len(navigation) == 12
    assert all(item.group == "navigation" for item in navigation)
    assert GROUP_LABELS["navigation"] == "Surface navigation"
    assert group_for("new_note", FocusMode.GLOBAL, frozenset()) == "global"


def test_focus_sequence_can_filter_surface() -> None:
    keyboard_map = export_keyboard_map()
    focus = focus_sequence(keyboard_map, surface="navigation")
    assert focus
    assert all("navigation" in item or item in keyboard_map.groups["navigation"] for item in focus)


def test_next_available_binding_does_not_mutate_registry() -> None:
    registry = complete_registry()
    before = len(registry)
    suggestion = next_available_binding(registry, "brand_new_action", scope=FocusMode.GLOBAL)
    assert "+" in suggestion
    assert len(registry) == before


def test_parse_map_binding_metadata() -> None:
    parsed = parse_map_binding("Ctrl+Shift+A")
    assert parsed["keys"] == ["ctrl", "shift", "a"]
    assert parsed["modifiers"] == ["ctrl", "shift"]
    assert parsed["key"] == "a"
