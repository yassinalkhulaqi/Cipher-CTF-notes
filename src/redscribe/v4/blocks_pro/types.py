"""Immutable value types for the professional block editor.

A document is an ordered tuple of typed blocks. Every value type validates its
own shape at construction time, serializes to plain dictionaries, and restores
from those dictionaries without losing information. The module is data-only: no
I/O, no code execution, and no dependency on the editor UI.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe.v4.contracts import SLUG_PATTERN, new_entity_id

BLOCK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
MAX_TEXT_LENGTH = 20_000
MAX_TITLE_LENGTH = 240
MAX_ITEMS = 500
MAX_BLOCKS = 2_000
MAX_ATTRS = 24
MAX_ATTR_KEY = 40
MAX_ATTR_VALUE = 500
MAX_NOTE_LENGTH = 240
MIN_HEADING_LEVEL = 1
MAX_HEADING_LEVEL = 6
LEGAL_HEADING_LEVELS = frozenset(range(MIN_HEADING_LEVEL, MAX_HEADING_LEVEL + 1))
LIST_STYLES: tuple[str, ...] = ("bullet", "ordered", "task")
KNOWN_LANGUAGES = frozenset(
    {
        "bash",
        "c",
        "cpp",
        "css",
        "diff",
        "go",
        "html",
        "javascript",
        "json",
        "markdown",
        "python",
        "rust",
        "sql",
        "text",
        "typescript",
        "yaml",
    }
)


class BlockKind(str, Enum):
    """The seven block kinds renderable by the v4 editor."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    CODE = "code"
    LIST = "list"
    QUOTE = "quote"
    TABLE = "table"
    DIVIDER = "divider"

    @classmethod
    def parse(cls, value: str) -> BlockKind:
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown block kind: {value}")

    @property
    def label(self) -> str:
        return self.value.title()

    @property
    def supports_text(self) -> bool:
        return self not in {BlockKind.DIVIDER, BlockKind.TABLE}

    @property
    def supports_items(self) -> bool:
        return self in {BlockKind.LIST, BlockKind.TABLE}

    @property
    def supports_language(self) -> bool:
        return self is BlockKind.CODE

    @property
    def supports_level(self) -> bool:
        return self is BlockKind.HEADING


class InlineMark(str, Enum):
    """Inline decorations the toolbar can apply to a text selection."""

    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"
    LINK = "link"

    @classmethod
    def parse(cls, value: str) -> InlineMark:
        normalized = value.strip().casefold()
        for mark in cls:
            if mark.value == normalized:
                return mark
        raise ValueError(f"Unknown inline mark: {value}")

    @property
    def marker(self) -> str:
        return {
            InlineMark.BOLD: "**",
            InlineMark.ITALIC: "*",
            InlineMark.CODE: "`",
            InlineMark.LINK: "]",
        }[self]

    @property
    def label(self) -> str:
        return self.value.title()

    def apply(self, text: str, target: str, href: str = "") -> str:
        """Wrap ``target`` with this mark's markdown syntax inside ``text``."""
        if not target or target not in text:
            raise ValueError(f"selection not present in text for {self.value}")
        if self is InlineMark.LINK:
            if not href.strip():
                raise ValueError("link mark requires an href")
            replacement = f"[{target}]({href.strip()})"
        elif self is InlineMark.CODE:
            replacement = f"`{target}`"
        elif self is InlineMark.BOLD:
            replacement = f"**{target}**"
        else:
            replacement = f"*{target}*"
        return text.replace(target, replacement, 1)


class BlockOp(str, Enum):
    """Editable operations accepted by the patch route."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"

    @classmethod
    def parse(cls, value: str) -> BlockOp:
        normalized = value.strip().casefold()
        for op in cls:
            if op.value == normalized:
                return op
        raise ValueError(f"Unknown block operation: {value}")

    @property
    def is_structural(self) -> bool:
        return self in {BlockOp.INSERT, BlockOp.DELETE, BlockOp.MOVE}


class ValidationSeverity(str, Enum):
    """Severity carried by a structural validation issue."""

    ERROR = "error"
    WARNING = "warning"


ALL_BLOCK_KINDS: tuple[BlockKind, ...] = tuple(BlockKind)
ALL_INLINE_MARKS: tuple[InlineMark, ...] = tuple(InlineMark)
ALL_BLOCK_OPS: tuple[BlockOp, ...] = tuple(BlockOp)
SLASH_ORDER: tuple[BlockKind, ...] = (
    BlockKind.PARAGRAPH,
    BlockKind.HEADING,
    BlockKind.LIST,
    BlockKind.CODE,
    BlockKind.QUOTE,
    BlockKind.TABLE,
    BlockKind.DIVIDER,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation finding with a stable machine-readable code."""

    path: str
    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValidationIssue:
        return cls(
            path=str(data.get("path", "")),
            code=str(data.get("code", "")),
            message=str(data.get("message", "")),
            severity=ValidationSeverity(str(data.get("severity", "error"))),
        )


