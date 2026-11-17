"""Template catalog and rendering engine for the playbooks feature."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from redscribe.content.templates import TEMPLATES
from redscribe.v2.playbooks.errors import DuplicateKeyError, UnknownTemplateError
from redscribe.v2.playbooks.interpolate import render, variables_in
from redscribe.v2.playbooks.types import (
    Issue,
    TemplateRecord,
    TemplateRender,
    Values,
    VariableDefinition,
)
from redscribe.v2.playbooks.validation import ensure_valid, validate_template
from redscribe.v2.playbooks.versions import VersionHistory, bump_version

_PLAYBOOK_TEMPLATE = """# {{ title }}

- **Playbook:** {{ playbook }}
- **Target:** {{ target }}
- **Version:** {{ version }}
- **Run:** {{ run_id }}

## Objectives

{{ objectives | default("Describe the objective of this run.") }}

## Step log

| Step | Status | Notes |
|------|--------|-------|
|      |        |       |

## Evidence

- [ ] Capture command output
- [ ] Attach supporting files
- [ ] Record timestamps

## Outcome

{{ outcome | default("Pending") }}
"""

_STEP_TEMPLATE = """## {{ title }}

- **Step id:** {{ step_id }}
- **Command:** `{{ command | default("n/a") }}`

### Observations

{{ observations | default("Add observations here.") }}

### Result

- [ ] Completed
- [ ] Evidence attached
"""

_CHECKLIST_TEMPLATE = """# Checklist: {{ title }}

Target: {{ target | default("n/a") }}

- [ ] {{ checklist | default("No items recorded") }}

