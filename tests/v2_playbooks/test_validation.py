from __future__ import annotations

import pytest

from redscribe.v2.playbooks.errors import ValidationError
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Condition,
    ConditionOperator,
    Playbook,
    PlaybookStep,
    SnippetRecord,
    TemplateRecord,
    VariableDefinition,
    VariableKind,
)
from redscribe.v2.playbooks.validation import (
    ensure_valid,
    validate_checklist_item,
    validate_condition,
    validate_expression_source,
    validate_key,
    validate_playbook,
    validate_snippet,
    validate_step,
    validate_template,
    validate_variable,
    validate_version,
)


def test_validate_key_accepts_stable_slugs() -> None:
    assert validate_key("web-app-assessment") == ()
    assert validate_key("step_2") == ()


@pytest.mark.parametrize("key", ["", "A", "a", "-bad", "bad key", "x" * 65])
def test_validate_key_rejects_bad_slugs(key: str) -> None:
    assert validate_key(key)


def test_validate_version_requires_semantic_version() -> None:
    assert validate_version("1.2.3") == ()
    assert validate_version("v1.2.3")
    assert validate_version("1.2")


def test_validate_variable_reports_kind_and_range_issues() -> None:
    choice = VariableDefinition("level", kind=VariableKind.CHOICE)
    bad_pattern = VariableDefinition("code", pattern="[")
    bad_range = VariableDefinition("num", minimum=10, maximum=1)

    assert validate_variable(choice)[0].code == "missing-choices"
    assert validate_variable(bad_pattern)[0].code == "invalid-pattern"
    assert validate_variable(bad_range)[0].code == "invalid-range"


def test_validate_variable_checks_known_variables() -> None:
    definition = VariableDefinition("target")

    assert validate_variable(definition, known_variables={"target"}) == ()
    assert validate_variable(definition, known_variables={"other"})[0].code == "undeclared-variable"


def test_validate_condition_checks_field_variable_and_regex() -> None:
    assert validate_condition(Condition(field="target")) == ()
    assert validate_condition(Condition(field=""))[0].code == "missing-field"
    assert validate_condition(Condition(field="missing"), known_variables={"target"})[0].code == (
        "unknown-variable"
    )
    regex_condition = Condition(field="target", operator=ConditionOperator.MATCHES, value="[")
    assert validate_condition(regex_condition)[0].code == "invalid-regex"


def test_validate_checklist_item_checks_id_label_and_condition() -> None:
    item = ChecklistItem(id="c1", label="Check")
    assert validate_checklist_item(item) == ()

    invalid = ChecklistItem(id="", label="", condition=Condition(field="unknown"))
    codes = {issue.code for issue in validate_checklist_item(invalid, known_variables={"target"})}

    assert {"missing-item-id", "missing-label", "unknown-variable"}.issubset(codes)


def test_validate_step_checks_dependencies_and_variables() -> None:
    step = PlaybookStep(
        id="a",
        title="Step",
        command_template="echo {{ target }} {{ mystery }}",
        depends_on=("missing",),
        snippet_key="unknown",
        variables=("undeclared",),
        estimated_minutes=-1,
    )
    issues = validate_step(
        step,
        known_steps={"a"},
        known_variables={"target"},
        known_snippets={"known"},
    )
    codes = {issue.code for issue in issues}

    assert {
        "unknown-dependency",
        "unknown-snippet",
        "unknown-variable",
        "negative-duration",
    }.issubset(codes)


def test_validate_step_detects_duplicate_checklist_items() -> None:
    items = (ChecklistItem(id="c1", label="One"), ChecklistItem(id="c1", label="Two"))
    step = PlaybookStep(id="a", title="Step", checklist=items)

    issues = validate_step(step, known_steps={"a"})

    assert any(issue.code == "duplicate-item" for issue in issues)


def test_validate_step_accepts_clean_step() -> None:
    step = PlaybookStep(id="a", title="Step", command_template="echo {{ target }}")

    assert validate_step(step, known_steps={"a"}, known_variables={"target"}) == ()


def test_validate_expression_source_reports_bad_placeholders() -> None:
    assert validate_expression_source("plain text") == ()
    assert validate_expression_source("{{ target | upper }}") == ()
    assert validate_expression_source("{{ target | bogus }}")[0].code == "unknown-filter"


def test_validate_playbook_accepts_fixture(playbook: Playbook) -> None:
    assert validate_playbook(playbook) == ()


def test_validate_playbook_reports_duplicate_variables_and_steps(playbook: Playbook) -> None:
    duplicate_variable = VariableDefinition("target", label="Target")
    duplicate_step = PlaybookStep(id="a", title="Duplicate")
    updated = playbook.with_changes(
        variables=(*playbook.variables, duplicate_variable),
        steps=(*playbook.steps, duplicate_step),
    )

    codes = {issue.code for issue in validate_playbook(updated)}

    assert "duplicate-variable" in codes
    assert "duplicate-step" in codes


def test_validate_playbook_reports_cycle(playbook: Playbook) -> None:
    first = playbook.steps[0].with_changes(depends_on=(playbook.steps[-1].id,))
    updated = playbook.with_changes(steps=(first, *playbook.steps[1:]))

    assert any(issue.code == "cycle" for issue in validate_playbook(updated))


def test_validate_snippet_requires_key_title_and_command() -> None:
    invalid = SnippetRecord(id=1, key="A", title="", command="")
    codes = {issue.code for issue in validate_snippet(invalid)}

    assert {"invalid-key", "missing-title", "missing-command"}.issubset(codes)


def test_validate_snippet_accepts_valid_record() -> None:
    snippet = SnippetRecord(id=1, key="nmap-scan", title="Nmap", command="nmap {{ target }}")

    assert validate_snippet(snippet) == ()


def test_validate_template_checks_content_and_declared_variables() -> None:
    template = TemplateRecord(
        id=1,
        key="report",
        name="Report",
        content="# {{ title }}\n{{ target }}\n{{ undeclared }}",
        variables=(VariableDefinition("title", required=True),),
    )
    codes = {issue.code for issue in validate_template(template)}

    assert "undeclared-variable" in codes


def test_validate_template_accepts_clean_record() -> None:
    template = TemplateRecord(
        id=1,
        key="report",
        name="Report",
        content="# {{ title }}",
        variables=(VariableDefinition("title", required=True),),
    )

    assert validate_template(template) == ()


def test_ensure_valid_raises_on_error_severity() -> None:
    from redscribe.v2.playbooks.types import Issue

    with pytest.raises(ValidationError, match="Validation failed"):
        ensure_valid((Issue("bad", "Broken"), Issue("warn", "Warning", severity="warning")))


def test_ensure_valid_allows_warnings_only() -> None:
    from redscribe.v2.playbooks.types import Issue

    ensure_valid((Issue("warn", "Warning", severity="warning"),))
