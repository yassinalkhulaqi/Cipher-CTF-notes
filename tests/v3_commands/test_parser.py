"""Tests for command text parsing and argument binding."""

from __future__ import annotations

import pytest

from redscribe.v3.commands.parser import (
    BindingError,
    ParseError,
    bind_arguments,
    canonicalize_command_id,
    parse_command,
    parse_sequence,
    render_command,
    tokenize,
)
from redscribe.v3.commands.registry import default_registry
from redscribe.v3.commands.types import ArgumentSpec, ArgumentType, CommandGroup, CommandSpec


def test_tokenize_respects_quotes_and_escapes() -> None:
    tokens = tokenize('title="Hello World" description=\'a \\"quote\\"\' plain')
    assert tuple(token.value for token in tokens) == (
        "title=Hello World",
        'description=a "quote"',
        "plain",
    )
    assert tokens[0].position == 0
    assert not tokens[0].is_flag
    assert tokenize("--flag value")[0].is_flag
    with pytest.raises(ParseError):
        tokenize('title="unterminated')


def test_canonicalize_command_id() -> None:
    assert canonicalize_command_id("/note:new") == "note.new"
    assert canonicalize_command_id(">CREATE.NOTE") == "create.note"
    assert canonicalize_command_id(" view : split ") == "view.split"
    with pytest.raises(ParseError):
        canonicalize_command_id("bad id!")
    with pytest.raises(ParseError):
        canonicalize_command_id("a.b.c.d")


def test_parse_command_named_and_flagged_arguments() -> None:
    parsed = parse_command('/create.note title="Hello World" --tags recon,web --pinned')
    assert parsed.command_id == "create.note"
    assert parsed.named == {"title": "Hello World", "tags": "recon,web", "pinned": "true"}
    assert parsed.positional == ()
    assert parsed.as_dict()["raw"].startswith("/create.note")


def test_parse_command_positional_and_equals() -> None:
    parsed = parse_command("view.split vertical pane=pane:side")
    assert parsed.command_id == "view.split"
    assert parsed.positional == ("vertical",)
    assert parsed.named == {"pane": "pane:side"}


def test_parse_command_rejects_bad_tokens() -> None:
    with pytest.raises(ParseError):
        parse_command("")
    with pytest.raises(ParseError):
        parse_command("create.note --title A --title B")
    with pytest.raises(ParseError):
        parse_command("create.note --=bad")
    with pytest.raises(ParseError):
        parse_command('create.note title="unterminated')


def test_bind_arguments_to_spec() -> None:
    registry = default_registry()
    spec = registry.require("create.finding")
    parsed = parse_command('/create.finding "SQL injection" high')
    invocation = bind_arguments(parsed, spec)
    assert invocation.command_id == "create.finding"
    assert invocation.arguments == {"title": "SQL injection", "severity": "high"}
    assert invocation.source == "palette"


def test_bind_arguments_defaults_and_aliases() -> None:
    registry = default_registry()
    spec = registry.require("create.finding")
    invocation = bind_arguments(parse_command('newfinding "Reflected XSS"'), spec)
    assert invocation.arguments["severity"] == "medium"
    with pytest.raises(BindingError):
        bind_arguments(parse_command("view.split"), spec)
    with pytest.raises(BindingError):
        bind_arguments(parse_command("create.finding X --unknown value"), spec)
    with pytest.raises(BindingError):
        bind_arguments(parse_command("create.finding X low extra"), spec)


def test_bind_arguments_validates_types() -> None:
    spec = CommandSpec(
        id="test.command",
        title="Test",
        group=CommandGroup.SYSTEM,
        arguments=(
            ArgumentSpec("count", arg_type=ArgumentType.NUMBER, required=True),
            ArgumentSpec("enabled", arg_type=ArgumentType.BOOLEAN, default="false"),
            ArgumentSpec("ref", arg_type=ArgumentType.ENTITY_REF, default="note:x"),
        ),
    )
    invocation = bind_arguments(parse_command("test.command 3 --enabled yes"), spec)
    assert invocation.arguments == {"count": "3", "enabled": "true", "ref": "note:x"}
    with pytest.raises(ValueError):
        bind_arguments(parse_command("test.command abc"), spec)


def test_render_command_roundtrip() -> None:
    registry = default_registry()
    spec = registry.require("create.note")
    invocation = bind_arguments(parse_command('/create.note title="Hello World" tags=recon'), spec)
    rendered = render_command(invocation, spec)
    assert rendered == '/create.note --title "Hello World" --tags recon'
    reparsed = bind_arguments(parse_command(rendered), spec)
    assert reparsed.arguments == invocation.arguments
    assert render_command(invocation).startswith("/create.note")


def test_render_quotes_empty_and_special_values() -> None:
    spec = CommandSpec(
        id="test.render",
        title="Render",
        group=CommandGroup.SYSTEM,
        arguments=(ArgumentSpec("value"),),
    )
    from redscribe.v3.commands.types import CommandInvocation

    assert (
        render_command(CommandInvocation("test.render", {"value": ""}), spec)
        == '/test.render --value ""'
    )
    rendered = render_command(CommandInvocation("test.render", {"value": 'a "b"'}), spec)
    assert "a" in rendered
    assert "b" in rendered


def test_parse_sequence_from_numbered_script() -> None:
    script = (
        "1. /navigation.goto --ref note:alpha\n2. - /create.note title=Demo\n\n- /session.start"
    )
    steps = parse_sequence(script)
    assert tuple(step.command_id for step in steps) == (
        "navigation.goto",
        "create.note",
        "session.start",
    )
    assert steps[1].named["title"] == "Demo"
