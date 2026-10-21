from __future__ import annotations

from redscribe.content.snippets import (
    BUILTIN_BY_KEY,
    BUILTIN_SNIPPETS,
    resolve_command,
    snippet_placeholders,
)


def test_builtin_snippets_have_unique_keys_and_commands() -> None:
    keys = [snippet.builtin_key for snippet in BUILTIN_SNIPPETS]
    assert len(keys) == len(set(keys))
    assert set(BUILTIN_BY_KEY) == set(keys)
    assert all(snippet.builtin for snippet in BUILTIN_SNIPPETS)
    assert all(snippet.command.strip() for snippet in BUILTIN_SNIPPETS)
    assert len(BUILTIN_SNIPPETS) >= 60


def test_snippet_placeholders_preserves_order_and_uniqueness() -> None:
    assert snippet_placeholders("ssh {{user}}@{{target}} {{user}}") == ["user", "target"]
    assert snippet_placeholders("nmap -sV example.test") == []


def test_resolve_command_uses_target_context() -> None:
    command = "nmap -sV {{target}} && curl {{url}} && host {{domain}}"
    resolved = resolve_command(command, target="https://app.acme.test:8443/login")
    assert resolved == (
        "nmap -sV https://app.acme.test:8443/login "
        "&& curl https://app.acme.test:8443/login "
        "&& host app.acme.test"
    )


def test_resolve_command_prefers_explicit_values() -> None:
    resolved = resolve_command(
        "ssh {{user}}@{{target}}",
        target="10.10.10.10",
        values={"user": "alice", "target": "192.0.2.5"},
    )
    assert resolved == "ssh alice@192.0.2.5"


def test_resolve_command_rederives_context_from_explicit_target() -> None:
    resolved = resolve_command(
        "{{target}} {{domain}} {{url}}",
        target="ignored.test",
        values={"target": "https://app.acme.test:8443/login"},
    )
    assert resolved == (
        "https://app.acme.test:8443/login app.acme.test https://app.acme.test:8443/login"
    )


def test_resolve_command_supports_ipv6_targets() -> None:
    resolved = resolve_command("curl {{url}}", target="[2001:db8::1]:8443")
    assert resolved == "curl https://[2001:db8::1]:8443"


def test_resolve_command_leaves_unknown_placeholders() -> None:
    assert resolve_command("echo {{missing}}") == "echo {{missing}}"
    assert resolve_command("echo {{missing}}", values={"missing": "  "}) == "echo {{missing}}"
