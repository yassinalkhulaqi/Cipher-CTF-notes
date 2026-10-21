from __future__ import annotations

import re

from redscribe.content.templates import TEMPLATE_MAP, TEMPLATES, get_template, render_template


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
