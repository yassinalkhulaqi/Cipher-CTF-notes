"""Parameterized query templates with safe placeholder rendering."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace

from redscribe.v3.search_intel.types import QueryTemplate

_PLACEHOLDER: re.Pattern[str] = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_SAFE_VALUE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")


def extract_placeholders(pattern: str) -> tuple[str, ...]:
    """Return placeholder names in first-appearance order."""
    return tuple(dict.fromkeys(_PLACEHOLDER.findall(pattern)))


def render_value(value: object) -> str:
    """Escape a placeholder value for safe inclusion in a v2 query."""
    text = " ".join(str(value).split())
    if _SAFE_VALUE.fullmatch(text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_template(template: QueryTemplate, values: Mapping[str, object]) -> str:
    """Render a template, rejecting missing and unknown placeholders."""
    placeholders = set(extract_placeholders(template.pattern) or template.placeholders)
    supplied = set(values)
    missing = sorted(placeholders - supplied)
    if missing:
        raise ValueError(f"Missing template values: {', '.join(missing)}")
    unknown = sorted(supplied - placeholders)
    if unknown:
        raise ValueError(f"Unknown template values: {', '.join(unknown)}")
    ordered = extract_placeholders(template.pattern) or template.placeholders
    rendered = template.pattern
    for name in ordered:
        value = values[name]
        if value is None or not str(value).strip():
            raise ValueError(f"Template value '{name}' cannot be empty")
        rendered = rendered.replace("{" + name + "}", render_value(value))
    return " ".join(rendered.split())


class TemplateRegistry:
    """Registry of built-in and branch-provided query templates."""

    def __init__(self, templates: Sequence[QueryTemplate] = ()) -> None:
        self._items: dict[str, QueryTemplate] = {}
        for template in templates:
            self.add(template)
        for template in default_templates():
            self.add(template)

    def add(self, template: QueryTemplate) -> QueryTemplate:
        """Add a template, rejecting duplicate ids."""
        if template.id in self._items:
            raise ValueError(f"Template already registered: {template.id}")
        if not template.placeholders:
            template = replace(template, placeholders=extract_placeholders(template.pattern))
        self._items[template.id] = template
        return template

    def get(self, template_id: str) -> QueryTemplate | None:
        """Look up a template by id."""
        return self._items.get(template_id)

    def list(self, *, category: str = "") -> tuple[QueryTemplate, ...]:
        """List templates in stable order, optionally by category."""
        items = [
            template
            for template in self._items.values()
            if not category or template.category == category.casefold()
        ]
        return tuple(sorted(items, key=lambda item: (item.category, item.name, item.id)))

    def render(self, template_id: str, values: Mapping[str, object]) -> str:
        """Render a registered template."""
        template = self.get(template_id)
        if template is None:
            raise KeyError(template_id)
        return render_template(template, values)

    def suggest(self, text: str, *, limit: int = 5) -> tuple[QueryTemplate, ...]:
        """Score templates against free-text intent."""
        tokens = {token for token in re.findall(r"[a-z]+", text.casefold()) if len(token) > 2}
        if not tokens:
            return self.list()[: max(0, limit)]
        scored: list[tuple[float, QueryTemplate]] = []
        for template in self.list():
            description = f"{template.name} {template.description} {template.pattern}"
            haystack = {
                token for token in re.findall(r"[a-z]+", description.casefold()) if len(token) > 2
            }
            name_bonus = 0.5 if template.name.casefold() in text.casefold() else 0.0
            prefix_bonus = float(
                sum(1 for needle in tokens if any(token.startswith(needle) for token in haystack))
            )
            score = len(tokens & haystack) + name_bonus + prefix_bonus
            if score > 0:
                scored.append((score, template))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(template for _score, template in scored[: max(0, limit)])


def default_templates() -> tuple[QueryTemplate, ...]:
    """Return the built-in cross-entity query templates."""
    specs = (
        (
            "critical-findings",
            "Critical findings",
            "kind:finding severity:critical",
            "All findings marked critical.",
            "triage",
            "",
        ),
        (
            "findings-for-target",
            "Findings for target",
            "kind:finding {target}",
            "Findings that mention a target.",
            "pivot",
            'kind:finding "web-01"',
        ),
        (
            "evidence-before",
            "Evidence before date",
            "kind:evidence before:{date}",
            "Evidence updated before a date.",
            "history",
            "kind:evidence before:2024-06-01",
        ),
        (
            "tagged-entities",
            "Tagged entities",
            "tag:{tag}",
            "Any entity carrying a tag.",
            "general",
            "tag:recon",
        ),
        (
            "linked-findings",
            "Findings with evidence",
            "kind:finding has:link(evidences)",
            "Findings that have an evidence link.",
            "pivot",
            "",
        ),
        (
            "status-triage",
            "Status by kind",
            "kind:{kind} status:{status}",
            "Entities of a kind in a lifecycle state.",
            "triage",
            "kind:note status:active",
        ),
        (
            "report-context",
            "Report by title",
            "kind:report {title}",
            "Find a report by title.",
            "pivot",
            'kind:report "client report"',
        ),
        (
            "recent-activity",
            "Recent activity",
            "kind:activity before:{date}",
            "Activity before a date boundary.",
            "history",
            "kind:activity before:2024-01-01",
        ),
    )
    return tuple(
        QueryTemplate(
            id=item_id,
            name=name,
            pattern=pattern,
            description=description,
            placeholders=extract_placeholders(pattern),
            category=category,
            example=example,
        )
        for item_id, name, pattern, description, category, example in specs
    )