Notes: {{ notes | default("None") }}
"""

EXTRA_TEMPLATES: tuple[TemplateRecord, ...] = (
    TemplateRecord(
        id=1001,
        key="playbook-run",
        name="Playbook run",
        content=_PLAYBOOK_TEMPLATE,
        description="Run metadata, step log, evidence, and outcome.",
        tags=("playbook", "run"),
        category="playbooks",
        variables=(
            VariableDefinition("title", "Title", required=True),
            VariableDefinition("playbook", "Playbook"),
            VariableDefinition("target", "Target"),
            VariableDefinition("version", "Version"),
            VariableDefinition("run_id", "Run id"),
            VariableDefinition("objectives", "Objectives"),
            VariableDefinition("outcome", "Outcome"),
        ),
    ),
    TemplateRecord(
        id=1002,
        key="step-log",
        name="Step log",
        content=_STEP_TEMPLATE,
        description="A compact record for one executed step.",
        tags=("playbook", "step"),
        category="playbooks",
        variables=(
            VariableDefinition("title", "Title", required=True),
            VariableDefinition("step_id", "Step id"),
            VariableDefinition("command", "Command"),
            VariableDefinition("observations", "Observations"),
        ),
    ),
    TemplateRecord(
        id=1003,
        key="checklist-summary",
        name="Checklist summary",
        content=_CHECKLIST_TEMPLATE,
        description="Human-readable checklist export.",
        tags=("playbook", "checklist"),
        category="playbooks",
        variables=(
            VariableDefinition("title", "Title", required=True),
            VariableDefinition("target", "Target"),
            VariableDefinition("checklist", "Checklist"),
            VariableDefinition("notes", "Notes"),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class TemplateSuggestion:
    """A template suggestion with a match score."""

    record: TemplateRecord
    score: float
    reason: str


def builtin_templates() -> tuple[TemplateRecord, ...]:
    """Convert the v1 template catalog into v2 records."""
    records: list[TemplateRecord] = []
    for index, template in enumerate(TEMPLATES, start=1):
        variables: list[VariableDefinition] = []
        if "title" in variables_in(template.content) or template.default_title:
            variables.append(
                VariableDefinition("title", "Title", required=bool(template.default_title))
            )
        for name in variables_in(template.content):
            if name in ("title", "date"):
                continue
            variables.append(VariableDefinition(name, name.replace("_", " ").title()))
        records.append(
            TemplateRecord(
                id=index,
                key=template.key,
                name=template.name,
                content=template.content,
                description=template.description,
                tags=tuple(tag.strip() for tag in template.tags.split(",") if tag.strip()),
                category=template.tags.split(",", 1)[0] if template.tags else "general",
                variables=tuple(variables),
                version="1.0.0",
                default_title=template.default_title,
            )
        )
    return tuple(records) + EXTRA_TEMPLATES


class TemplateEngine:
    """A registry of templates with pure rendering and version metadata."""

    def __init__(self, records: tuple[TemplateRecord, ...] | None = None) -> None:
        self._records: dict[str, TemplateRecord] = {}
        self._histories: dict[str, VersionHistory] = {}
        for record in records if records is not None else builtin_templates():
            self._insert(record, validate=False)

    def __len__(self) -> int:
        return len(self._records)

    @property
    def records(self) -> tuple[TemplateRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def get(self, key: str) -> TemplateRecord:
        """Return one template or raise."""
        record = self._records.get(key.strip().casefold())
        if record is None:
            raise UnknownTemplateError(f"Template not found: {key}", details={"key": key})
        return record

    def find(self, key: str) -> TemplateRecord | None:
        """Return one template or ``None``."""
        return self._records.get(key.strip().casefold())

    def _insert(self, record: TemplateRecord, *, validate: bool = True) -> TemplateRecord:
        key = record.key.strip().casefold()
        if key in self._records:
            raise DuplicateKeyError(f"Template already exists: {key}", details={"key": key})
        if validate:
            ensure_valid(validate_template(record), "Template validation failed")
        self._records[key] = record.with_changes(key=key)
        self._histories[key] = VersionHistory(key).append(
            record.version or "1.0.0", message="Initial version", checksum=_checksum(record.content)
        )
        return self._records[key]

    def register(self, record: TemplateRecord) -> TemplateRecord:
        """Add or replace a template and append a version entry."""
        key = record.key.strip().casefold()
        existing = self._records.get(key)
        if existing is None:
            return self._insert(record)
        if existing.version == record.version and existing.content == record.content:
            return existing
        version = record.version or bump_version(existing.version, "patch")
        updated = record.with_changes(key=key, version=version)
        ensure_valid(validate_template(updated), "Template validation failed")
        history = self._histories[key].append(
            version, message="Updated template", checksum=_checksum(updated.content)
        )
        self._records[key] = updated
        self._histories[key] = history
        return updated

    def remove(self, key: str) -> TemplateRecord:
        """Remove a template from the catalog."""
        record = self.get(key)
        del self._records[record.key]
        self._histories.pop(record.key, None)
        return record

    def list_records(
        self, *, category: str = "", tags: tuple[str, ...] = ()
    ) -> list[TemplateRecord]:
        """List templates with optional category and tag filters."""
        wanted = {tag.casefold() for tag in tags}
        results: list[TemplateRecord] = []
        for record in self.records:
            if category and record.category.casefold() != category.casefold():
                continue
            if wanted and not wanted.intersection({tag.casefold() for tag in record.tags}):
                continue
            results.append(record)
        return results

    def render(
        self,
        key: str,
        values: Values | None = None,
        *,
        strict: bool = False,
        target: str = "",
    ) -> TemplateRender:
        """Render one template with optional strict variable checking."""
        record = self.get(key)
        context = dict(values or {})
        if target and "target" not in context:
            context["target"] = target
        declared = {item.key for item in record.variables}
        missing = tuple(
            item.key
            for item in record.variables
            if item.required and not str(context.get(item.key, "")).strip()
        )
        rendered = render(record.content, context)
        warnings: list[Issue] = list(rendered.issues)
        if strict and missing:
            raise ValueError(f"Missing required template variables: {', '.join(missing)}")
        for name in rendered.unresolved:
            if name not in declared:
                warnings.append(
                    Issue(
                        code="undeclared-variable",
                        message=f"Template uses undeclared variable: {name}",
                        severity="warning",
                    )
                )
        return TemplateRender(
            key=record.key,
            version=record.version,
            content=rendered.text,
            used=rendered.used,
            unresolved=rendered.unresolved,
            warnings=tuple(warnings),
        )

    def render_source(self, source: str, values: Values | None = None) -> TemplateRender:
        """Render ad-hoc template source."""
        rendered = render(source, values)
        return TemplateRender(
            key="ad-hoc",
            version="0.0.0",
            content=rendered.text,
            used=rendered.used,
            unresolved=rendered.unresolved,
            warnings=rendered.issues,
        )

    def version(self, key: str) -> str:
        """Return the current version for a template."""
        history = self._histories.get(key.strip().casefold())
        return history.latest.version if history and history.latest else "0.0.0"

    def history(self, key: str) -> dict[str, Any]:
        """Return the version history for a template."""
        record = self.get(key)
        return self._histories[record.key].as_dict()

    def validate_catalog(self) -> tuple[Issue, ...]:
        """Validate the entire catalog."""
        issues: list[Issue] = []
        for record in self.records:
            issues.extend(validate_template(record))
        return tuple(issues)

    def suggest(self, query: str, *, limit: int = 5) -> list[TemplateSuggestion]:
        """Rank templates by relevance to a free-text query."""
        needle = query.strip().casefold()
        suggestions: list[TemplateSuggestion] = []
        for record in self.records:
            haystack = f"{record.key} {record.name} {record.description} {' '.join(record.tags)}"
            score = 0.0
            if needle:
                if record.key == needle:
                    score += 10
                if needle in haystack.casefold():
                    score += 4
                score += _overlap(needle, haystack.casefold()) * 0.5
            if score > 0:
                suggestions.append(TemplateSuggestion(record, score, "Matches template metadata"))
        suggestions.sort(key=lambda item: (-item.score, item.record.key))
        return suggestions[:limit]

    def as_dict(self, *, include_content: bool = False) -> list[dict[str, Any]]:
        """Serialize the catalog."""
        return [record.as_dict(include_content=include_content) for record in self.records]

    def to_records(self) -> tuple[TemplateRecord, ...]:
        """Return all templates for persistence."""
        return self.records


def _overlap(needle: str, haystack: str) -> int:
    tokens = [token for token in needle.split() if len(token) > 2]
    return sum(1 for token in tokens if token in haystack)


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "EXTRA_TEMPLATES",
    "TemplateEngine",
    "TemplateSuggestion",
    "builtin_templates",
]
