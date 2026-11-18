"""Immutable block and document value objects.

The model is deliberately independent of storage and transport. Every mutation
returns a new value so optimistic revision checks can compare documents by
identity as well as by revision number.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, TypeVar

from redscribe.v2.blocks.types import (
    BLOCK_TYPES,
    CALLOUT_TONES,
    LIST_STYLES,
    BlockType,
    CalloutTone,
    ListStyle,
    MentionKind,
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

BlockChoice = TypeVar("BlockChoice", BlockType, ListStyle, CalloutTone, MentionKind)


def utc_now() -> str:
    """Return a compact UTC timestamp with an explicit designator."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str = "blk") -> str:
    """Generate a stable, URL-safe identifier with a readable prefix."""
    clean = re.sub(r"[^a-z0-9]+", "", prefix.casefold()) or "id"
    return f"{clean}-{uuid.uuid4().hex[:16]}"


def valid_id(value: str) -> bool:
    """Return whether ``value`` is acceptable as a block/document id."""
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def _as_enum(
    value: object,
    enum_type: type[BlockChoice],
    default: BlockChoice,
) -> BlockChoice:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value.casefold())
        except ValueError:
            return default
    return default


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _as_bool(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _as_bool_tuple(value: object, size: int) -> tuple[bool, ...]:
    if isinstance(value, Sequence):
        values = tuple(item for item in value if isinstance(item, bool))
        return (values + (False,) * size)[:size]
    return (False,) * size


def _as_rows(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, Sequence):
        return ()
    rows: list[tuple[str, ...]] = []
    for row in value:
        if isinstance(row, Sequence):
            rows.append(tuple(cell for cell in row if isinstance(cell, str)))
    return tuple(rows)


def _as_string_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _as_str(item) for key, item in value.items()}


@dataclass(frozen=True, slots=True)
class Mention:
    """One resolved ``@[label](kind:target)`` reference inside a block."""

    kind: MentionKind
    target: str
    label: str
    start: int
    end: int
    block_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "block_id": self.block_id,
        }

    @property
    def token(self) -> str:
        return f"@[{self.label}]({self.kind.value}:{self.target})"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Mention:
        return cls(
            kind=_as_enum(value.get("kind"), MentionKind, MentionKind.NOTE),
            target=_as_str(value.get("target")),
            label=_as_str(value.get("label")),
            start=max(0, _as_int(value.get("start"))),
            end=max(0, _as_int(value.get("end"))),
            block_id=_as_str(value.get("block_id")),
        )


@dataclass(frozen=True, slots=True)
class Block:
    """A single structured content unit."""

    id: str
    type: BlockType
    text: str = ""
    level: int = 1
    language: str = ""
    items: tuple[str, ...] = ()
    checked: tuple[bool, ...] = ()
    style: ListStyle = ListStyle.BULLET
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    tone: CalloutTone = CalloutTone.INFO
    alt: str = ""
    source: str = ""
    mentions: tuple[Mention, ...] = ()
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def plain_text(self) -> str:
        """Return searchable text regardless of block geometry."""
        if self.type is BlockType.LIST:
            return "\n".join(self.items)
        if self.type is BlockType.TABLE:
            lines = [" | ".join(self.headers)]
            lines.extend(" | ".join(row) for row in self.rows)
            return "\n".join(lines)
        if self.type is BlockType.DIVIDER:
            return ""
        if self.type is BlockType.IMAGE:
            return " ".join(part for part in (self.alt, self.source) if part)
        return self.text

    def with_changes(self, **changes: Any) -> Block:
        """Return a shallow copy with selected fields replaced."""
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "text": self.text,
            "level": self.level,
            "language": self.language,
            "items": list(self.items),
            "checked": list(self.checked),
            "style": self.style.value,
            "headers": list(self.headers),
            "rows": [list(row) for row in self.rows],
            "tone": self.tone.value,
            "alt": self.alt,
            "source": self.source,
            "mentions": [mention.as_dict() for mention in self.mentions],
            "attrs": dict(self.attrs),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | Block) -> Block:
        """Build a block from a mapping, tolerating partial payloads."""
        if isinstance(value, Block):
            return value
        items = _as_text_tuple(value.get("items"))
        return cls(
            id=_as_str(value.get("id")) or new_id(),
            type=_as_enum(value.get("type"), BlockType, BlockType.PARAGRAPH),
            text=_as_str(value.get("text")),
            level=_as_int(value.get("level"), 1),
            language=_as_str(value.get("language")),
            items=items,
            checked=_as_bool_tuple(value.get("checked"), len(items)),
            style=_as_enum(value.get("style"), ListStyle, ListStyle.BULLET),
            headers=_as_text_tuple(value.get("headers")),
            rows=_as_rows(value.get("rows")),
            tone=_as_enum(value.get("tone"), CalloutTone, CalloutTone.INFO),
            alt=_as_str(value.get("alt")),
            source=_as_str(value.get("source")),
            mentions=tuple(
                Mention.from_dict(item)
                for item in value.get("mentions", ())
                if isinstance(item, Mapping)
            ),
            attrs=_as_string_map(value.get("attrs")),
        )


