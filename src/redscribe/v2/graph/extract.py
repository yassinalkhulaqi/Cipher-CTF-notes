"""Reference and tag extraction from vault note bodies.

Extraction is deliberately conservative: fenced code, inline code, and escaped
brackets do not produce links. Every occurrence keeps its source offsets so
callers can build snippets and highlight ranges without rescanning the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from redscribe.domain.utils import collapse_whitespace, slugify

WIKILINK_RE = re.compile(r"(?<!\\)\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]")
INLINE_TAG_RE = re.compile(r"(?<![\w/])#([A-Za-z][\w/-]{0,48})")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+[^\n]*", re.MULTILINE)
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
TAG_SPLIT_RE = re.compile(r"[,;]+|\s+")

_MAX_SNIPPET = 180


@dataclass(frozen=True, slots=True)
class LinkOccurrence:
    """One wikilink found at a precise location in a note body."""

    target: str
    alias: str = ""
    heading: str = ""
    start: int = 0
    end: int = 0
    line: int = 1

    @property
    def key(self) -> str:
        """Normalized target key used for resolution."""
        return normalize_reference(self.target)

    @property
    def display(self) -> str:
        """Human-readable label for the reference."""
        return self.alias or self.target

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable view."""
        return {
            "target": self.target,
            "alias": self.alias,
            "heading": self.heading,
            "start": self.start,
            "end": self.end,
            "line": self.line,
            "key": self.key,
        }


@dataclass(frozen=True, slots=True)
class TagOccurrence:
    """One tag token with its origin and source position."""

    value: str
    source: str
    start: int = 0
    end: int = 0

    @property
    def key(self) -> str:
        """Case-folded tag identity."""
        return self.value.casefold()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable view."""
        return {"value": self.value, "source": self.source, "start": self.start, "end": self.end}


def normalize_reference(value: str) -> str:
    """Normalize a wikilink target for deterministic title resolution."""
    cleaned = value.strip().replace("\\", "/")
    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0]
    if not cleaned.strip():
        return ""
    return slugify(cleaned.strip())


def mask_protected_spans(content: str) -> str:
    """Blank out code spans while preserving all source offsets."""
    masked = list(content)
    for pattern in (FENCE_RE, INLINE_CODE_RE):
        for match in pattern.finditer("".join(masked)):
            for index in range(match.start(), match.end()):
                if masked[index] != "\n":
                    masked[index] = " "
    return "".join(masked)


def parse_wikilink(raw: str) -> tuple[str, str, str]:
    """Split a wikilink body into target, alias, and heading."""
    target, separator, alias = raw.partition("|")
    heading = ""
    if "#" in target:
        target, _, heading = target.partition("#")
        heading = heading.strip()
    return target.strip(), alias.strip() if separator else "", heading


def extract_wikilinks(content: str) -> tuple[LinkOccurrence, ...]:
    """Return all wikilinks in ``content``, in reading order."""
    if not content:
        return ()
    source = mask_protected_spans(content)
    occurrences: list[LinkOccurrence] = []
    seen: set[tuple[str, str, str, int]] = set()
    for match in WIKILINK_RE.finditer(source):
        raw = match.group(1)
        if match.group(2) is not None:
            raw = f"{raw}|{match.group(2)}"
        target, alias, heading = parse_wikilink(raw)
        if not target:
            continue
        line = content.count("\n", 0, match.start()) + 1
        identity = (target.casefold(), alias.casefold(), heading, line)
        if identity in seen:
            continue
        seen.add(identity)
        occurrences.append(
            LinkOccurrence(
                target=target,
                alias=alias,
                heading=heading,
                start=match.start(),
                end=match.end(),
                line=line,
            )
        )
    return tuple(occurrences)


def extract_inline_tags(content: str) -> tuple[TagOccurrence, ...]:
    """Return hashtag tokens, ignoring headings and code spans."""
    if not content:
        return ()
    source = mask_protected_spans(content)
    for match in HEADING_RE.finditer(source):
        for index in range(match.start(), match.end()):
            source = source[:index] + " " + source[index + 1 :]
    found: list[TagOccurrence] = []
    seen: set[str] = set()
    for match in INLINE_TAG_RE.finditer(source):
        value = match.group(1)
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(
            TagOccurrence(value=value, source="inline", start=match.start(1), end=match.end(1))
        )
    return tuple(found)


def extract_frontmatter(content: str) -> dict[str, str]:
    """Return a small map of scalar frontmatter fields."""
    match = FRONTMATTER_RE.match(content)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip().casefold()] = value.strip()
    return fields


def extract_frontmatter_tags(content: str) -> tuple[TagOccurrence, ...]:
    """Return tags declared in YAML-style frontmatter."""
    match = FRONTMATTER_RE.match(content)
    if match is None:
        return ()
    fields = extract_frontmatter(content)
    raw = fields.get("tags") or fields.get("tag") or fields.get("keywords") or ""
    raw = raw.strip().strip("'\"").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    offset = match.start(1)
    found: list[TagOccurrence] = []
    seen: set[str] = set()
    for token in TAG_SPLIT_RE.split(raw):
        value = token.strip().lstrip("#")
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        found.append(
            TagOccurrence(
                value=value,
                source="frontmatter",
                start=offset + raw.find(token),
                end=offset + raw.find(token) + len(token),
            )
        )
    return tuple(found)


def extract_tags(content: str, *, stored: str = "") -> tuple[TagOccurrence, ...]:
    """Return stored, frontmatter, and inline tags in stable priority order."""
    occurrences: list[TagOccurrence] = []
    positions: dict[str, int] = {}
    priority = {"stored": 0, "inline": 1, "frontmatter": 2}

    def merge(item: TagOccurrence) -> None:
        index = positions.get(item.key)
        if index is None:
            positions[item.key] = len(occurrences)
            occurrences.append(item)
            return
        if priority[item.source] > priority[occurrences[index].source]:
            occurrences[index] = item

    for token in stored.split(","):
        value = token.strip().lstrip("#")
        if value:
            merge(TagOccurrence(value=value, source="stored"))
    for item in (*extract_frontmatter_tags(content), *extract_inline_tags(content)):
        merge(item)
    return tuple(occurrences)


def link_snippet(content: str, start: int, end: int, *, width: int = 100) -> str:
    """Return a compact excerpt around one reference."""
    if not content or width < 8:
        return ""
    left = max(0, start - width // 2)
    right = min(len(content), end + width)
    excerpt = collapse_whitespace(content[left:right]).replace("[[", "").replace("]]", "")
    if len(excerpt) > _MAX_SNIPPET:
        excerpt = excerpt[: _MAX_SNIPPET - 1] + "…"
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(content) else ""
    return f"{prefix}{excerpt}{suffix}"


def reference_index(nodes: list[tuple[int, str]]) -> dict[str, int]:
    """Index normalized labels to ids, keeping the first label for each key."""
    index: dict[str, int] = {}
    for node_id, label in nodes:
        index.setdefault(normalize_reference(label), node_id)
    return index
