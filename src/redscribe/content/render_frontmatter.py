"""Shared front-matter parsing and canonicalization for imports and exports."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

_FRONTMATTER_END = frozenset({"---", "..."})
_FRONT_MATTER_KEY = re.compile(r"^(?P<key>[A-Za-z0-9_-]+)\s*:\s*(?P<value>.*)$")
_FRONT_MATTER_LIST_ITEM = re.compile(r"^\s*-\s+(?P<value>.+?)\s*$")
_HEADING = re.compile(r"^\s{0,3}#\s+(?P<title>.+?)\s*#*\s*$")
_KEY_ALIASES = {
    "tag": "tags",
    "keywords": "tags",
    "created_at": "created",
    "date": "created",
    "updated_at": "updated",
    "modified": "updated",
}
_CANONICAL_ORDER = ("title", "status", "created", "updated", "tags", "target", "difficulty", "flag")
_ALWAYS_INCLUDE = frozenset({"title", "status", "created", "updated"})


@dataclass(frozen=True, slots=True)
class FrontMatter:
    metadata: dict[str, str]
    body: str


def normalize_tag_string(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    tags: list[str] = []
    seen: set[str] = set()
    for part in cleaned.split(","):
        tag = part.strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return ",".join(tags)


def clean_front_matter_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        if stripped[0] == '"':
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, str):
                    return parsed
            except json.JSONDecodeError:
                pass
        return stripped[1:-1]
    return stripped


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a simple YAML front matter block and return metadata plus body."""
    document = parse_front_matter_document(text)
    return document.metadata, document.body


def parse_front_matter_document(text: str) -> FrontMatter:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not normalized.startswith("---\n"):
        return FrontMatter({}, normalized)
    lines = normalized.split("\n")
    end = -1
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONTMATTER_END:
            end = index
            break
    if end < 0:
        return FrontMatter({}, normalized)

    metadata: dict[str, str] = {}
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = _FRONT_MATTER_KEY.match(line)
        if match is None:
            index += 1
            continue
        key = _canonical_key(match.group("key"))
        value = clean_front_matter_value(match.group("value"))
        index += 1
        if key == "tags":
            if not value:
                items: list[str] = []
                while index < end:
                    item = _FRONT_MATTER_LIST_ITEM.match(lines[index])
                    if item is None:
                        break
                    items.append(clean_front_matter_value(item.group("value")))
                    index += 1
                value = ",".join(items)
            value = normalize_tag_string(value)
        metadata[key] = value

    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return FrontMatter(metadata, body)


def canonical_front_matter(
    values: Mapping[str, object],
    *,
    order: tuple[str, ...] = _CANONICAL_ORDER,
    include_empty: frozenset[str] = _ALWAYS_INCLUDE,
) -> str:
    """Render metadata as stable, quoted front matter with known fields first."""
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        if raw_value is None:
            continue
        key = _canonical_key(str(raw_key))
        value = str(raw_value).strip()
        if key == "tags":
            value = normalize_tag_string(value)
        normalized[key] = value

    ordered_keys = [key for key in order if key in normalized]
    ordered_keys.extend(sorted(key for key in normalized if key not in order))
    lines = ["---"]
    for key in ordered_keys:
        value = normalized[key]
        if not value and key not in include_empty:
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _HEADING.match(line)
        if match:
            return match.group("title").strip() or fallback
        break
    return fallback


def _canonical_key(key: str) -> str:
    lowered = key.strip().lower()
    return _KEY_ALIASES.get(lowered, lowered)