@dataclass(frozen=True, slots=True)
class BlockDocument:
    """An ordered collection of blocks with an optimistic revision counter."""

    id: str
    title: str = ""
    blocks: tuple[Block, ...] = ()
    revision: int = 0
    updated_at: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(block.id for block in self.blocks)

    @property
    def word_count(self) -> int:
        return sum(len(block.plain_text.split()) for block in self.blocks)

    def index_of(self, block_id: str) -> int:
        """Return the position of ``block_id`` or ``-1``."""
        for index, block in enumerate(self.blocks):
            if block.id == block_id:
                return index
        return -1

    def find(self, block_id: str) -> Block | None:
        """Return the block with ``block_id`` when present."""
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def with_blocks(self, blocks: Iterable[Block]) -> BlockDocument:
        """Return a copy with a new block sequence and an unchanged revision."""
        return replace(self, blocks=tuple(blocks))

    def advanced(self, revision: int | None = None) -> BlockDocument:
        """Return a copy with an incremented revision and fresh timestamp."""
        return replace(
            self,
            revision=self.revision + 1 if revision is None else revision,
            updated_at=utc_now(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "blocks": [block.as_dict() for block in self.blocks],
            "revision": self.revision,
            "updated_at": self.updated_at,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | BlockDocument) -> BlockDocument:
        """Build a document from a mapping, tolerating partial payloads."""
        if isinstance(value, BlockDocument):
            return value
        blocks = value.get("blocks", ())
        return cls(
            id=_as_str(value.get("id")) or new_id("doc"),
            title=_as_str(value.get("title")),
            blocks=tuple(Block.from_dict(item) for item in blocks if isinstance(item, Mapping)),
            revision=max(0, _as_int(value.get("revision"))),
            updated_at=_as_str(value.get("updated_at")) or utc_now(),
            tags=_as_text_tuple(value.get("tags")),
            metadata=_as_string_map(value.get("metadata")),
        )


def make_block(
    block_type: BlockType | str = BlockType.PARAGRAPH,
    text: str = "",
    *,
    block_id: str | None = None,
    level: int = 1,
    language: str = "",
    items: Sequence[str] = (),
    checked: Sequence[bool] = (),
    style: ListStyle | str = ListStyle.BULLET,
    headers: Sequence[str] = (),
    rows: Sequence[Sequence[str]] = (),
    tone: CalloutTone | str = CalloutTone.INFO,
    alt: str = "",
    source: str = "",
    mentions: Sequence[Mention] = (),
    attrs: Mapping[str, str] | None = None,
) -> Block:
    """Construct a block with sensible defaults for every supported type."""
    resolved_type = _as_enum(block_type, BlockType, BlockType.PARAGRAPH)
    return Block(
        id=block_id or new_id(),
        type=resolved_type,
        text=text,
        level=level if resolved_type is BlockType.HEADING else 1,
        language=language if resolved_type is BlockType.CODE else "",
        items=tuple(items) if resolved_type is BlockType.LIST else (),
        checked=tuple(checked) if resolved_type is BlockType.LIST else (),
        style=_as_enum(style, ListStyle, ListStyle.BULLET),
        headers=tuple(headers) if resolved_type is BlockType.TABLE else (),
        rows=tuple(tuple(row) for row in rows) if resolved_type is BlockType.TABLE else (),
        tone=_as_enum(tone, CalloutTone, CalloutTone.INFO),
        alt=alt if resolved_type is BlockType.IMAGE else "",
        source=source if resolved_type is BlockType.IMAGE else "",
        mentions=tuple(mentions),
        attrs=dict(attrs or {}),
    )


def make_document(
    document_id: str | None = None,
    title: str = "",
    blocks: Sequence[Block] = (),
    *,
    tags: Sequence[str] = (),
    metadata: Mapping[str, str] | None = None,
) -> BlockDocument:
    """Construct a document with one editable block when none are supplied."""
    initial = tuple(blocks) if blocks else (make_block(),)
    return BlockDocument(
        id=document_id or new_id("doc"),
        title=title,
        blocks=initial,
        revision=0,
        updated_at=utc_now(),
        tags=tuple(tags),
        metadata=dict(metadata or {}),
    )


def clone_block(block: Block) -> Block:
    """Return a detached copy with a fresh id and no resolved mentions."""
    return replace(block, id=new_id(), mentions=(), attrs=dict(block.attrs))


def is_known_type(value: object) -> bool:
    """Return whether ``value`` names a registered block type."""
    return isinstance(value, str) and value in {item.value for item in BLOCK_TYPES}


def is_known_tone(value: object) -> bool:
    """Return whether ``value`` names a registered callout tone."""
    return isinstance(value, str) and value in {item.value for item in CALLOUT_TONES}


def is_known_style(value: object) -> bool:
    """Return whether ``value`` names a registered list style."""
    return isinstance(value, str) and value in {item.value for item in LIST_STYLES}
