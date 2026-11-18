from __future__ import annotations

import pytest

from redscribe.v2.playbooks.catalog import PLAYBOOKS
from redscribe.v2.playbooks.dag import validate_dag
from redscribe.v2.playbooks.errors import (
    DuplicateKeyError,
    UnknownSnippetError,
    UnknownTemplateError,
)
from redscribe.v2.playbooks.snippets import (
    SnippetLibrary,
    builtin_snippets,
    compose_snippets,
    snippet_refs,
    snippet_variables,
)
from redscribe.v2.playbooks.templates import EXTRA_TEMPLATES, TemplateEngine, builtin_templates
from redscribe.v2.playbooks.types import SnippetRecord, TemplateRecord, VariableDefinition
from redscribe.v2.playbooks.validation import validate_playbook


def test_curated_catalog_is_valid_and_diverse() -> None:
    assert len(PLAYBOOKS) == 8
    assert len({item.key for item in PLAYBOOKS}) == len(PLAYBOOKS)
    assert all(validate_playbook(item) == () for item in PLAYBOOKS)
    assert len({item.category for item in PLAYBOOKS}) >= 6


def test_curated_catalog_graphs_are_acyclic() -> None:
    for playbook in PLAYBOOKS:
        assert validate_dag(playbook.steps).ok, playbook.key


def test_builtin_snippets_are_valid_and_belong_to_builtin_library() -> None:
    snippets = builtin_snippets()

    assert len(snippets) > 40
    assert len({item.key for item in snippets}) == len(snippets)
    assert all(item.library == "builtin" for item in snippets)
    assert all(item.variables == snippet_variables(item.command) for item in snippets)


def test_snippet_variables_and_references_are_distinct() -> None:
    command = "run {{ target }} && {{snippet:base}} && {{ target }}"

    assert snippet_variables(command) == ("target",)
    assert snippet_refs(command) == ("base",)


def test_snippet_library_crud_and_search() -> None:
    library = SnippetLibrary()
    record = SnippetRecord(
        id=1,
        key="scan",
        title="Scan target",
        command="nmap {{ target }}",
        tags=("recon", "network"),
        variables=("target",),
    )

    library.add(record)
    assert library.get("SCAN") == record.with_changes(key="scan")
    assert [item.key for item in library.search("scan")] == ["scan"]
    assert [item.key for item in library.search(tags=("network",))] == ["scan"]

    library.record_usage("scan")
    assert library.get("scan").usage_count == 1

    updated = library.update("scan", title="Updated scan")
    assert updated.title == "Updated scan"

    removed = library.remove("scan")
    assert removed.key == "scan"
    assert len(library) == 0


def test_snippet_library_rejects_duplicates_and_unknown_keys() -> None:
    library = SnippetLibrary()
    record = SnippetRecord(id=1, key="scan", title="Scan", command="nmap {{ target }}")
    library.add(record)

    with pytest.raises(DuplicateKeyError):
        library.add(record)

    with pytest.raises(UnknownSnippetError):
        library.get("missing")


def test_snippet_library_replace_all_is_atomic() -> None:
    library = SnippetLibrary()
    records = [
        SnippetRecord(id=1, key="one", title="One", command="echo one"),
        SnippetRecord(id=2, key="two", title="Two", command="echo two"),
    ]
    library.replace_all(records)

    assert [item.key for item in library.to_records()] == ["one", "two"]

    with pytest.raises(DuplicateKeyError):
        library.replace_all([records[0], records[0]])

    assert [item.key for item in library.to_records()] == ["one", "two"]


def test_snippet_library_stats_and_serialization() -> None:
    library = SnippetLibrary()
    library.add(SnippetRecord(id=1, key="one", title="One", command="echo {{ target }}"))
    library.record_usage("one")

    stats = library.stats()
    assert stats["total"] == 1
    assert stats["usage_count"] == 1
    assert stats["variables"] == ["target"]

    assert "command" in library.as_dict()[0]
    assert "command" not in library.as_dict(include_commands=False)[0]


def test_compose_snippets_expands_references() -> None:
    records = (
        SnippetRecord(id=1, key="base", title="Base", command="scan {{ target }}"),
        SnippetRecord(id=2, key="full", title="Full", command="{{snippet:base}} -A"),
    )
    result = compose_snippets(records, {"target": "example.com"})

    assert result.command == "scan example.com -A"
    assert result.order == ("full", "base")
    assert result.ok


def test_compose_snippets_reports_cycles_and_missing_references() -> None:
    cyclic = compose_snippets(
        (
            SnippetRecord(id=1, key="a", title="A", command="{{snippet:b}}"),
            SnippetRecord(id=2, key="b", title="B", command="{{snippet:a}}"),
        )
    )
    missing = compose_snippets(
        (SnippetRecord(id=1, key="a", title="A", command="{{snippet:gone}}"),)
    )

    assert cyclic.cycles
    assert not cyclic.ok
    assert missing.missing == ("gone",)


def test_builtin_templates_include_playbook_templates() -> None:
    templates = builtin_templates()
    keys = {item.key for item in templates}

    assert len(templates) > 5
    assert {item.key for item in EXTRA_TEMPLATES}.issubset(keys)
    assert [item.key for item in EXTRA_TEMPLATES] == [
        "playbook-run",
        "step-log",
        "checklist-summary",
    ]


def test_template_engine_catalog_is_valid() -> None:
    assert TemplateEngine().validate_catalog() == ()


def test_template_engine_crud_and_history() -> None:
    engine = TemplateEngine(())
    record = TemplateRecord(
        id=1,
        key="custom",
        name="Custom",
        content="# {{ title }}",
        variables=(VariableDefinition("title", required=True),),
    )

    engine.register(record)
    assert engine.get("custom").name == "Custom"
    assert engine.version("custom") == "1.0.0"

    engine.register(record.with_changes(content="# {{ title }}\nBody", version="1.1.0"))
    assert engine.version("custom") == "1.1.0"
    assert len(engine.history("custom")["entries"]) == 2

    removed = engine.remove("custom")
    assert removed.key == "custom"
    with pytest.raises(UnknownTemplateError):
        engine.get("custom")


def test_template_engine_register_is_idempotent() -> None:
    engine = TemplateEngine(())
    record = TemplateRecord(id=1, key="custom", name="Custom", content="Body")

    engine.register(record)
    engine.register(record)

    assert len(engine.history("custom")["entries"]) == 1


def test_template_engine_list_and_suggest() -> None:
    engine = TemplateEngine()
    playbook_templates = engine.list_records(category="playbooks")

    assert [item.key for item in playbook_templates] == [
        "checklist-summary",
        "playbook-run",
        "step-log",
    ]
    assert engine.list_records(tags=("checklist",))[0].key == "checklist-summary"
    assert engine.suggest("playbook-run")[0].record.key == "playbook-run"


def test_template_engine_render_and_strict_mode() -> None:
    engine = TemplateEngine()
    rendered = engine.render(
        "playbook-run",
        {"title": "Assessment", "playbook": "web", "target": "example.com"},
    )

    assert "Assessment" in rendered.content
    assert "example.com" in rendered.content
    assert "title" in rendered.used

    with pytest.raises(ValueError, match="Missing required template variables"):
        engine.render("playbook-run", {}, strict=True)


def test_template_engine_render_source_and_history_errors() -> None:
    engine = TemplateEngine()
    ad_hoc = engine.render_source("Hello {{ name }}", {"name": "world"})

    assert ad_hoc.key == "ad-hoc"
    assert ad_hoc.content == "Hello world"

    with pytest.raises(UnknownTemplateError):
        engine.history("missing")
