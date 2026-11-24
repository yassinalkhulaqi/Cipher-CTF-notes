"""Tests for context resolution and deterministic command scoring."""

from __future__ import annotations

import pytest

from redscribe.v3.capabilities import Capabilities
from redscribe.v3.commands.context import ContextResolver, ContextRule
from redscribe.v3.commands.registry import default_registry
from redscribe.v3.commands.scoring import (
    CommandScorer,
    group_hits,
    normalize,
    rank_commands,
    subsequence_ratio,
    tokenize_query,
)
from redscribe.v3.commands.types import CommandContext, CommandGroup, CommandSpec, CommandStatus
from redscribe.v3.commands.usage import UsageModel
from redscribe.v3.entities.types import EntityKind, EntityRef


def _resolver() -> ContextResolver:
    return ContextResolver()


def _context(**changes: object) -> CommandContext:
    payload: dict[str, object] = {"pane_id": "pane:main", "capabilities": frozenset({"commands"})}
    payload.update(changes)
    return CommandContext(
        pane_id=str(payload["pane_id"]),
        capabilities=frozenset(payload["capabilities"]),  # type: ignore[arg-type]
        entity=payload.get("entity"),  # type: ignore[arg-type]
        selection=payload.get("selection", ()),  # type: ignore[arg-type]
        tags=payload.get("tags", ()),  # type: ignore[arg-type]
        focus_active=bool(payload.get("focus_active", False)),
    )


def test_normalize_and_tokens() -> None:
    assert normalize("  Hello   WORLD ") == "hello world"
    assert tokenize_query("find:web 2024") == ("find", "web", "2024")
    assert subsequence_ratio("abc", "aXbYc") == 1.0
    assert subsequence_ratio("abc", "acb") == pytest.approx(2 / 3)
    assert subsequence_ratio("", "abc") == 0.0


def test_resolver_uses_registered_provider() -> None:
    resolver = _resolver()
    resolver.add_provider(
        "pane:main",
        lambda pane: CommandContext(pane_id=pane, entity=EntityRef.of("note", "alpha", "Alpha")),
    )
    context = resolver.resolve(
        "pane:main", capabilities=Capabilities(enabled=frozenset({"commands"}))
    )
    assert context.entity_ref == "note:alpha"
    assert context.capabilities == frozenset({"commands"})
    with pytest.raises(ValueError):
        resolver.add_provider("", lambda pane: CommandContext(pane_id=pane))


def test_availability_checks() -> None:
    resolver = _resolver()
    registry = default_registry()
    note_spec = registry.require("create.note")
    assert resolver.is_available(note_spec, _context())
    no_caps = _context(capabilities=frozenset())
    assert not resolver.is_available(note_spec, no_caps)
    rich_context = CommandContext(
        pane_id="pane:main",
        capabilities=frozenset({"commands"}),
        entity=EntityRef.of("note", "alpha"),
    )
    assert resolver.is_available(note_spec, rich_context)
    disabled = CommandSpec("test.disabled", "D", CommandGroup.SYSTEM, status=CommandStatus.DISABLED)
    assert not resolver.is_available(disabled, rich_context)
    selected_only = CommandSpec(
        "test.selection", "S", CommandGroup.INSPECT, requires_selection=True
    )
    assert not resolver.is_available(selected_only, rich_context)
    selected = CommandContext(
        pane_id="p",
        capabilities=frozenset({"commands"}),
        selection=(EntityRef.of("note", "x"),),
    )
    assert resolver.is_available(selected_only, selected)
    typed = CommandSpec("test.typed", "T", CommandGroup.INSPECT, target_kind=EntityKind.FINDING)
    assert not resolver.is_available(typed, rich_context)
    assert not resolver.is_available(typed, selected)
    finding_context = CommandContext(
        pane_id="p",
        capabilities=frozenset({"commands"}),
        entity=EntityRef.of("finding", "web-1"),
    )
    assert resolver.is_available(typed, finding_context)


def test_context_rules_and_weight() -> None:
    resolver = ContextResolver(
        rules=(ContextRule(group=CommandGroup.SESSION, required_tag="focus"),)
    )
    spec = default_registry().require("session.start")
    assert not resolver.is_available(spec, _context())
    assert resolver.is_available(spec, _context(tags=("focus",)))
    assert resolver.weight(spec, _context(focus_active=True)) > 0
    assert resolver.weight(spec, _context(focus_active=False)) < 0
    inspect = default_registry().require("inspect.entity")
    assert resolver.weight(inspect, _context(selection=(EntityRef.of("note", "x"),))) > 0
    assert "pane" in resolver.describe(_context())


def test_scorer_signals() -> None:
    spec = default_registry().require("create.note")
    scorer = CommandScorer()
    exact = scorer.score("note", spec, _context())
    assert exact.total > 0
    assert any(signal.startswith("contains") for signal in exact.signals)
    assert "exact:action" in exact.signals
    alias = scorer.score("newnote", spec, _context())
    assert "alias:newnote" in alias.signals
    assert alias.total > 0
    assert scorer.score("zzzz", spec, _context()).total == 0


def test_usage_boosts_score() -> None:
    spec = default_registry().require("create.note")
    usage = UsageModel()
    from redscribe.v3.commands.types import CommandInvocation

    usage.record(CommandInvocation(spec.id), now=100.0)
    plain = CommandScorer().score("note", spec, _context(), now=100.0).total
    boosted = CommandScorer(usage=usage).score("note", spec, _context(), now=100.0).total
    assert boosted > plain


def test_rank_and_group_results() -> None:
    registry = default_registry()
    context = _context(capabilities=frozenset({"commands"}))
    hits = rank_commands("focus", registry.all(), context)
    assert hits
    assert {hit.command.id for hit in hits[:3]} >= {"session.start", "view.focus"}
    groups = group_hits(hits)
    assert {group.group for group in groups} >= {CommandGroup.SESSION, CommandGroup.VIEW}
    assert all(len(group.hits) <= 6 for group in groups)
    with pytest.raises(ValueError):
        rank_commands("x", registry.all(), context, limit=0)
    with pytest.raises(ValueError):
        group_hits(hits, limit_per_group=0)


def test_empty_query_returns_available_commands() -> None:
    registry = default_registry()
    hits = rank_commands("", registry.all(), _context(capabilities=frozenset({"commands"})))
    assert len(hits) == 12
    assert hits == tuple(
        sorted(
            hits,
            key=lambda hit: (
                -hit.score,
                hit.command.group.order,
                hit.command.order,
                hit.command.id,
            ),
        )
    )
