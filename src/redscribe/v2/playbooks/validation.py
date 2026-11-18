"""Structural validation for playbook domain objects."""

from __future__ import annotations

import re

from redscribe.v2.playbooks.dag import validate_dag
from redscribe.v2.playbooks.errors import ValidationError
from redscribe.v2.playbooks.interpolate import validate_source, variables_in
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Condition,
    Issue,
    Playbook,
    PlaybookStep,
    SnippetRecord,
    TemplateRecord,
    VariableDefinition,
    VariableKind,
)

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_STEP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def ensure_valid(issues: tuple[Issue, ...], message: str = "Validation failed") -> None:
    """Raise a validation error when any issue has error severity."""
    errors = tuple(issue for issue in issues if issue.is_error)
    if errors:
        raise ValidationError(message, issues=errors)


def validate_key(key: str, *, label: str = "Key") -> tuple[Issue, ...]:
    """Validate a stable slug-style identifier."""
    if not key.strip():
        return (Issue("missing-key", f"{label} is required"),)
    if _KEY_RE.match(key) is None:
        return (
            Issue(
                code="invalid-key",
                message=f"{label} must use lowercase letters, digits, '-' or '_' (2-64 chars)",
            ),
        )
    return ()


def validate_version(version: str) -> tuple[Issue, ...]:
    """Validate a semantic version string."""
    if _VERSION_RE.match(version) is None:
        return (Issue("invalid-version", f"Version must be MAJOR.MINOR.PATCH: {version}"),)
    return ()


def validate_variable(
    definition: VariableDefinition,
    *,
    path: str = "variables",
    known_variables: set[str] | None = None,
) -> tuple[Issue, ...]:
    """Validate one variable definition."""
    issues = list(validate_key(definition.key, label="Variable key"))
    if definition.kind == VariableKind.CHOICE and not definition.choices:
        issues.append(
            Issue("missing-choices", f"Choice variable has no choices: {definition.key}", path=path)
        )
    if definition.pattern:
        try:
            re.compile(definition.pattern)
        except re.error as exc:
            issues.append(
                Issue("invalid-pattern", f"Invalid pattern for {definition.key}: {exc}", path=path)
            )
    if (
        definition.minimum is not None
        and definition.maximum is not None
        and definition.minimum > definition.maximum
    ):
        issues.append(
            Issue("invalid-range", f"Minimum exceeds maximum for {definition.key}", path=path)
        )
    if known_variables is not None and definition.key not in known_variables:
        issues.append(
            Issue("undeclared-variable", f"Variable is not declared: {definition.key}", path=path)
        )
    return tuple(issues)


def validate_condition(
    condition: Condition,
    *,
    known_variables: set[str] | None = None,
    path: str = "condition",
) -> tuple[Issue, ...]:
    """Validate one structured condition."""
    issues: list[Issue] = []
    if not condition.field.strip():
        issues.append(Issue("missing-field", "Condition has no field", path=path))
    elif known_variables is not None and condition.field not in known_variables:
        issues.append(
            Issue(
                code="unknown-variable",
                message=f"Condition references unknown variable: {condition.field}",
                path=path,
            )
        )
    if condition.operator.value == "matches":
        try:
            re.compile(str(condition.value))
        except re.error as exc:
            issues.append(Issue("invalid-regex", f"Invalid condition regex: {exc}", path=path))
    return tuple(issues)


def validate_checklist_item(
    item: ChecklistItem,
    *,
    known_variables: set[str] | None = None,
    path: str = "checklist",
) -> tuple[Issue, ...]:
    """Validate one checklist item and its optional gate."""
    issues: list[Issue] = []
    if not item.id.strip():
        issues.append(Issue("missing-item-id", "Checklist item has no id", path=path))
    if not item.label.strip():
        issues.append(Issue("missing-label", f"Checklist item {item.id} has no label", path=path))
    if item.condition is not None:
        issues.extend(
            validate_condition(
                item.condition, known_variables=known_variables, path=f"{path}.{item.id}"
            )
        )
    return tuple(issues)


