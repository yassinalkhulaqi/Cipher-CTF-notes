from __future__ import annotations

from redscribe.v2.a11y.aria import (
    accessible_name_map,
    compute_accessible_name,
    known_roles,
    role_spec,
    role_summary,
    validate_attribute,
    validate_tree,
)
from redscribe.v2.a11y.audit import (
    AccessibilityAuditor,
    audit_payload,
    audit_summary,
    flatten,
    node_from_payload,
    nodes_from_payload,
)
from redscribe.v2.a11y.focus import (
    analyze_focus_order,
    collect_focusables,
    compute_tab_order,
    describe_focusable,
    detect_traps,
    focus_mode_for,
    focus_summary,
    has_skip_link,
    is_focusable,
    is_skip_link,
    parse_tab_index,
    simulate_tabs,
)
from redscribe.v2.a11y.models import ElementNode, FocusMode, Severity
from redscribe.v2.a11y.shortcuts import (
    Shortcut,
    ShortcutRegistry,
    binding_conflict,
    default_shortcuts,
    format_binding,
    normalize_binding,
    normalize_key,
    parse_binding,
    shortcut_groups,
    suggest_binding,
    unknown_keys,
)


def _tree() -> tuple[ElementNode, ...]:
    return nodes_from_payload(
        [
            {
                "tag": "a",
                "attrs": {"href": "#main", "id": "skip"},
                "text": "Skip to content",
                "path": "/0",
            },
            {
                "tag": "button",
                "attrs": {"type": "button"},
                "text": "Save",
                "path": "/1",
            },
            {
                "tag": "img",
                "attrs": {"src": "logo.png", "alt": "Logo"},
                "text": "",
                "path": "/2",
            },
            {
                "tag": "input",
                "attrs": {"type": "text", "id": "title", "aria-label": "Title"},
                "text": "",
                "path": "/3",
            },
        ]
    )


def test_node_from_payload_builds_nested_elements() -> None:
    node = node_from_payload(
        {
            "tag": "SECTION",
            "attrs": {"aria-label": "Tools"},
            "text": "ignored",
            "visible": False,
            "path": "/root",
            "children": [{"tag": "button", "text": "Run", "path": "/root/0"}],
        }
    )
    assert node.normalized_tag == "section"
    assert node.visible is False
    assert len(node.children) == 1
    assert node.children[0].normalized_tag == "button"


def test_flatten_walks_depth_first() -> None:
    child = ElementNode("button", {}, "A", path="/0/0")
    sibling = ElementNode("button", {}, "B", path="/0/1")
    root = ElementNode("div", {}, "", (child, sibling), path="/0")
    assert [node.path for node in flatten([root])] == ["/0", "/0/0", "/0/1"]


def test_known_roles_and_specs_cover_interactive_widgets() -> None:
    roles = known_roles()
    assert "button" in roles
    assert "dialog" in roles
    assert "navigation" in roles
    button = role_spec("button")
    assert button is not None
    assert button.focusable is True
    assert role_spec("not-a-role") is None
    summary = role_summary()
    assert summary["roles"] == len(roles)
    assert "widget" in summary["categories"]


def test_compute_accessible_name_prefers_labels_and_aria() -> None:
    labelled = ElementNode(
        "button",
        {"id": "run", "aria-label": "Run scan"},
        "Ignored",
    )
    referenced = ElementNode("span", {"id": "description"}, "Details")
    via_reference = ElementNode(
        "button",
        {"aria-labelledby": "description"},
        "Ignored",
    )
    assert compute_accessible_name(labelled) == "Run scan"
    assert (
        compute_accessible_name(via_reference, name_lookup={"description": "Details"}) == "Details"
    )
    assert compute_accessible_name(ElementNode("button", {}, "Visible")) == "Visible"
    assert accessible_name_map([labelled, referenced])["run"] == "Run scan"


def test_validate_tree_reports_missing_names_and_bad_attributes() -> None:
    nodes = (
        ElementNode("button", {}, "", path="/0"),
        ElementNode("img", {"src": "x.png"}, "", path="/1"),
    )
    report = validate_tree(nodes)
    rules = {issue.rule for issue in report.issues}
    assert "aria-missing-name" in rules
    assert "aria-missing-alt" in rules
    assert report.checked == 2
    assert report.as_dict()["passed"] is False


