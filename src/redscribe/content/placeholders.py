"""Shared placeholder expansion and target normalization.

Templates and command snippets use the same ``{{name}}`` syntax. Keeping the
resolver in one module guarantees consistent target, domain, URL, and slug
derivation across both content features.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from redscribe.domain.utils import slugify

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def placeholder_names(text: str) -> list[str]:
    """Return placeholder names in first-use order, without duplicates."""
    names: list[str] = []
    seen: set[str] = set()
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def interpolate(text: str, values: Mapping[str, str]) -> str:
    """Replace known placeholders, leaving unknown or blank values intact."""

    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1), "").strip()
        return value if value else match.group(0)

    return PLACEHOLDER_RE.sub(replace, text)


def target_values(target: str) -> dict[str, str]:
    """Derive the placeholder context for a host or URL target."""
    cleaned = target.strip()
    if not cleaned:
        return {}
    host = _hostname(cleaned)
    values = {
        "target": cleaned,
        "slug": slugify(cleaned),
    }
    if host:
        values["domain"] = host
    values["url"] = _target_url(cleaned)
    return values


def _hostname(target: str) -> str:
    candidate = target if _SCHEME_RE.match(target) else f"//{target}"
    try:
        return urlsplit(candidate).hostname or ""
    except ValueError:
        return ""


def _target_url(target: str) -> str:
    if _SCHEME_RE.match(target):
        return target.rstrip("/")
    return f"https://{target.lstrip('/')}".rstrip("/")
