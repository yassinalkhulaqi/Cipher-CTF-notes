from __future__ import annotations

import re

import pytest

from redscribe.content.templates import (
    REQUIRED_FIELDS,
    TEMPLATE_CHANGELOG,
    TEMPLATE_MAP,
    TEMPLATE_VERSIONS,
    TEMPLATES,
    TemplateRenderError,
    get_template,
    render_template,
    render_template_checked,
    render_template_strict,
    required_fields,
    template_changelog,
    template_manifest,
    template_placeholders,
    template_version,
    validate_template,
    validate_template_registry,
)
from redscribe.domain.models import Template


def test_every_template_key_is_unique_and_reachable() -> None:
    keys = [template.key for template in TEMPLATES]
    assert len(keys) == len(set(keys))
    assert set(TEMPLATE_MAP) == set(keys)
    assert {template.key for template in TEMPLATES} >= {
        "blank",
        "ctf",
        "host",
        "web",
        "finding",
        "engagement",
        "cheatsheet",
    }


def test_get_template_falls_back_to_blank() -> None:
    assert get_template("ctf").key == "ctf"
    assert get_template("does-not-exist").key == "blank"


def test_every_template_renders_without_known_placeholders() -> None:
    for template in TEMPLATES:
        content = render_template(template, "Example", "app.acme.test")
        assert "{{" not in content
        assert "}}" not in content


def test_render_template_fills_context() -> None:
    content = render_template(get_template("host"), "ACME web", "app.acme.test")
    assert "# ACME web" in content
    assert "Target: `app.acme.test`" in content
    assert "nmap/app-acme-test app.acme.test" in content
    assert "{{" not in content

    web = render_template(
        get_template("web"),
        "ACME web",
        "https://app.acme.test:8443/login",
    )
    assert "Base URL: https://app.acme.test:8443/login" in web
    assert "Host: app.acme.test" in web


def test_render_template_uses_placeholders_when_target_missing() -> None:
    content = render_template(get_template("web"), "New web assessment")
    assert "Target: `<TARGET>`" in content
    assert "Base URL: https://<TARGET>" in content
    assert "Host: <TARGET>" in content
    assert "{{" not in content
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)


def test_render_template_normalizes_host_port_targets() -> None:
    content = render_template(get_template("web"), "ACME web", "app.acme.test:8443/app")
    assert "Base URL: https://app.acme.test:8443/app" in content
    assert "Host: app.acme.test" in content
    assert "{{" not in content


def test_render_template_never_leaves_known_placeholders() -> None:
    content = render_template(get_template("ctf"), "", "")
    assert content.startswith("# Untitled")
    assert "{{" not in content
    web = render_template(get_template("web"), "", "")
    assert "<TARGET>" in web
    assert "{{" not in web


def test_blank_template_is_empty() -> None:
    assert render_template(get_template("blank"), "Untitled") == ""


def test_template_versions_and_changelogs_are_registered() -> None:
    assert set(TEMPLATE_VERSIONS) == set(TEMPLATE_MAP)
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", version) for version in TEMPLATE_VERSIONS.values())
    assert template_version("ctf") == "2.0.0"
    assert template_version("missing") == "0.0.0"
    assert template_changelog("ctf")[0].startswith("2.0.0:")
    assert template_changelog("missing") == ()
    assert "ctf" in TEMPLATE_CHANGELOG


def test_required_fields_registry_is_consistent() -> None:
    assert set(REQUIRED_FIELDS) == set(TEMPLATE_MAP)
    assert required_fields("blank") == ()
    assert [field.name for field in required_fields("host")] == ["title", "target"]
    assert required_fields(get_template("ctf")) == required_fields("ctf")
    assert all(field.required for field in required_fields("web"))


def test_registry_validation_and_placeholder_inventory() -> None:
    assert validate_template_registry() == ()
    names = set(template_placeholders(get_template("host")))
    assert {"title", "target", "slug", "date"} <= names
    assert template_placeholders(get_template("blank")) == ()


def test_validate_template_reports_metadata_problems() -> None:
    issues = validate_template(Template("", "", "", "# {{value}}"))
    assert [issue.code for issue in issues] == [
        "missing-key",
        "missing-name",
        "unversioned-template",
    ]
    duplicate = Template("ctf", "Other", "Other", "# {{title}}")
    assert validate_template(duplicate) == ()


def test_strict_render_reports_missing_required_fields() -> None:
    result = render_template_strict(get_template("host"), {"title": "ACME"})
    assert result.ok is False
    assert result.missing == ("target",)
    assert result.version == "2.0.0"
    assert result.template_key == "host"
    assert any(issue.code == "missing-field" for issue in result.issues)


def test_strict_render_succeeds_with_all_fields() -> None:
    result = render_template_strict(
        get_template("host"), {"title": "ACME", "target": "app.acme.test"}
    )
    assert result.ok is True
    assert result.missing == ()
    assert "app.acme.test" in result.content
    assert "# ACME" in result.content
    assert all(issue.severity != "error" for issue in result.issues)


def test_render_template_checked_raises_on_missing_fields() -> None:
    with pytest.raises(TemplateRenderError):
        render_template_checked(get_template("web"), {"title": "ACME"})
    content = render_template_checked(
        get_template("web"), {"title": "ACME", "target": "app.acme.test"}
    )
    assert "# ACME" in content


def test_template_manifest_exposes_versioned_metadata() -> None:
    manifest = template_manifest()
    assert len(manifest) == len(TEMPLATES)
    assert set(manifest[0]) == {"key", "name", "version", "required", "changelog"}
    host = next(item for item in manifest if item["key"] == "host")
    assert host["required"] == ["title", "target"]
