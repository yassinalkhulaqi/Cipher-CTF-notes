from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.namespaces.reporting import (
    CONFIG_FIELDS,
    ROUTE_SPECS,
    ReportingHandlers,
    ReportingNamespace,
    register,
    register_with_vault,
    route_names,
    route_specs,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2
from redscribe.v2.reporting.pipeline import ReportingService


def seed(vault: Vault) -> None:
    root = vault.create_node("Engagement", kind="folder")
    vault.create_node(
        "Critical finding",
        root.id,
        content="flag{demo1234}\nadmin@example.test\napi_key: abcdef123456",
        tags="critical, web, report",
        target="app.example.test",
        status="active",
        flag="flag{demo1234}",
    )
    vault.create_node(
        "Low finding",
        root.id,
        content="Minor hardening note.",
        tags="low, host",
        status="todo",
    )


def make_router(vault: Vault) -> tuple[V2Router, ReportingNamespace]:
    api = ApiV2(vault)
    namespace = register(api)
    return V2Router(vault, api), namespace


def envelope_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    assert isinstance(data, dict)
    return data


def error_code(response: dict[str, Any]) -> str:
    error = response.get("error")
    assert isinstance(error, dict)
    assert isinstance(error.get("code"), str)
    return error["code"]


def test_registration_is_additive_and_complete(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = register(api)
    names = route_names()
    assert len(names) == len(ROUTE_SPECS) == 20
    assert set(names) <= set(api.routes)
    assert namespace.routes() == names
    assert namespace.service.vault is vault
    assert len(namespace.handler_map()) == len(names)
    assert all(spec["description"] for spec in route_specs())
    assert all("action" in spec for spec in ROUTE_SPECS)
    assert isinstance(namespace.handlers, ReportingHandlers)
    assert isinstance(namespace.service, ReportingService)


def test_register_with_vault_does_not_mutate_registry(vault: Vault) -> None:
    namespace = register_with_vault(vault)
    first = ApiV2(vault)
    second = ApiV2(vault)
    assert set(first.routes) == set(second.routes)
    assert set(route_names()).isdisjoint(set(first.routes))
    assert namespace.handlers.health({}).data["namespace"] == "reporting"


def test_bad_registrar_is_rejected(vault: Vault) -> None:
    namespace = register_with_vault(vault)

    class InvalidRegistrar:
        pass

    InvalidRegistrar.vault = vault
    with pytest.raises(TypeError):
        namespace.register(InvalidRegistrar())


def test_health_templates_profiles_and_schema(vault: Vault) -> None:
    router, _ = make_router(vault)
    health = envelope_data(router.dispatch("reporting.health", {}))
    assert health["ok"] is True
    assert health["namespace"] == "reporting"
    assert "markdown" in health["formats"]
    assert "ctf" in health["templates"]
    assert any(profile["name"] == "standard" for profile in health["profiles"])
    templates = envelope_data(router.dispatch("reporting.templates", {}))["templates"]
    assert len(templates) == 5
    template = envelope_data(router.dispatch("reporting.template", {"key": "engagement"}))
    assert template["key"] == "engagement"
    assert template["sections"]
    profiles = envelope_data(router.dispatch("reporting.profiles", {}))["profiles"]
    assert len(profiles) == 5
    schema = envelope_data(router.dispatch("reporting.config_schema", {}))
    assert schema["version"]
    assert "formats" in schema["formats"]
    field_names = {field["name"] for field in schema["fields"]}
    assert {"title", "template", "format", "print_profile", "statuses"} <= field_names
    assert len(CONFIG_FIELDS) == len(schema["fields"])


def test_source_route_filters_and_digest(vault: Vault) -> None:
    seed(vault)
    router, _ = make_router(vault)
    first = envelope_data(router.dispatch("reporting.source", {"generated_at": "fixed"}))
    second = envelope_data(router.dispatch("reporting.source", {"generated_at": "fixed"}))
    assert first == second
    assert first["generated_at"] == "fixed"
    assert len(first["notes"]) == 2
    filtered = envelope_data(router.dispatch("reporting.source", {"tag": "critical"}))
    assert len(filtered["notes"]) == 1
    assert filtered["notes"][0]["title"] == "Critical finding"
    assert len(envelope_data(router.dispatch("reporting.source", {"status": "todo"}))["notes"]) == 1


def test_sections_route_outline_and_parse(vault: Vault) -> None:
    router, _ = make_router(vault)
    default = envelope_data(router.dispatch("reporting.sections", {"key": "ctf"}))
    assert default["sections"]
    assert default["stats"]["sections"] > 0
    assert default["outline"]
    parsed = envelope_data(
        router.dispatch(
            "reporting.sections",
            {"sections": [{"identifier": "custom", "title": "Custom", "level": 2}]},
        )
    )
    assert parsed["sections"][0]["identifier"] == "custom"
    assert parsed["stats"]["sections"] == 1


def test_build_preview_validate_severity_and_inclusion(vault: Vault) -> None:
    seed(vault)
    router, _ = make_router(vault)
    payload = {"title": "Engagement Report", "template": "engagement", "generated_at": "fixed"}
    built = envelope_data(router.dispatch("reporting.build", payload))
    assert built["title"] == "Engagement Report"
    assert built["finding_count"] == 2
    assert built["severity"]["critical"] == 1
    assert built["source_digest"]
    preview = envelope_data(router.dispatch("reporting.preview", payload))
    assert preview["finding_count"] == 2
    assert preview["severity"]["risk_level"] == "critical"
    assert preview["sections"]
    validated = envelope_data(router.dispatch("reporting.validate", payload))
    assert validated["valid"] is True
    assert validated["errors"] == 0
    severity = envelope_data(router.dispatch("reporting.severity", payload))
    assert severity["total"] == 2
    assert len(severity["findings"]) == 2
    inclusion = envelope_data(router.dispatch("reporting.inclusion", payload))
    assert inclusion["source_notes"] == 2
    assert inclusion["selected_notes"] == 2
    assert inclusion["rules"]["includes"] == 1


def test_render_export_and_manifest_routes(vault: Vault, tmp_path: Path) -> None:
    seed(vault)
    router, _ = make_router(vault)
    payload = {"title": "Report", "generated_at": "fixed"}
    for fmt, extension in (
        ("markdown", ".md"),
        ("html", ".html"),
        ("json", ".json"),
        ("print", ".print.html"),
    ):
        rendered = envelope_data(router.dispatch("reporting.render", {**payload, "format": fmt}))
        assert rendered["format"] == fmt
        assert rendered["filename"].endswith(extension)
        assert rendered["content"]
        assert rendered["manifest"]["inputs"]["source_digest"]
    exported = envelope_data(
        router.dispatch(
            "reporting.export",
            {**payload, "format": "markdown", "directory": str(tmp_path / "exports")},
        )
    )
    assert Path(exported["path"]).is_file()
    assert exported["bytes"] > 0
    manifest = envelope_data(router.dispatch("reporting.manifest", payload))
    assert manifest["report_id"] == "report"
    assert manifest["outputs"] == {}


def test_bundle_route_writes_all_outputs(vault: Vault, tmp_path: Path) -> None:
    seed(vault)
    router, _ = make_router(vault)
    target = tmp_path / "bundle"
    result = envelope_data(
        router.dispatch(
            "reporting.bundle",
            {
                "title": "Bundle",
                "generated_at": "fixed",
                "directory": str(target),
                "formats": ["markdown", "html", "json"],
            },
        )
    )
    assert result["formats"] == ["markdown", "html", "json"]
    assert set(result["outputs"]) == {"markdown", "html", "json"}
    assert (target / "manifest.json").is_file()
    assert len(list(target.glob("*"))) == 4


def test_redaction_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    result = envelope_data(
        router.dispatch(
            "reporting.redact",
            {"text": "flag{demo1234} admin@example.test", "context": 4},
        )
    )
    assert "[FLAG]" in result["text"]
    assert "[EMAIL]" in result["text"]
    assert "flag" in result["applied"]
    assert result["preview"]
    assert result["rules"]
    rules = envelope_data(router.dispatch("reporting.redaction_rules", {}))["rules"]
    assert next(rule["name"] for rule in rules) == "private-key"
    with_hosts = envelope_data(
        router.dispatch("reporting.redaction_rules", {"include_hosts": True})
    )["rules"]
    assert len(with_hosts) == len(rules) + 1


def test_reorder_and_move_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    template = envelope_data(router.dispatch("reporting.template", {"key": "ctf"}))
    sections = template["sections"]
    identifiers = [item["identifier"] for item in sections]
    reordered = envelope_data(
        router.dispatch(
            "reporting.reorder",
            {"sections": sections, "parent_id": "", "order": list(reversed(identifiers))},
        )
    )["sections"]
    assert [item["identifier"] for item in reordered] == list(reversed(identifiers))
    moved = envelope_data(
        router.dispatch(
            "reporting.move",
            {
                "sections": reordered,
                "identifier": identifiers[0],
                "parent_id": "",
                "index": len(identifiers) - 1,
            },
        )
    )["sections"]
    assert [item["identifier"] for item in moved][-1] == identifiers[0]


def test_route_error_envelopes(vault: Vault) -> None:
    router, _ = make_router(vault)
    missing_key = router.dispatch("reporting.template", {})
    assert missing_key["ok"] is False
    assert error_code(missing_key) == "missing_field"
    bad_template = router.dispatch("reporting.template", {"key": "missing"})
    assert error_code(bad_template) == "invalid_request"
    bad_format = router.dispatch("reporting.render", {"format": "pdf"})
    assert error_code(bad_format) == "invalid_choice"
    bad_sections = router.dispatch("reporting.sections", {"sections": "not-an-array"})
    assert error_code(bad_sections) == "invalid_request"
    bad_context = router.dispatch("reporting.redact", {"text": "x", "context": "wide"})
    assert error_code(bad_context) == "invalid_request"
    unknown = router.dispatch("reporting.missing", {})
    assert error_code(unknown) == "unknown_route"


def test_handlers_expose_etags_and_service(vault: Vault) -> None:
    seed(vault)
    _, namespace = make_router(vault)
    handlers = namespace.handlers
    assert handlers.service is namespace.service
    for call in (
        handlers.health,
        handlers.templates,
        handlers.profiles,
        handlers.config_schema,
    ):
        result = call({})
        assert result.etag
        assert result.status == 200
    assert handlers.config_schema({}).data["version"] == "1.0.0"