def canonical_checksum(value: Mapping[str, Any]) -> str:
    """Return a short deterministic checksum of a serializable mapping."""
    raw = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_text(value: str) -> str:
    """Trim trailing spaces per line and collapse more than two blank lines."""
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            normalized.append(line)
        elif blank_run < 1:
            blank_run += 1
            normalized.append("")
    while normalized and not normalized[-1]:
        normalized.pop()
    return "\n".join(normalized)


def attr_pairs(
    attrs: Mapping[str, str] | Iterable[tuple[str, str]] | None,
) -> tuple[tuple[str, str], ...]:
    """Convert a mapping or pair sequence into stable sorted attribute pairs."""
    if attrs is None:
        return ()
    if isinstance(attrs, Mapping):
        items: Iterable[tuple[str, str]] = attrs.items()
    else:
        items = attrs
    result: dict[str, str] = {}
    for key, value in items:
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("block attributes must map strings to strings")
        result[key] = value
    if len(result) > MAX_ATTRS:
        raise ValueError(f"block has more than {MAX_ATTRS} attributes")
    for key, value in result.items():
        if len(key) > MAX_ATTR_KEY or not SLUG_PATTERN.match(key):
            raise ValueError(f"invalid attribute key: {key}")
        if len(value) > MAX_ATTR_VALUE:
            raise ValueError(f"attribute value too long: {key}")
    return tuple(sorted(result.items()))


