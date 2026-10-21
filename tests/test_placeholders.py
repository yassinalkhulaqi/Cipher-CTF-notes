from __future__ import annotations

from redscribe.content.placeholders import (
    interpolate,
    placeholder_names,
    target_values,
)


def test_placeholder_names_are_unique_and_ordered() -> None:
    assert placeholder_names("{{user}}@{{target}} {{user}} {{lport}}") == [
        "user",
        "target",
        "lport",
    ]
    assert placeholder_names("no placeholders") == []


def test_interpolate_replaces_values_and_keeps_unknown() -> None:
    result = interpolate(
        "{{user}}@{{target}} {{unknown}} {{blank}}",
        {"user": " alice ", "target": "10.0.0.5", "blank": "  "},
    )
    assert result == "alice@10.0.0.5 {{unknown}} {{blank}}"


def test_target_values_derives_url_context() -> None:
    values = target_values("https://app.acme.test:8443/login?next=/admin")
    assert values["target"] == "https://app.acme.test:8443/login?next=/admin"
    assert values["domain"] == "app.acme.test"
    assert values["url"] == "https://app.acme.test:8443/login?next=/admin"
    assert values["slug"]


def test_target_values_accepts_host_port_and_path() -> None:
    values = target_values("10.10.10.10:8080/admin")
    assert values["domain"] == "10.10.10.10"
    assert values["url"] == "https://10.10.10.10:8080/admin"


def test_target_values_handles_ipv6() -> None:
    values = target_values("http://[2001:db8::1]:8080/path")
    assert values["domain"] == "2001:db8::1"
    assert values["url"] == "http://[2001:db8::1]:8080/path"


def test_empty_target_has_no_context() -> None:
    assert target_values("   ") == {}
