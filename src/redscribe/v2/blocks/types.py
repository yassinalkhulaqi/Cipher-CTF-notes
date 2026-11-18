"""Enums and small value types used by the block model."""

from __future__ import annotations

from enum import Enum


class BlockType(str, Enum):
    """Supported block kinds in the V2 editor."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    CODE = "code"
    QUOTE = "quote"
    LIST = "list"
    TABLE = "table"
    CALLOUT = "callout"
    DIVIDER = "divider"
    IMAGE = "image"


class ListStyle(str, Enum):
    """Marker style for list blocks."""

    BULLET = "bullet"
    ORDERED = "ordered"
    TASKS = "tasks"


class CalloutTone(str, Enum):
    """Semantic tones for callout blocks."""

    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"
    DANGER = "danger"
    NOTE = "note"
    TIP = "tip"


class IssueSeverity(str, Enum):
    """Validation issue levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class MentionKind(str, Enum):
    """Namespaces addressable from a mention token."""

    NOTE = "note"
    USER = "user"
    TARGET = "target"
    FINDING = "finding"
    EVIDENCE = "evidence"
    TAG = "tag"


class PatchOperation(str, Enum):
    """Editable operations carried by an optimistic patch."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"


class DiffOperation(str, Enum):
    """Read-only operations describing a document delta."""

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    MOVE = "move"


BLOCK_TYPES: tuple[BlockType, ...] = tuple(BlockType)
LIST_STYLES: tuple[ListStyle, ...] = tuple(ListStyle)
CALLOUT_TONES: tuple[CalloutTone, ...] = tuple(CalloutTone)
MENTION_KINDS: tuple[MentionKind, ...] = tuple(MentionKind)
TEXT_BLOCK_TYPES: frozenset[BlockType] = frozenset(
    {
        BlockType.PARAGRAPH,
        BlockType.HEADING,
        BlockType.CODE,
        BlockType.QUOTE,
        BlockType.CALLOUT,
    }
)
SLASH_BLOCK_TYPES: tuple[BlockType, ...] = (
    BlockType.PARAGRAPH,
    BlockType.HEADING,
    BlockType.CODE,
    BlockType.QUOTE,
    BlockType.LIST,
    BlockType.TABLE,
    BlockType.CALLOUT,
    BlockType.DIVIDER,
    BlockType.IMAGE,
)


def block_type_values() -> list[str]:
    """Return all registered block type names in menu order."""
    return [item.value for item in SLASH_BLOCK_TYPES]


def mention_kind_values() -> list[str]:
    """Return all registered mention namespace names."""
    return [item.value for item in MENTION_KINDS]
