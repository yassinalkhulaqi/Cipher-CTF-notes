"""Slash-command grammar, catalog, and completion engine."""

from __future__ import annotations

from redscribe.v2.search.commands.catalog import DEFAULT_COMMANDS, CommandCatalog
from redscribe.v2.search.commands.grammar import (
    command_grammar,
    format_command,
    parse_command,
    split_pipeline,
)
from redscribe.v2.search.commands.models import (
    CommandKind,
    CommandNode,
    CommandPlan,
    CommandSpec,
    CommandSuggestion,
    ParsedCommand,
    SuggestionResult,
)
from redscribe.v2.search.commands.suggestions import (
    apply_suggestion,
    complete_command,
    suggest_commands,
)

__all__ = [
    "DEFAULT_COMMANDS",
    "CommandCatalog",
    "CommandKind",
    "CommandNode",
    "CommandPlan",
    "CommandSpec",
    "CommandSuggestion",
    "ParsedCommand",
    "SuggestionResult",
    "apply_suggestion",
    "command_grammar",
    "complete_command",
    "format_command",
    "parse_command",
    "split_pipeline",
    "suggest_commands",
]
