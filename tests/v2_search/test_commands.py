from __future__ import annotations

import pytest

from redscribe.v2.search.commands.catalog import (
    CommandCatalog,
    command_issues_summary,
    command_metadata,
    commands_by_prefix,
    merge_issue_lists,
    spec_from_mapping,
)
from redscribe.v2.search.commands.grammar import (
    argument_map,
    command_context,
    command_grammar,
    format_command,
    lex_command,
    parse_command,
    split_pipeline,
    validate_arguments,
)
from redscribe.v2.search.commands.models import CommandKind, ParseIssue
from redscribe.v2.search.commands.suggestions import (
    apply_suggestion,
    complete_command,
    prefix_matches,
    rank_suggestions,
    suggest_arguments,
    suggest_commands,
    suggestion_labels,
)
from redscribe.v2.search.models import SavedQuery


def test_lex_command_handles_quotes_and_options() -> None:
    tokens = lex_command('/search "open ports" --limit=5')
    assert tokens[0].text == "/search"
    assert any(token.quoted for token in tokens)
    assert any(token.text.startswith("--") for token in tokens)


def test_parse_command_builds_node_and_options() -> None:
    parsed = parse_command("/search nmap --limit=5")
    assert parsed.node is not None
    assert parsed.node.name == "search"
    assert parsed.node.option("limit") == "5"
    assert parsed.node.option("missing", "default") == "default"
    assert [item.value for item in parsed.node.positional] == ["nmap"]
    assert format_command(parsed.node).startswith("/search")


def test_parse_command_reports_missing_prefix_and_empty_input() -> None:
    assert any(issue.code == "missing-prefix" for issue in parse_command("search nmap").issues)
    assert any(issue.code == "empty-command" for issue in parse_command("").issues)
    assert parse_command("").node is None


def test_catalog_resolves_aliases_and_issues() -> None:
    catalog = CommandCatalog.default()
    assert catalog.get("search")
    assert catalog.get("find") is not None
    assert "search" in catalog.names()
    assert len(catalog.all()) >= 10
    assert catalog.by_kind(CommandKind.NAVIGATION)
    parsed = catalog.parse("/bogus value")
    assert any(issue.code == "unknown-command" for issue in parsed.issues)
    assert catalog.parse("/search").ok is True


def test_catalog_unregister_and_metadata() -> None:
    catalog = CommandCatalog.default()
    original = len(catalog.all())
    assert catalog.unregister("reindex") is True
    assert catalog.unregister("reindex") is False
    assert len(catalog.all()) == original - 1
    metadata = command_metadata(catalog)
    assert metadata["count"] == len(catalog.all())
    assert isinstance(metadata["aliases"], dict)
    assert "search" in commands_by_prefix(catalog, "sea")[0].name


def test_validate_arguments_reports_missing_and_excess() -> None:
    catalog = CommandCatalog.default()
    spec = catalog.get("status")
    assert spec is not None
    node = parse_command("/status bogus").node
    assert node is not None
    from dataclasses import replace

    from redscribe.v2.search.commands.models import CommandArgument

    node = replace(node, arguments=(CommandArgument("status", "bogus", 8),))
    issues = validate_arguments(node, spec)
    assert issues


def test_command_plan_is_side_effect_free() -> None:
    catalog = CommandCatalog.default()
    node = catalog.parse("/search nmap tag:web --limit=7").node
    assert node is not None
    plan = catalog.plan(node)
    assert plan.action == "search"
    assert plan.as_dict()["name"] == "search"
    assert "limit" in dict(node.options)


def test_command_grammar_and_pipeline_helpers() -> None:
    grammar = command_grammar()
    assert grammar["prefixes"] == ["/", ":"]
    assert split_pipeline("/search nmap | /sort title") == ("/search nmap", "/sort title")
    node = parse_command("/search nmap --sort=title").node
    assert node is not None
    assert argument_map(node)["1"] == "nmap"
    assert node.options["sort"] == "title"
    assert command_context("/search nm", len("/search nm")) in {"argument", "term"}


def test_issue_helpers_deduplicate() -> None:
    issues = (ParseIssue("a", "First", 0), ParseIssue("b", "Second", 1))
    assert "First" in command_issues_summary(issues)
    assert len(merge_issue_lists(issues, issues[:1])) == 2


def test_spec_from_mapping_validates_payload() -> None:
    spec = spec_from_mapping(
        {
            "name": "Audit",
            "aliases": ["audit", "check"],
            "description": "Audit notes",
            "usage": "/audit",
        }
    )
    assert spec.name == "audit"
    assert "check" in spec.aliases
    with pytest.raises(ValueError):
        spec_from_mapping({})
    with pytest.raises(ValueError):
        spec_from_mapping({"name": "Bad", "aliases": "not a list"})


def test_command_suggestions_rank_and_apply() -> None:
    catalog = CommandCatalog.default()
    saved = (SavedQuery("sq_1", "Weekly", "nmap", pinned=True),)
    suggestions = suggest_commands("/se", catalog, saved=saved, limit=5)
    labels = suggestion_labels(suggestions)
    assert "/search" in labels
    assert "/saved" in labels
    assert suggestions[0].score >= suggestions[-1].score
    assert apply_suggestion("/se", suggestions[0]) == suggestions[0].insert_text
    assert prefix_matches(catalog, "sea")
    assert rank_suggestions(suggestions)[0].score >= rank_suggestions(suggestions)[-1].score


def test_suggest_arguments_and_completion() -> None:
    catalog = CommandCatalog.default()
    status_spec = catalog.get("status")
    assert status_spec is not None
    arguments = suggest_arguments(status_spec, "ac")
    assert any(item.label == "active" for item in arguments)
    completion = complete_command("/se", catalog)
    assert completion.context in {"command", "argument", "option"}
    assert completion.suggestions
    assert completion.as_dict()["text"] == "/se"
