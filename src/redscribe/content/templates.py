"""Built-in note templates for common security workflows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from redscribe.content.placeholders import (
    expression_names,
    interpolate,
    render_expressions,
    target_values,
    validate_expression,
)
from redscribe.domain.models import Template, TemplateField, ValidationIssue
from redscribe.domain.utils import slugify

_CTF = r"""# {{title}}

- **Category:**
- **Difficulty:**
- **Points:**
- **Target:** {{target}}
- **Status:** active

## Description

> Paste the challenge statement here.

## Recon

```bash
file ./challenge
strings -n 6 ./challenge | head -50
```

## Hypothesis

-

## Exploit

```bash
```

## Flag

```text
flag{...}
```

## Takeaways

-
"""

_HOST = r"""# {{title}}

> Target: `{{target}}` · Date: {{date}} · Authorized scope only

## Snapshot

- **Host / IP:**
- **OS:**
- **Domain:**
- **Credentials:**
- **Access level:**

## Port scan

```bash
nmap -sC -sV -p- --min-rate 2000 -oA nmap/{{slug}} {{target}}
```

## Service notes

| Port | Service | Version | Notes |
|------|---------|---------|-------|
|      |         |         |       |

## Findings

- [ ]

## Foothold

```text
```

## Privilege escalation

```text
```

## Loot

- [ ] user flag
- [ ] root flag
- [ ] credentials
- [ ] Interesting files

## Cleanup

- [ ] Remove uploaded tooling
- [ ] Document changes
- [ ] Notify the client
"""

_WEB = r"""# {{title}}

> Target: `{{target}}` · Date: {{date}} · Authorized scope only

## Scope

- Base URL: {{url}}
- Authentication:
- Test accounts:
- Out of scope:

## Tech stack

```bash
whatweb {{target}}
curl -sSIL {{url}}
```

## Endpoint inventory

| Method | Path | Auth | Notes |
|--------|------|------|-------|
|        |      |      |       |

## Test log

- [ ] Authentication and session handling
- [ ] Authorization / IDOR
- [ ] Injection (SQLi, SSTI, command)
- [ ] SSRF
- [ ] File upload / path traversal
- [ ] XSS
- [ ] Business logic
- [ ] Security headers and TLS

## Findings

### Finding title

- **Severity:**
- **Evidence:**
- **Remediation:**

## Requests

```http
GET / HTTP/1.1
Host: {{domain}}
User-Agent: RedScribe
```
"""

_FINDING = r"""# {{title}}

| Field | Value |
|-------|-------|
| Severity | High |
| CVSS | 0.0 |
| Target | {{target}} |
| Status | Open |

## Summary

## Impact

## Evidence

```text
```

## Reproduction

1.

## Remediation

## References

-
"""

_ENGAGEMENT = r"""# {{title}}

- **Client:**
- **Window:** {{date}} →
- **Scope:**
- **Rules of engagement:**
- **Emergency contact:**

## Objectives

- [ ]
- [ ]
- [ ]

## Daily log

### {{date}}

-

## Credentials

| User | Secret | Source | Notes |
|------|--------|--------|-------|
|      |        |        |       |

## Findings

| Severity | Title | Status |
|----------|-------|--------|
|          |       |        |

## Deliverables

- [ ] Draft report
- [ ] Client review
- [ ] Final report
- [ ] Retest
"""

_CHEATSHEET = r"""# {{title}}

> Quick reference. Replace `{{target}}` with the current target.

## Commands

```bash

```

## Notes

-

## References

