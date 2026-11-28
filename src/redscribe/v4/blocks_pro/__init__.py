"""Professional block editor for RedScribe v4.

The package ships immutable document types, a lossless markdown codec, an LCS
differ, autosave snapshots, structural validation, an in-memory store with
revisions, and v4 API handlers. Importing it has no side effects; ``register``
wires routes into a v4 route registry when called by namespace discovery.
"""

from __future__ import annotations

from redscribe.v4.blocks_pro.api import (
    ROUTE_SPECS,
    BlockRoutes,
    register,
)
from redscribe.v4.blocks_pro.service import (
    AutosaveManager,
    BlockDiff,
    BlockValidator,
    CodecError,
    DiffError,
    DocumentInvalidError,
    LineDelta,
    MarkdownCodec,
    Snapshot,
    SnapshotError,
    apply_mark,
    markdown_summary,
    strip_markdown,
)
from redscribe.v4.blocks_pro.storage import (
    BlockStore,
    ConflictError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    Revision,
    RevisionNotFoundError,
    StorageError,
)
from redscribe.v4.blocks_pro.types import (
    ALL_BLOCK_KINDS,
    ALL_BLOCK_OPS,
    ALL_INLINE_MARKS,
    SLASH_ORDER,
    Block,
    BlockDocument,
    BlockKind,
    BlockOp,
    EditOperation,
    InlineMark,
    ValidationIssue,
    ValidationSeverity,
    new_block,
    new_document,
)

__all__ = [
    "ALL_BLOCK_KINDS",
    "ALL_BLOCK_OPS",
    "ALL_INLINE_MARKS",
    "ROUTE_SPECS",
    "SLASH_ORDER",
    "AutosaveManager",
    "Block",
    "BlockDiff",
    "BlockDocument",
    "BlockKind",
    "BlockOp",
    "BlockRoutes",
    "BlockStore",
    "BlockValidator",
    "CodecError",
    "ConflictError",
    "DiffError",
    "DocumentInvalidError",
    "DocumentNotFoundError",
    "DuplicateDocumentError",
    "EditOperation",
    "InlineMark",
    "LineDelta",
    "MarkdownCodec",
    "Revision",
    "RevisionNotFoundError",
    "Snapshot",
    "SnapshotError",
    "StorageError",
    "ValidationIssue",
    "ValidationSeverity",
    "apply_mark",
    "markdown_summary",
    "new_block",
    "new_document",
    "register",
    "strip_markdown",
]
