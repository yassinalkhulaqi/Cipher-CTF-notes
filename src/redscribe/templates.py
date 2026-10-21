"""Built-in note templates for common security workflows."""

from __future__ import annotations

from datetime import datetime, timezone

from redscribe.models import Template
from redscribe.utils import slugify

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
    today = datetime.now(timezone.utc).date().isoformat()
    replacements = {
        "{{title}}": title,
        "{{date}}": today,
        "{{target}}": target.strip() or "<TARGET>",
        "{{domain}}": _domain_for(target),
        "{{url}}": _url_for(target),
        "{{slug}}": slugify(target or title),
    }
    content = template.content
    for key, value in replacements.items():
        content = content.replace(key, value)
    return content


def _domain_for(target: str) -> str:
    value = target.strip()
    if not value:
        return "<TARGET>"
    for prefix in ("https://", "http://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
    return value.split("/", 1)[0].split(":", 1)[0]


def _url_for(target: str) -> str:
    value = target.strip()
    if not value:
        return "https://<TARGET>"
    if value.lower().startswith(("http://", "https://")):
        return value.rstrip("/")
    return f"https://{value.rstrip('/')}"
