"""Structured block editor domain for API v2."""

from __future__ import annotations

from redscribe.v2.blocks.autosave import (
    AutosaveBatch,
    AutosaveCoalescer,
    coalesce_batches,
)
from redscribe.v2.blocks.diff import (
    BlockPatch,
    DiffEntry,
    DocumentDiff,
    PatchEntry,
    PatchError,
    apply_patch,
    diff_documents,
    make_patch,
    merge_entries,
    patch_from_diff,
)
from redscribe.v2.blocks.markdown import (
    parse_blocks,
    parse_document,
    serialize_block,
    serialize_document,
)
from redscribe.v2.blocks.mentions import (
    MentionIndex,
    extract_mentions,
    refresh_block_mentions,
)
from redscribe.v2.blocks.model import (
    Block,
    BlockDocument,
    Mention,
    make_block,
    make_document,
)
from redscribe.v2.blocks.normalize import normalize_block, normalize_document
from redscribe.v2.blocks.revisions import (
    RevisionConflictError,
    RevisionManager,
    RevisionToken,
    decode_token,
    encode_token,
    issue_token,
    verify_token,
)
from redscribe.v2.blocks.search import BlockSearchIndex, SearchResult
from redscribe.v2.blocks.store import BlockStore, create_store_with_sample
from redscribe.v2.blocks.types import (
    BLOCK_TYPES,
    SLASH_BLOCK_TYPES,
    BlockType,
    CalloutTone,
    DiffOperation,
    ListStyle,
    MentionKind,
    PatchOperation,
)
from redscribe.v2.blocks.validation import (
    ValidationIssue,
    ValidationReport,
    validate_document,
    validate_patch,
)
from redscribe.v2.blocks.vault import BlockVaultService, document_from_note

__all__ = [
    "BLOCK_TYPES",
    "SLASH_BLOCK_TYPES",
    "AutosaveBatch",
    "AutosaveCoalescer",
    "Block",
    "BlockDocument",
    "BlockPatch",
    "BlockSearchIndex",
    "BlockStore",
    "BlockType",
    "BlockVaultService",
    "CalloutTone",
    "DiffEntry",
    "DiffOperation",
    "DocumentDiff",
    "ListStyle",
    "Mention",
    "MentionIndex",
    "MentionKind",
    "PatchEntry",
    "PatchError",
    "PatchOperation",
    "RevisionConflictError",
    "RevisionManager",
    "RevisionToken",
    "SearchResult",
    "ValidationIssue",
    "ValidationReport",
    "apply_patch",
    "coalesce_batches",
    "create_store_with_sample",
    "decode_token",
    "diff_documents",
    "document_from_note",
    "encode_token",
    "extract_mentions",
    "issue_token",
    "make_block",
    "make_document",
    "make_patch",
    "merge_entries",
    "normalize_block",
    "normalize_document",
    "parse_blocks",
    "parse_document",
    "patch_from_diff",
    "refresh_block_mentions",
    "serialize_block",
    "serialize_document",
    "validate_document",
    "validate_patch",
    "verify_token",
]