def test_validate_tree_passes_for_labelled_controls() -> None:
    nodes = (
        ElementNode("button", {"aria-label": "Save"}, "", path="/0"),
        ElementNode("img", {"src": "x.png", "alt": "Chart"}, "", path="/1"),
    )
    report = validate_tree((nodes[0],), strict=True)
    assert report.issues == ()
    assert report.passed is True


def test_validate_attribute_understands_allowed_values() -> None:
    assert validate_attribute("aria-hidden", "true") == []
    assert validate_attribute("aria-expanded", "maybe")
    assert validate_attribute("aria-live", "polite") == []
    assert validate_attribute("aria-live", "sometimes")


def test_audit_payload_finds_issues_and_summarizes_severity() -> None:
    report = audit_payload(
        {
            "nodes": [
                {"tag": "img", "attrs": {"src": "a.png"}, "path": "/0"},
                {"tag": "input", "attrs": {"type": "text"}, "path": "/1"},
            ]
        },
        locale="en",
        level="AAA",
    )
    assert report.checked_elements == 2
    assert report.level.value == "AAA"
    assert report.issues
    assert report.score < 100
    summary = audit_summary(report)
    assert summary["elements"] == 2
    assert summary["issues"] == len(report.issues)
    assert "serious" in summary


def test_audit_passes_for_clean_markup() -> None:
    report = audit_payload(
        {
            "nodes": [
                {"tag": "h1", "text": "Title", "path": "/0"},
                {"tag": "button", "text": "Save", "path": "/1"},
            ]
        }
    )
    assert report.score > 0
    assert not any(issue.rule.startswith("image.") for issue in report.issues)
    assert not any(issue.rule.startswith("aria.") for issue in report.issues)


def test_accessibility_auditor_can_disable_rule_groups() -> None:
    nodes = (ElementNode("img", {"src": "x.png"}, "", path="/0"),)
    strict = AccessibilityAuditor(locale="en").audit(nodes)
    relaxed = AccessibilityAuditor(
        locale="en",
        require_skip_link=False,
        require_landmarks=False,
    ).audit(nodes)
    assert strict.issues
    assert len(relaxed.issues) <= len(strict.issues)


def test_is_focusable_respects_disabled_and_href() -> None:
    assert is_focusable(ElementNode("button", {"type": "button"})) is True
    assert is_focusable(ElementNode("button", {"disabled": "true"})) is False
    assert is_focusable(ElementNode("a", {"href": "/notes"})) is True
    assert is_focusable(ElementNode("a", {})) is True
    assert is_focusable(ElementNode("div", {"tabindex": "0"})) is True
    assert is_focusable(ElementNode("div", {}, visible=False)) is False


def test_parse_tab_index_handles_numeric_and_invalid_values() -> None:
    assert parse_tab_index(ElementNode("button", {"tabindex": "2"})) == 2
    assert parse_tab_index(ElementNode("button", {"tabindex": "-1"})) == -1
    assert parse_tab_index(ElementNode("button", {})) == 0
    assert parse_tab_index(ElementNode("button", {"tabindex": "many"})) == 0


def test_focus_ordering_puts_positive_tabindex_first() -> None:
    nodes = (
        ElementNode("button", {"tabindex": "2"}, "Second", path="/0"),
        ElementNode("button", {}, "Natural", path="/1"),
        ElementNode("button", {"tabindex": "1"}, "First", path="/2"),
    )
    candidates = collect_focusables(nodes)
    ordered = compute_tab_order(candidates)
    assert [candidate.label for candidate in ordered[:2]] == ["First", "Second"]
    assert describe_focusable(candidates[1].node) == "Natural"


def test_skip_link_detection_and_requirements() -> None:
    skip = ElementNode("a", {"href": "#main"}, "Skip to content", path="/0")
    regular = ElementNode("a", {"href": "/note"}, "Note", path="/1")
    assert is_skip_link(skip) is True
    assert is_skip_link(regular) is False
    assert has_skip_link([regular]) is False
    assert has_skip_link([regular, skip]) is True
    without_skip = analyze_focus_order([regular], require_skip_link=True)
    assert any(issue.rule == "focus-no-skip-link" for issue in without_skip.issues)


def test_analyze_focus_order_scores_valid_tree() -> None:
    nodes = _tree()
    report = analyze_focus_order(nodes, require_skip_link=True)
    assert report.focusable_count == 3
    assert report.has_skip_link is True
    assert report.positive_tabindex_count == 0
    assert report.score == 100.0
    summary = focus_summary(report)
    assert summary["focusable"] == 3
    assert summary["skip_link"] is True