-
"""

_BLANK = ""

TEMPLATES: tuple[Template, ...] = (
    Template(
        key="blank",
        name="Blank note",
        description="An empty Markdown note.",
        content=_BLANK,
        tags="",
        status="todo",
        default_title="Untitled",
        glyph="◆",
    ),
    Template(
        key="ctf",
        name="CTF challenge",
        description="Challenge statement, recon, exploit, and flag.",
        content=_CTF,
        tags="ctf",
        status="active",
        default_title="New CTF challenge",
        glyph="⚑",
    ),
    Template(
        key="host",
        name="Host recon",
        description="Ports, services, findings, foothold, and loot.",
        content=_HOST,
        tags="host,recon",
        status="active",
        default_title="New host",
        glyph="▣",
    ),
    Template(
        key="web",
        name="Web assessment",
        description="Scope, endpoints, test log, and findings.",
        content=_WEB,
        tags="web",
        status="active",
        default_title="New web assessment",
        glyph="◈",
    ),
    Template(
        key="finding",
        name="Finding",
        description="Severity, impact, evidence, and remediation.",
        content=_FINDING,
        tags="finding",
        status="todo",
        default_title="New finding",
        glyph="△",
    ),
    Template(
        key="engagement",
        name="Engagement log",
        description="Client, scope, daily log, credentials, and deliverables.",
        content=_ENGAGEMENT,
        tags="engagement",
        status="active",
        default_title="New engagement",
        glyph="▤",
    ),
    Template(
        key="cheatsheet",
        name="Cheatsheet",
        description="A compact command reference note.",
        content=_CHEATSHEET,
        tags="cheatsheet",
        status="todo",
        default_title="New cheatsheet",
        glyph="≡",
    ),
)

TEMPLATE_MAP: dict[str, Template] = {template.key: template for template in TEMPLATES}


def get_template(key: str) -> Template:
    """Return a template by key, falling back to the blank note."""
    return TEMPLATE_MAP.get(key, TEMPLATE_MAP["blank"])


def render_template(template: Template, title: str, target: str = "") -> str:
    """Fill the placeholders in a template."""
    cleaned_target = target.strip()
    values = {
        "title": title.strip() or "Untitled",
        "date": datetime.now(timezone.utc).date().isoformat(),
    }
    if cleaned_target:
        values.update(target_values(cleaned_target))
        values.setdefault("domain", "<TARGET>")
    else:
        values.update(target="<TARGET>", domain="<TARGET>", url="https://<TARGET>")
    values["slug"] = slugify(cleaned_target or title)
    return interpolate(template.content, values)


TEMPLATE_VERSIONS: dict[str, str] = {
    "blank": "1.0.0",
    "ctf": "2.0.0",
    "host": "2.0.0",
    "web": "2.0.0",
    "finding": "1.1.0",
    "engagement": "1.1.0",
    "cheatsheet": "1.0.0",
}

TEMPLATE_CHANGELOG: dict[str, tuple[str, ...]] = {
    "ctf": ("2.0.0: structured hypothesis and takeaways sections",),
    "host": ("2.0.0: loot and cleanup checklists",),
    "web": ("2.0.0: endpoint inventory and request log",),
    "finding": ("1.1.0: added reproduction steps",),
    "engagement": ("1.1.0: added deliverables checklist",),
}

REQUIRED_FIELDS: dict[str, tuple[TemplateField, ...]] = {
    "blank": (),
    "ctf": (TemplateField("title", description="Challenge title"),),
    "host": (
        TemplateField("title", description="Host label"),
        TemplateField("target", description="Host or IP address"),
    ),
    "web": (
        TemplateField("title", description="Assessment title"),
        TemplateField("target", description="Base URL or host"),
    ),
    "finding": (TemplateField("title", description="Finding title"),),
    "engagement": (TemplateField("title", description="Engagement name"),),
    "cheatsheet": (TemplateField("title", description="Cheatsheet title"),),
}


class TemplateRenderError(ValueError):
    """Raised when strict template rendering cannot satisfy required fields."""


@dataclass(frozen=True, slots=True)
class StrictRenderResult:
    """A strict preview render with version, missing fields, and diagnostics."""

    content: str
    template_key: str
    version: str
    missing: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not any(issue.severity == "error" for issue in self.issues)


def template_version(key: str) -> str:
    """Return the registered version for a template key."""
    return TEMPLATE_VERSIONS.get(key, "0.0.0")


def template_changelog(key: str) -> tuple[str, ...]:
    """Return the changelog entries for a template key."""
    return TEMPLATE_CHANGELOG.get(key, ())


def required_fields(template: Template | str) -> tuple[TemplateField, ...]:
    """Return the fields a caller must supply for a strict render."""
    key = template if isinstance(template, str) else template.key
    return REQUIRED_FIELDS.get(key, ())


def template_placeholders(template: Template) -> tuple[str, ...]:
    """Return every expression name referenced by a template."""
    return tuple(expression_names(template.content))


def validate_template(template: Template) -> tuple[ValidationIssue, ...]:
    """Validate template metadata, declarations, and expression syntax."""
    issues: list[ValidationIssue] = []
    if not template.key.strip():
        issues.append(ValidationIssue("missing-key", "Template has no key."))
    if not template.name.strip():
        issues.append(ValidationIssue("missing-name", "Template has no display name."))
    if template_version(template.key) == "0.0.0":
        issues.append(
            ValidationIssue(
                code="unversioned-template",
                message=f"Template {template.key} has no registered version.",
                severity="warning",
            )
        )
    names = set(template_placeholders(template))
    for field in required_fields(template):
        if field.required and field.name not in names:
            issues.append(
                ValidationIssue(
                    code="missing-required-placeholder",
                    message=f"Required field has no matching placeholder: {field.name}",
                )
            )
    for name in sorted(names):
        issues.extend(validate_expression(name))
    return tuple(issues)


def validate_template_registry(
    templates: Iterable[Template] = TEMPLATES,
) -> tuple[ValidationIssue, ...]:
    """Validate a whole template registry, including key uniqueness."""
    items = tuple(templates)
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for template in items:
        if template.key in seen:
            issues.append(
                ValidationIssue("duplicate-key", f"Duplicate template key: {template.key}")
            )
        seen.add(template.key)
        issues.extend(validate_template(template))
    return tuple(issues)


def _strict_context(
    template: Template, values: Mapping[str, object], target: str
) -> dict[str, object]:
    cleaned_target = target.strip()
    context: dict[str, object] = {
        "title": str(values.get("title", "")).strip() or template.default_title,
        "date": datetime.now(timezone.utc).date().isoformat(),
    }
    if cleaned_target:
        context.update(target_values(cleaned_target))
        context.setdefault("domain", "<TARGET>")
    else:
        context.update(target="<TARGET>", domain="<TARGET>", url="https://<TARGET>")
    context["slug"] = slugify(cleaned_target or str(context["title"]))
    context.update(values)
    return context


def render_template_strict(
    template: Template,
    values: Mapping[str, object],
    *,
    target: str = "",
) -> StrictRenderResult:
    """Render a preview without silently dropping missing required fields."""
    context = _strict_context(template, values, target)
    rendered = render_expressions(template.content, context)
    issues = list(validate_template(template))
    missing = tuple(
        field.name
        for field in required_fields(template)
        if field.required and str(context.get(field.name, "")).strip() in ("", "<TARGET>")
    )
    for name in missing:
        issues.append(ValidationIssue("missing-field", f"Required field is blank: {name}"))
    for name in rendered.unresolved:
        issues.append(
            ValidationIssue(
                code="unresolved-placeholder",
                message=f"Unresolved placeholder: {name}",
                severity="warning",
            )
        )
    return StrictRenderResult(
        content=rendered.text,
        template_key=template.key,
        version=template_version(template.key),
        missing=missing,
        issues=tuple(issues),
    )


def render_template_checked(
    template: Template,
    values: Mapping[str, object],
    *,
    target: str = "",
) -> str:
    """Render a template, raising when required fields or metadata are invalid."""
    result = render_template_strict(template, values, target=target)
    if not result.ok:
        details = ", ".join(issue.message for issue in result.issues if issue.severity == "error")
        raise TemplateRenderError(details or "Template rendering failed validation")
    return result.content


def template_manifest(templates: Iterable[Template] = TEMPLATES) -> tuple[dict[str, object], ...]:
    """Return versioned template metadata suitable for an API payload."""
    return tuple(
        {
            "key": template.key,
            "name": template.name,
            "version": template_version(template.key),
            "required": [field.name for field in required_fields(template) if field.required],
            "changelog": list(template_changelog(template.key)),
        }
        for template in templates
    )
