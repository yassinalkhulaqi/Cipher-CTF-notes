from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import V2Error
from redscribe.ui.web.v2.namespaces.a11y import (
    ROUTE_SPECS,
    A11yHandlers,
    A11yNamespace,
    A11yService,
    register,
    route_names,
    route_specs,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2


def _nodes() -> list[dict[str, Any]]:
    return [
        {
            "tag": "a",
            "attrs": {"href": "#main"},
            "text": "Skip to content",
            "path": "/0",
        },
        {
            "tag": "button",
            "attrs": {"type": "button", "aria-label": "Save"},
            "text": "",
            "path": "/1",
        },
        {
            "tag": "img",
            "attrs": {"src": "chart.png", "alt": "Chart"},
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


def test_service_health_reports_capabilities() -> None:
    health = A11yService().health()
    assert health["ok"] is True
    assert health["namespace"] == "a11y"
    assert "accessibility_audit" in health["features"]
    assert "theme_contrast" in health["features"]
    assert health["wcag_levels"] == ["A", "AA", "AAA"]
    assert health["locales"] > 0
    assert health["themes"] > 0
    assert health["shortcuts"] > 0


def test_service_audit_and_summary() -> None:
    report = A11yService().audit({"nodes": _nodes(), "level": "AA", "locale": "en"})
    assert report["level"] == "AA"
    assert report["checked_elements"] == 4
    assert report["score"] > 0
    assert "score" in report["summary"]
    assert isinstance(report["passed"], bool)


def test_service_audit_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unknown WCAG level"):
        A11yService().audit({"level": "ZZZ"})


def test_service_contrast_accepts_pairs_and_palettes() -> None:
    service = A11yService()
    pairs = service.contrast(
        {"pairs": [{"name": "body", "foreground": "#000", "background": "#fff"}]}
    )
    assert pairs["pairs"][0]["passed"] is True
    assert pairs["grades"][0]["best"] == "AAA"
    palette = service.contrast(
        {
            "palette": {
                "text": "#000",
                "text_muted": "#777",
                "surface": "#fff",
                "surface_alt": "#f5f5f5",
                "accent": "#06c",
                "on_accent": "#fff",
                "border": "#ccc",
            }
        }
    )
    assert len(palette["pairs"]) > 0
    assert 0 <= palette["score"] <= 100


def test_service_single_contrast_check_includes_suggestion() -> None:
    result = A11yService().check_contrast("#777777", "#ffffff", level="AA")
    assert result["passed"] is False
    assert result["suggestion"].startswith("#")
    assert result["grade"]["grades"]["AA"] is False


def test_service_focus_and_aria_reports() -> None:
    service = A11yService()
    focus = service.focus({"nodes": _nodes(), "simulate_presses": 3})
    assert focus["focusable_count"] == 3
    assert focus["has_skip_link"] is True
    assert len(focus["simulation"]) == 3
    aria = service.aria({"nodes": _nodes(), "strict": True})
    assert aria["checked"] == 4
    assert isinstance(aria["issues"], list)


def test_service_aria_attribute_and_role_catalog() -> None:
    service = A11yService()
    valid = service.validate_aria_attribute("aria-hidden", "true")
    invalid = service.validate_aria_attribute("aria-expanded", "maybe")
    assert valid["valid"] is True
    assert invalid["valid"] is False
    assert service.role_catalog()["roles"] > 50


def test_service_shortcut_validation_and_formatting() -> None:
    service = A11yService()
    report = service.shortcuts({"suggest_for": "notes.open"})
    assert len(report["shortcuts"]) >= 25
    assert "groups" in report
    assert "suggestion" in report
    formatted = service.shortcut_format(["CTRL", "K"], platform="mac")
    assert formatted["binding"] == "ctrl+k"
    assert "K" in formatted["display"]
    overridden = service.shortcuts({"overrides": {"save": ["ctrl", "alt", "s"]}})
    assert len(overridden["shortcuts"]) >= 25


def test_service_locale_catalog_and_translation() -> None:
    service = A11yService()
    locales = service.locales({"accept_language": "fr-CA,fr;q=0.9"})
    assert locales["matched"] == "fr-CA" or locales["matched"] == "fr"
    assert any(item["code"] == "ar" for item in locales["locales"])
    detail = service.locale_detail("ar")
    assert detail["supported"] is True
    assert detail["direction"] == "rtl"
    catalog = service.catalog("en", prefixes=["action."])
    assert catalog["count"] > 0
    assert all(key.startswith("action.") for key in catalog["keys"])
    translated = service.translate("es", "action.save")
    assert translated["message"] == "Guardar"
    assert translated["missing"] is False
    assert service.coverage()["baseline"] == "en"


def test_service_locale_errors() -> None:
    service = A11yService()
    with pytest.raises(ValueError, match="Unknown locale"):
        service.locale_detail("xx")
    with pytest.raises(ValueError, match="Unknown catalog"):
        service.catalog("xx")


def test_service_format_kinds() -> None:
    service = A11yService()
    assert "," in service.format({"kind": "number", "value": 1234, "locale": "en"})["value"]
    assert (
        service.format({"kind": "plural", "key": "plural.note", "value": 2})["value"]
        == "plural.note.other"
    )
    assert service.format({"kind": "date", "value": "2026-11-18"})["value"] == "2026-11-18"
    assert "2026" in service.format({"kind": "datetime", "value": "2026-11-18T10:00:00Z"})["value"]
    assert "ago" in service.format({"kind": "relative", "value": "2026-11-01T10:00:00Z"})["value"]
    with pytest.raises(ValueError, match="Unsupported format kind"):
        service.format({"kind": "unknown", "value": 1})


def test_service_rtl_payload() -> None:
    result = A11yService().rtl({"locale": "ar", "text": "hello (world)", "nodes": _nodes()})
    assert result["css_vars"]["--a11y-inline-start"] == "right"
    assert result["warnings"]
    assert result["tree"]["direction"] == "rtl"


def test_service_theme_payloads() -> None:
    service = A11yService()
    themes = service.themes()
    assert any(theme["name"] == "graphite" for theme in themes["themes"])
    assert "--a11y-" in themes["css"]
    detail = service.theme_detail("high-contrast-light")
    assert detail["issue_summary"]["passed"] is True
    css = service.theme_css("paper", selector="[data-theme='paper']")
    assert css["theme"] == "paper"
    assert css["css"].startswith("[data-theme='paper']")
    compare = service.theme_compare("paper", "graphite")
    assert compare["count"] > 0
    custom = service.theme_create({"name": "Custom", "tokens": {"accent": "#123456"}})
    assert custom["name"] == "custom"
    contrast = service.theme_contrast({"themes": ["paper", "graphite"]})
    assert "paper" in contrast["themes"]
    fixes = service.theme_fixes("high-contrast-dark")
    assert fixes["before"] == pytest.approx(fixes["after"])


def test_service_theme_errors() -> None:
    service = A11yService()
    with pytest.raises(ValueError, match="Unknown theme"):
        service.theme_detail("missing")
    with pytest.raises(ValueError, match="Unknown theme"):
        service.theme_css("missing")


def test_service_preferences_crud() -> None:
    service = A11yService()
    defaults = service.preferences_defaults()
    assert defaults["locale"] == "en"
    schema = service.preferences_schema()
    assert schema["version"] == 2
    validation = service.preferences_validate({"locale": "fr", "font_scale": 1.1})
    assert validation["valid"] is True
    updated = service.preferences_update(
        {"locale": "fr", "theme": "paper", "reduce_motion": True},
        profile="study",
    )
    assert updated["preferences"]["locale"] == "fr"
    current = service.preferences("study")
    assert current["direction"] == "ltr"
    assert current["preferences"]["reduce_motion"] is True
    exported = service.preferences_export(profile="study")
    service.preferences_import(exported, profile="copy")
    assert service.preferences("copy")["preferences"]["locale"] == "fr"
    replaced = service.preferences_replace({"locale": "de"}, profile="copy")
    assert replaced["preferences"]["locale"] == "de"
    reset = service.preferences_reset(profile="copy")
    assert reset["preferences"]["locale"] == "en"


def test_service_dashboard_combines_reports() -> None:
    result = A11yService().dashboard({"locale": "ar", "nodes": _nodes(), "theme": "paper"})
    assert result["locale"] == "ar"
    assert "score" in result["audit"]
    assert "focusable" in result["focus"]
    assert "passed" in result["aria"]
    assert "score" in result["contrast"]
    assert result["themes"] > 0


def test_route_specs_are_complete_and_typed() -> None:
    names = route_names()
    assert len(names) == len(ROUTE_SPECS)
    assert "a11y.health" in names
    assert "a11y.preferences_update" in names
    specs = route_specs()
    assert all(spec["description"] for spec in specs)
    mutating = {spec["action"] for spec in specs if spec["mutating"]}
    assert "preferences_update" in mutating
    assert "health" not in mutating
    required = {spec["action"]: spec["required"] for spec in specs}
    assert required["contrast_check"] == ["foreground", "background"]


def test_handlers_return_etagged_route_results() -> None:
    handlers = A11yHandlers(A11yService())
    result = handlers.health({})
    assert result.etag
    assert result.data["namespace"] == "a11y"
    assert handlers.dashboard({}).data["locale"] == "en"


def test_handlers_validate_required_fields() -> None:
    handlers = A11yHandlers(A11yService())
    with pytest.raises(V2Error):
        handlers.contrast_check({"foreground": "#000000"})
    with pytest.raises(V2Error):
        handlers.shortcut_format({})
    with pytest.raises(V2Error):
        handlers.format({"kind": "number"})


def test_namespace_register_adds_routes_to_api(vault: Vault) -> None:
    api = ApiV2(vault)
    original = set(api.routes)
    namespace = A11yNamespace(A11yService())
    registered = namespace.register(api)
    assert set(registered) <= set(api.routes)
    assert set(route_names()) <= set(api.routes)
    assert set(api.routes) == original | set(route_names())
    assert api.route("a11y.health").description
    assert api.route("a11y.preferences_reset").mutating is True


def test_namespace_handler_map_matches_specs() -> None:
    namespace = A11yNamespace(A11yService())
    handler_map = namespace.handler_map()
    assert set(handler_map) == {spec.action for spec in ROUTE_SPECS}
    assert all(callable(handler) for handler in handler_map.values())
    assert namespace.service.health()["ok"] is True


def test_module_register_helper_builds_namespace(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = register(api)
    assert isinstance(namespace, A11yNamespace)
    assert "a11y.coverage" in api.routes


def test_namespace_register_rejects_invalid_registrar() -> None:
    with pytest.raises(TypeError, match="registration method"):
        A11yNamespace(A11yService()).register(object())


def test_router_dispatches_namespace_routes(vault: Vault) -> None:
    api = ApiV2(vault)
    A11yNamespace(A11yService()).register(api)
    router = V2Router(vault, api)
    response = router.dispatch("a11y.health", {}, request_id="req_test")
    assert response["ok"] is True
    assert response["data"]["namespace"] == "a11y"
    assert response["meta"]["etag"]
    audited = router.dispatch("a11y.audit", {"nodes": _nodes()})
    assert audited["ok"] is True
    assert audited["data"]["checked_elements"] == 4


def test_router_reports_namespace_validation_errors(vault: Vault) -> None:
    api = ApiV2(vault)
    A11yNamespace(A11yService()).register(api)
    router = V2Router(vault, api)
    response = router.dispatch("a11y.contrast_check", {"foreground": "#000000"})
    assert response["ok"] is False
    assert response["error"]["code"] in {"missing_field", "invalid_request"}
    invalid = router.dispatch("a11y.format", {"kind": "bad", "value": 1})
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "invalid_request"


def test_router_replays_mutating_preference_updates(vault: Vault) -> None:
    api = ApiV2(vault)
    A11yNamespace(A11yService()).register(api)
    router = V2Router(vault, api)
    body = {"patch": {"locale": "de", "theme": "paper"}, "profile": "idem"}
    first = router.dispatch("a11y.preferences_update", body, idempotency_key="idem-1")
    second = router.dispatch("a11y.preferences_update", body, idempotency_key="idem-1")
    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["preferences"]["revision"] == second["data"]["preferences"]["revision"]
    assert second["data"]["preferences"]["locale"] == "de"


def test_router_rejects_reused_idempotency_key(vault: Vault) -> None:
    api = ApiV2(vault)
    A11yNamespace(A11yService()).register(api)
    router = V2Router(vault, api)
    router.dispatch(
        "a11y.preferences_update",
        {"patch": {"locale": "fr"}, "profile": "one"},
        idempotency_key="shared",
    )
    conflict = router.dispatch(
        "a11y.preferences_update",
        {"patch": {"locale": "de"}, "profile": "two"},
        idempotency_key="shared",
    )
    assert conflict["ok"] is False
    assert conflict["error"]["code"] == "idempotency_conflict"