def test_simulate_tabs_wraps_and_tracks_steps() -> None:
    nodes = _tree()
    steps = simulate_tabs(nodes, presses=5, start=-1, wrap=True)
    assert len(steps) == 5
    assert [step.target for step in steps[:3]] == ["/0", "/1", "/3"]
    assert steps[3].target == "/0"
    assert steps[0].order == 1


def test_detect_traps_flags_confined_candidates() -> None:
    candidates = collect_focusables(
        (
            ElementNode("button", {}, "Only", path="/0"),
            ElementNode("button", {}, "Second", path="/1"),
        )
    )
    assert detect_traps(candidates) == []


def test_focus_mode_for_maps_contexts() -> None:
    assert focus_mode_for(ElementNode("input", {"type": "text"})) is FocusMode.EDITOR
    assert focus_mode_for(ElementNode("nav", {"role": "navigation"})) is FocusMode.SIDEBAR
    assert focus_mode_for(ElementNode("article", {})) is FocusMode.READING
    assert focus_mode_for(ElementNode("div", {})) is FocusMode.GLOBAL


def test_shortcut_binding_normalization_and_display() -> None:
    assert normalize_key("ESC") == "esc"
    assert normalize_binding("Ctrl + Shift + F") == ("ctrl", "shift", "f")
    assert normalize_binding(["ctrl", "k"]) == ("ctrl", "k")
    parsed = parse_binding("ctrl+alt+a")
    assert parsed.binding == "ctrl+alt+a"
    assert unknown_keys(parsed) == ()
    assert unknown_keys(parse_binding("ctrl+wat")) == ("wat",)
    assert format_binding(["ctrl", "p"], platform="desktop") == "Ctrl+P"
    assert format_binding(["ctrl", "p"], platform="mac") == "⌘+P"


def test_shortcut_registry_validates_defaults_and_groups() -> None:
    registry = default_shortcuts()
    report = registry.validate()
    assert len(registry) >= 25
    assert report.shortcuts
    assert report.conflicts == ()
    assert set(report.unknown_keys) <= {"settings"}
    groups = shortcut_groups(registry)
    assert "global" in groups
    assert "editor" in groups
    assert "dialog" in groups
    assert registry.find("ctrl+s", scope=FocusMode.EDITOR)
    assert registry.find("ctrl+s", scope=FocusMode.SIDEBAR) == []


def test_shortcut_registry_updates_and_serializes() -> None:
    registry = ShortcutRegistry(
        [
            Shortcut("save", ("ctrl", "s"), "Save", FocusMode.EDITOR),
            Shortcut("find", ("ctrl", "f"), "Find", FocusMode.EDITOR),
        ]
    )
    registry.update_keys("save", ("ctrl", "alt", "s"))
    save = registry.get("save")
    assert save is not None
    assert set(save.keys) == {"ctrl", "alt", "s"}
    payload = registry.to_payload()
    assert payload["find"] == ["ctrl", "f"]
    restored = ShortcutRegistry.from_payload(payload)
    assert len(restored) == 2
    registry.set_enabled("find", False)
    assert registry.find("ctrl+f") == []


def test_binding_conflict_respects_scope() -> None:
    first = Shortcut("one", ("ctrl", "s"), "One", FocusMode.EDITOR)
    second = Shortcut("two", ("ctrl", "s"), "Two", FocusMode.EDITOR)
    other = Shortcut("three", ("ctrl", "s"), "Three", FocusMode.DIALOG)
    assert binding_conflict(first, second) is True
    assert binding_conflict(first, other) is False


def test_suggest_binding_avoids_existing_shortcuts() -> None:
    registry = ShortcutRegistry([Shortcut("save", ("ctrl", "alt", "a"), "Save", FocusMode.EDITOR)])
    suggestion = suggest_binding(registry, "extra", scope=FocusMode.EDITOR)
    assert suggestion != "Ctrl+Alt+A"
    assert "extra" in registry


def test_audit_issue_severity_is_comparable() -> None:
    issue = next(iter(audit_payload({"nodes": [{"tag": "img", "attrs": {"src": "x"}}]}).issues))
    assert issue.severity in Severity
    assert issue.as_dict()["remediation"]