def validate_step(
    step: PlaybookStep,
    *,
    known_steps: set[str],
    known_variables: set[str] | None = None,
    known_snippets: set[str] | None = None,
    path: str = "steps",
) -> tuple[Issue, ...]:
    """Validate one playbook step."""
    issues: list[Issue] = []
    if _STEP_ID_RE.match(step.id) is None:
        issues.append(Issue("invalid-step-id", f"Invalid step id: {step.id}", path=path))
    if not step.title.strip():
        issues.append(Issue("missing-title", f"Step {step.id} has no title", path=path))
    if step.estimated_minutes < 0:
        issues.append(
            Issue("negative-duration", f"Step {step.id} has a negative duration", path=path)
        )
    for dependency in step.depends_on:
        if dependency not in known_steps:
            issues.append(
                Issue(
                    code="unknown-dependency",
                    message=f"Step {step.id} depends on unknown step: {dependency}",
                    path=path,
                )
            )
    if step.snippet_key and known_snippets is not None and step.snippet_key not in known_snippets:
        issues.append(
            Issue(
                code="unknown-snippet",
                message=f"Step {step.id} references unknown snippet: {step.snippet_key}",
                path=path,
            )
        )
    for condition in step.when:
        issues.extend(
            validate_condition(
                condition, known_variables=known_variables, path=f"{path}.{step.id}.when"
            )
        )
    for name in step.variables:
        if known_variables is not None and name not in known_variables:
            issues.append(
                Issue(
                    code="unknown-variable",
                    message=f"Step {step.id} references undeclared variable: {name}",
                    path=path,
                )
            )
    for name in variables_in(step.command_template):
        if known_variables is not None and name not in known_variables:
            issues.append(
                Issue(
                    code="unknown-variable",
                    message=f"Command in step {step.id} uses undeclared variable: {name}",
                    path=path,
                )
            )
    issues.extend(validate_expression_source(step.command_template, path=f"{path}.{step.id}"))
    seen_items: set[str] = set()
    for item in step.checklist:
        if item.id in seen_items:
            issues.append(
                Issue("duplicate-item", f"Duplicate checklist item: {item.id}", path=path)
            )
        seen_items.add(item.id)
        issues.extend(
            validate_checklist_item(item, known_variables=known_variables, path=f"{path}.{step.id}")
        )
    return tuple(issues)


def validate_expression_source(source: str, *, path: str = "") -> tuple[Issue, ...]:
    """Validate interpolation syntax in a command or note."""
    return validate_source(source) if "{{" in source or "}}" in source else ()


def validate_playbook(
    playbook: Playbook,
    *,
    known_snippets: set[str] | None = None,
) -> tuple[Issue, ...]:
    """Validate a whole playbook, including its DAG and metadata."""
    issues: list[Issue] = []
    issues.extend(validate_key(playbook.key, label="Playbook key"))
    issues.extend(validate_version(playbook.version))
    if not playbook.title.strip():
        issues.append(Issue("missing-title", "Playbook has no title"))
    seen_variables: set[str] = set()
    for definition in playbook.variables:
        if definition.key in seen_variables:
            issues.append(Issue("duplicate-variable", f"Duplicate variable: {definition.key}"))
        seen_variables.add(definition.key)
        issues.extend(validate_variable(definition, path=f"{playbook.key}.variables"))
    known_variables = seen_variables | {
        "target",
        "domain",
        "url",
        "host",
        "ip",
        "port",
        "date",
        "slug",
        "user",
        "password",
        "lhost",
        "lport",
    }
    known_steps = {step.id for step in playbook.steps}
    seen_steps: set[str] = set()
    for step in playbook.steps:
        if step.id in seen_steps:
            issues.append(Issue("duplicate-step", f"Duplicate step id: {step.id}"))
        seen_steps.add(step.id)
        issues.extend(
            validate_step(
                step,
                known_steps=known_steps,
                known_variables=known_variables,
                known_snippets=known_snippets,
                path=f"{playbook.key}.steps",
            )
        )
    graph = validate_dag(playbook.steps)
    for cycle in graph.cycles:
        issues.append(
            Issue("cycle", f"Step dependency cycle: {' -> '.join(cycle)}", path=playbook.key)
        )
    for name in graph.missing:
        issues.append(Issue("unknown-dependency", f"Missing dependency: {name}", path=playbook.key))
    return tuple(issues)


def validate_snippet(snippet: SnippetRecord) -> tuple[Issue, ...]:
    """Validate a snippet record."""
    issues = list(validate_key(snippet.key, label="Snippet key"))
    issues.extend(validate_version(snippet.version))
    if not snippet.title.strip():
        issues.append(Issue("missing-title", "Snippet has no title"))
    if not snippet.command.strip():
        issues.append(Issue("missing-command", f"Snippet {snippet.key} has no command"))
    issues.extend(validate_expression_source(snippet.command, path=snippet.key))
    return tuple(issues)


def validate_template(template: TemplateRecord) -> tuple[Issue, ...]:
    """Validate a template record and its declared variables."""
    issues = list(validate_key(template.key, label="Template key"))
    issues.extend(validate_version(template.version))
    if not template.name.strip():
        issues.append(Issue("missing-name", "Template has no name"))
    issues.extend(validate_expression_source(template.content, path=template.key))
    known = {item.key for item in template.variables}
    for definition in template.variables:
        issues.extend(validate_variable(definition, path=f"{template.key}.variables"))
    for name in variables_in(template.content):
        if name not in known and name not in ("title", "date", "target", "slug"):
            issues.append(
                Issue(
                    code="undeclared-variable",
                    message=f"Template uses undeclared variable: {name}",
                    path=template.key,
                )
            )
    return tuple(issues)