@dataclass(frozen=True, slots=True)
class Block:
    """One immutable block in a document."""

    id: str
    kind: BlockKind
    text: str = ""
    level: int = 1
    language: str = ""
    items: tuple[str, ...] = ()
    attrs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not BLOCK_ID_PATTERN.match(self.id):
            raise ValueError(f"invalid block id: {self.id}")
        if not isinstance(self.kind, BlockKind):
            raise TypeError("block kind must be a BlockKind")
        if not isinstance(self.text, str):
            raise TypeError("block text must be a string")
        if len(self.text) > MAX_TEXT_LENGTH:
            raise ValueError(f"block text exceeds {MAX_TEXT_LENGTH} characters")
        if isinstance(self.level, bool) or not isinstance(self.level, int):
            raise TypeError("block level must be an integer")
        if self.level not in LEGAL_HEADING_LEVELS:
            raise ValueError(
                f"block level must be between {MIN_HEADING_LEVEL} and {MAX_HEADING_LEVEL}"
            )
        if not isinstance(self.language, str) or len(self.language) > 60:
            raise ValueError("block language must be a short string")
        if len(self.items) > MAX_ITEMS:
            raise ValueError(f"block has more than {MAX_ITEMS} items")
        for item in self.items:
            if not isinstance(item, str) or len(item) > MAX_TEXT_LENGTH:
                raise ValueError("block items must be bounded strings")
        object.__setattr__(self, "attrs", attr_pairs(self.attrs))

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not any(item.strip() for item in self.items)

    @property
    def word_count(self) -> int:
        return len(self.text.split()) + sum(len(item.split()) for item in self.items)

    def attrs_dict(self) -> dict[str, str]:
        return dict(self.attrs)

    def attr(self, key: str, default: str = "") -> str:
        return self.attrs_dict().get(key, default)

    def checksum(self) -> str:
        return canonical_checksum(self.to_dict())

    def with_text(self, text: str) -> Block:
        return Block(self.id, self.kind, text, self.level, self.language, self.items, self.attrs)

    def with_items(self, items: Sequence[str]) -> Block:
        return Block(
            self.id, self.kind, self.text, self.level, self.language, tuple(items), self.attrs
        )

    def with_level(self, level: int) -> Block:
        return Block(self.id, self.kind, self.text, level, self.language, self.items, self.attrs)

    def with_language(self, language: str) -> Block:
        return Block(self.id, self.kind, self.text, self.level, language, self.items, self.attrs)

    def with_attrs(self, attrs: Mapping[str, str] | Iterable[tuple[str, str]]) -> Block:
        return Block(
            self.id,
            self.kind,
            self.text,
            self.level,
            self.language,
            self.items,
            attr_pairs(attrs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "text": self.text,
            "level": self.level,
            "language": self.language,
            "items": list(self.items),
            "attrs": self.attrs_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Block:
        kind = BlockKind.parse(str(data.get("kind", "")))
        raw_items = data.get("items", ())
        if not isinstance(raw_items, (list, tuple)):
            raise ValueError("block items must be a list")
        raw_attrs = data.get("attrs", {})
        return cls(
            id=str(data.get("id", "")),
            kind=kind,
            text=str(data.get("text", "")),
            level=int(data.get("level", 1)),
            language=str(data.get("language", "")),
            items=tuple(str(item) for item in raw_items),
            attrs=attr_pairs(raw_attrs),
        )


@dataclass(frozen=True, slots=True)
class BlockDocument:
    """An ordered, immutable collection of blocks with a title and identity."""

    id: str
    title: str
    blocks: tuple[Block, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not BLOCK_ID_PATTERN.match(self.id):
            raise ValueError(f"invalid document id: {self.id}")
        if not isinstance(self.title, str) or len(self.title) > MAX_TITLE_LENGTH:
            raise ValueError(f"document title must be a string under {MAX_TITLE_LENGTH} characters")
        if len(self.blocks) > MAX_BLOCKS:
            raise ValueError(f"document has more than {MAX_BLOCKS} blocks")
        for block in self.blocks:
            if not isinstance(block, Block):
                raise TypeError("document blocks must be Block instances")

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(block.id for block in self.blocks)

    @property
    def word_count(self) -> int:
        return len(self.title.split()) + sum(block.word_count for block in self.blocks)

    def get(self, block_id: str) -> Block | None:
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def index_of(self, block_id: str) -> int:
        for index, block in enumerate(self.blocks):
            if block.id == block_id:
                return index
        return -1

    def with_blocks(self, blocks: Sequence[Block]) -> BlockDocument:
        return BlockDocument(self.id, self.title, tuple(blocks))

    def with_title(self, title: str) -> BlockDocument:
        return BlockDocument(self.id, title, self.blocks)

    def checksum(self) -> str:
        return canonical_checksum(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "blocks": [block.to_dict() for block in self.blocks],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BlockDocument:
        raw_blocks = data.get("blocks", ())
        if not isinstance(raw_blocks, (list, tuple)):
            raise ValueError("document blocks must be a list")
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            blocks=tuple(Block.from_dict(item) for item in raw_blocks),
        )


@dataclass(frozen=True, slots=True)
class EditOperation:
    """A single, replayable change to a document."""

    op: BlockOp
    block_id: str
    index: int = 0
    target_index: int | None = None
    block: Block | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.op, BlockOp):
            raise TypeError("operation must be a BlockOp")
        if not isinstance(self.block_id, str) or not BLOCK_ID_PATTERN.match(self.block_id):
            raise ValueError(f"invalid operation block id: {self.block_id}")
        if isinstance(self.index, bool) or self.index < 0:
            raise ValueError("operation index must be non-negative")
        if self.target_index is not None and self.target_index < 0:
            raise ValueError("operation target index must be non-negative")
        if self.op in {BlockOp.INSERT, BlockOp.UPDATE} and not isinstance(self.block, Block):
            raise ValueError(f"{self.op.value} operation requires a block")
        if self.op in {BlockOp.DELETE, BlockOp.MOVE} and self.block is not None:
            raise ValueError(f"{self.op.value} operation must not carry a block")
        if self.op is BlockOp.MOVE and self.target_index is None:
            raise ValueError("move operation requires a target index")
        if len(self.note) > MAX_NOTE_LENGTH:
            raise ValueError(f"operation note exceeds {MAX_NOTE_LENGTH} characters")

    @property
    def label(self) -> str:
        return f"{self.op.value}:{self.block_id}"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "op": self.op.value,
            "block_id": self.block_id,
            "index": self.index,
            "target_index": self.target_index,
            "note": self.note,
        }
        if self.block is not None:
            data["block"] = self.block.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EditOperation:
        raw_block = data.get("block")
        raw_target = data.get("target_index")
        return cls(
            op=BlockOp.parse(str(data.get("op", ""))),
            block_id=str(data.get("block_id", "")),
            index=int(data.get("index", 0)),
            target_index=None if raw_target is None else int(raw_target),
            block=Block.from_dict(raw_block) if isinstance(raw_block, Mapping) else None,
            note=str(data.get("note", "")),
        )


def new_block(
    kind: BlockKind | str,
    text: str = "",
    *,
    id_factory: Callable[[], str] = new_entity_id,
    level: int = 1,
    language: str = "",
    items: Sequence[str] = (),
    attrs: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
) -> Block:
    """Build a block with a generated identifier."""
    resolved = kind if isinstance(kind, BlockKind) else BlockKind.parse(kind)
    return Block(
        id=id_factory(),
        kind=resolved,
        text=text,
        level=level,
        language=language,
        items=tuple(items),
        attrs=attr_pairs(attrs),
    )


def new_document(
    title: str,
    blocks: Sequence[Block] = (),
    *,
    id_factory: Callable[[], str] = new_entity_id,
) -> BlockDocument:
    """Build a document with a generated identifier."""
    return BlockDocument(id=id_factory(), title=title, blocks=tuple(blocks))


__all__ = [
    "ALL_BLOCK_KINDS",
    "ALL_BLOCK_OPS",
    "ALL_INLINE_MARKS",
    "KNOWN_LANGUAGES",
    "LEGAL_HEADING_LEVELS",
    "LIST_STYLES",
    "MAX_HEADING_LEVEL",
    "MIN_HEADING_LEVEL",
    "SLASH_ORDER",
    "Block",
    "BlockDocument",
    "BlockKind",
    "BlockOp",
    "EditOperation",
    "InlineMark",
    "ValidationIssue",
    "ValidationSeverity",
    "attr_pairs",
    "canonical_checksum",
    "new_block",
    "new_document",
    "normalize_text",
]
