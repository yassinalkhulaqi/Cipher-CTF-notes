"""A11y namespace registration and route behavior tests."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.namespaces import has_namespace, load_namespace, namespace_names
from redscribe.v3.namespaces.a11y import register

ACTIONS = (
    "audit",
    "audit_all",
    "bidi",
    "contrast",
    "dashboard",
    "export",
    "format",
    "format_batch",
    "health",
    "keyboard",
    "keyboard_group",
    "keyboard_help",
    "keyboard_lookup",
    "locales",
    "motion",
    "preferences",
    "preferences_sync",
    "preferences_update",
    "round_trip",
    "rtl",
    "rtl_manifest",
    "rules",
    "surfaces",
    "theme_contrast",
    "translate",
)


def new_router() -> V3Router:
    router = V3Router()
    register(router)
    return router


def test_namespace_is_discoverable() -> None:
    assert "a11y" in namespace_names()
    assert has_namespace("a11y")
    module = load_namespace("a11y")
    assert callable(module.register)


def test_register_adds_all_actions() -> None:
    router = new_router()
    assert router.namespaces() == ("a11y",)
    assert tuple(route.action for route in router.routes()) == ACTIONS
    assert router.size() == len(ACTIONS)
    manifest = router.manifest()
    assert any(route["path"] == "/api/v3/a11y/audit" for route in manifest["routes"])


def test_duplicate_registration_is_rejected() -> None:
    router = new_router()
    with pytest.raises(V3Error, match="already registered"):
        register(router)


def test_health_and_rules_routes() -> None:
    router = new_router()
    health = router.dispatch("a11y", "health")
    assert health["namespace"] == "a11y"
    assert health["wcag22_rules"] >= 8
    rules = router.dispatch("a11y", "rules", {"level": "aa"})
    assert rules["level"] == "AA"
    assert "focus.not_obscured" in [item["id"] for item in rules["rules"]]


def test_surfaces_and_audit_routes() -> None:
    router = new_router()
    surfaces = router.dispatch("a11y", "surfaces")
    assert len(surfaces["names"]) >= 10
    audit = router.dispatch("a11y", "audit", {"surface": "graph-workbench"})
    assert audit["surface"] == "graph-workbench"
    assert audit["passed"] is False
    all_audit = router.dispatch("a11y", "audit_all", {"level": "AA"})
    assert all_audit["surfaces"] >= 10
    assert all_audit["failed"] >= 1


def test_audit_rejects_unknown_surface() -> None:
    router = new_router()
    with pytest.raises(V3Error, match="Unknown surface"):
        router.dispatch("a11y", "audit", {"surface": "ghost"})


def test_contrast_routes() -> None:
    router = new_router()
    report = router.dispatch(
        "a11y",
        "contrast",
        {"targets": [{"name": "faint", "foreground": "#eee", "background": "#fff"}]},
    )
    assert report["passed"] is False
    assert report["fixes"]
    themes = router.dispatch("a11y", "theme_contrast")
    assert themes["score"] == 100.0
    assert themes["equivalent"] is True


def test_format_routes() -> None:
    router = new_router()
    single = router.dispatch(
        "a11y",
        "format",
        {
            "locale": "de-DE",
            "kind": "number",
            "value": 1234.5,
            "options": {"min_digits": 2, "max_digits": 2},
        },
    )
    assert single["text"] == "1.234,5"
    batch = router.dispatch(
        "a11y",
        "format_batch",
        {"requests": [{"locale": "en", "kind": "number", "value": 5}]},
    )
    assert batch["results"][0]["text"] == "5"
    round_trip = router.dispatch("a11y", "round_trip", {"locale": "fr", "value": 12.5})
    assert round_trip["exact"] is True


def test_locale_and_translate_routes() -> None:
    router = new_router()
    locales = router.dispatch("a11y", "locales", {"accept_language": "fa-IR,en;q=0.8"})
    assert "fa" in [item["value"] for item in locales["locales"]]
    translated = router.dispatch(
        "a11y",
        "translate",
        {"locale": "pt-BR", "key": "v3.search.results", "params": {"count": 4}},
    )
    assert "4" in translated["message"]
    assert translated["missing"] is False


def test_rtl_routes() -> None:
    router = new_router()
    layout = router.dispatch(
        "a11y", "rtl", {"pane": "finding-studio", "locale": "ar", "text": "hello שלום"}
    )
    assert layout["layout"]["direction"] == "rtl"
    assert layout["layout"]["sides"]["start"] == "right"
    assert layout["validation"]["valid"] is True
    assert layout["attributes"]["dir"] == "rtl"
    manifest = router.dispatch("a11y", "rtl_manifest", {"locale": "he"})
    assert len(manifest["panes"]) >= 10
    bidi = router.dispatch("a11y", "bidi", {"locale": "ar", "text": "abcDEF"})
    assert bidi["warnings"]


def test_keyboard_routes() -> None:
    router = new_router()
    keyboard = router.dispatch("a11y", "keyboard", {"platform": "desktop"})
    assert keyboard["complete"] is True
    assert len(keyboard["bindings"]) >= 40
    help_payload = router.dispatch("a11y", "keyboard_help", {"locale": "en"})
    assert help_payload["lines"]
    assert help_payload["focus_order"]
    lookup = router.dispatch(
        "a11y", "keyboard_lookup", {"pressed": ["ctrl", "s"], "scope": "editor"}
    )
    assert lookup["bindings"][0]["action"] == "save"
    group = router.dispatch("a11y", "keyboard_group", {"group": "navigation"})
    assert len(group["bindings"]) == 12


def test_preference_routes() -> None:
    router = new_router()
    defaults = router.dispatch("a11y", "preferences")
    assert defaults["valid"] is True
    updated = router.dispatch(
        "a11y", "preferences_update", {"patch": {"locale": "ar", "theme": "light"}}
    )
    assert updated["preferences"]["locale"] == "ar"
    synced = router.dispatch(
        "a11y",
        "preferences_sync",
        {
            "remote": {"preferences": {"locale": "de", "theme": "light", "revision": 7}},
            "strategy": "remote_wins",
        },
    )
    assert synced["applied"] is True
    assert synced["record"]["preferences"]["locale"] == "de"


def test_motion_dashboard_and_export_routes() -> None:
    router = new_router()
    motion = router.dispatch("a11y", "motion", {"mode": "reduced"})
    assert motion["content_hidden"] is False
    dashboard = router.dispatch("a11y", "dashboard", {"locale": "fa"})
    assert dashboard["direction"] == "rtl"
    assert dashboard["keyboard"]["complete"] is True
    exported = router.dispatch("a11y", "export")
    assert exported["version"] == "3.0"
    assert exported["rules"]
    assert exported["keyboard"]["bindings"]


def test_routes_validate_input_types() -> None:
    router = new_router()
    with pytest.raises(V3Error) as error:
        router.dispatch("a11y", "rules", {"level": "ZZ"})
    assert error.value.code == V3ErrorCode.INVALID_CHOICE
    with pytest.raises(V3Error, match="must be a string"):
        router.dispatch("a11y", "translate", {"key": 7})
    with pytest.raises(V3Error, match="must be a list"):
        router.dispatch("a11y", "format_batch", {"requests": "nope"})
    with pytest.raises(V3Error, match="must be numeric"):
        router.dispatch("a11y", "round_trip", {"value": True})
    with pytest.raises(V3Error, match="Unsupported format kind"):
        router.dispatch("a11y", "format", {"kind": "mystery", "value": 1})


def test_dynamic_install_registers_a11y() -> None:
    router = V3Router()
    installed = router.install_namespaces()
    assert installed >= 2
    assert router.get("a11y", "health") is not None
    assert "a11y" in router.namespaces()
    assert router.dispatch("a11y", "health")["namespace"] == "a11y"
