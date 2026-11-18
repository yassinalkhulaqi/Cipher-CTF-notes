"""In-memory block document store with revisions and derived indices."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from redscribe.v2.blocks.autosave import (
    AutosaveBatch,
    AutosaveCoalescer,
    coalesce_batches,
)
from redscribe.v2.blocks.diff import (
    BlockPatch,
    DocumentDiff,
    PatchError,
    apply_patch,
    diff_documents,
    ensure_patch_id,
)
from redscribe.v2.blocks.markdown import parse_blocks, serialize_document
from redscribe.v2.blocks.mentions import (
    MentionHit,
    MentionIndex,
    MentionSuggestion,
    extract_mentions,
)
from redscribe.v2.blocks.model import Block, BlockDocument, make_block, make_document
from redscribe.v2.blocks.normalize import normalize_document
from redscribe.v2.blocks.revisions import (
    RevisionConflictError,
    RevisionManager,
    RevisionToken,
    issue_token,
)
from redscribe.v2.blocks.search import BlockSearchIndex, SearchResult
from redscribe.v2.blocks.types import BlockType, MentionKind
from redscribe.v2.blocks.validation import ValidationReport, validate_document


class BlockStoreError(ValueError):
    """Base error for invalid store operations."""


class BlockNotFoundError(BlockStoreError):
    """Raised when a document id is unknown."""


class BlockValidationError(BlockStoreError):
    """Raised when a document or patch fails validation."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("Block validation failed")
        self.report = report


class BlockStore:
    """Own documents, tokens, autosave batches, and derived indices."""

    def __init__(
        self,
        *,
        secret: str = "",
        autosave_interval_ms: int | None = None,
        autosave_max_wait_ms: int | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._documents: dict[str, BlockDocument] = {}
        self._revisions = RevisionManager(secret=secret)
        self._search = BlockSearchIndex()
        self._mentions = MentionIndex()
        options: dict[str, Any] = {}
        if autosave_interval_ms is not None:
            options["interval_ms"] = autosave_interval_ms
        if autosave_max_wait_ms is not None:
            options["max_wait_ms"] = autosave_max_wait_ms
        self._autosave = AutosaveCoalescer(**options)

    @property
    def revisions(self) -> RevisionManager:
        return self._revisions

    @property
    def autosave(self) -> AutosaveCoalescer:
        return self._autosave

    def reset(self) -> None:
        """Remove all documents and derived state."""
        with self._lock:
            self._documents.clear()
            self._revisions.clear()
            self._autosave.clear()
            self._search.clear()
            self._mentions.clear()

    def create(
        self,
        *,
        document_id: str | None = None,
        title: str = "",
        markdown: str = "",
        blocks: Sequence[Block] = (),
        tags: Sequence[str] = (),
        metadata: Mapping[str, str] | None = None,
    ) -> BlockDocument:
        """Create and index a new document."""
        resolved_blocks = tuple(blocks) if blocks else parse_blocks(markdown)
        document = make_document(
            document_id,
            title,
            resolved_blocks,
            tags=tags,
            metadata=metadata,
        )
        return self.put(document)

    def put(self, document: BlockDocument, *, validate: bool = True) -> BlockDocument:
        """Insert or replace a document without a revision check."""
        stored = normalize_document(document)
        if validate:
            report = validate_document(stored)
            if report.has_errors:
                raise BlockValidationError(report)
        with self._lock:
            self._documents[stored.id] = stored
            self._search.replace(stored)
            self._mentions.replace(stored)
            self._revisions.issue(stored)
            self._autosave.cancel(stored.id)
        return stored

    def get(self, document_id: str) -> BlockDocument:
        """Return a document or raise ``BlockNotFoundError``."""
        document = self.find(document_id)
        if document is None:
            raise BlockNotFoundError(f"Unknown block document: {document_id}")
        return document

    def find(self, document_id: str) -> BlockDocument | None:
        """Return a document when present."""
        with self._lock:
            return self._documents.get(document_id)

    def list_documents(self) -> list[BlockDocument]:
        """Return all documents in deterministic id order."""
        with self._lock:
            return [self._documents[key] for key in sorted(self._documents)]

    def list_ids(self) -> list[str]:
        """Return all document ids in deterministic order."""
        return [document.id for document in self.list_documents()]

    def delete(self, document_id: str) -> bool:
        """Remove a document and all derived entries."""
        with self._lock:
            existed = self._documents.pop(document_id, None) is not None
            self._search.remove(document_id)
            self._mentions.remove(document_id)
            self._autosave.cancel(document_id)
            return existed

    def save(
        self,
        document: BlockDocument,
        token: RevisionToken | str | None = None,
        *,
        require_token: bool = True,
    ) -> BlockDocument:
        """Persist a whole document after an optimistic revision check."""
        current = self.get(document.id)
        if require_token:
            if token is None:
                raise RevisionConflictError(
                    -1,
                    current.revision,
                    document_id=current.id,
                    reason="missing revision token",
                )
            self._revisions.verify(current, token)
        incoming = normalize_document(replace(document, revision=current.revision))
        report = validate_document(incoming)
        if report.has_errors:
            raise BlockValidationError(report)
        advanced = current.with_blocks(incoming.blocks).advanced()
        advanced = replace(
            advanced,
            title=incoming.title,
            tags=incoming.tags,
            metadata=dict(incoming.metadata),
        )
        with self._lock:
            self._documents[advanced.id] = advanced
            self._search.replace(advanced)
            self._mentions.replace(advanced)
            self._revisions.issue(advanced)
            self._autosave.acknowledge(advanced.id, advanced.revision)
        return advanced

    def apply_patch(
        self,
        document_id: str,
        patch: BlockPatch | Mapping[str, Any],
        token: RevisionToken | str | None = None,
        *,
        require_token: bool = True,
    ) -> BlockDocument:
        """Validate and apply an optimistic patch to a stored document."""
        current = self.get(document_id)
        resolved = BlockPatch.from_dict(patch) if isinstance(patch, Mapping) else patch
        resolved = ensure_patch_id(resolved, document_id)
        if require_token:
            if token is None:
                raise RevisionConflictError(
                    -1,
                    current.revision,
                    document_id=current.id,
                    reason="missing revision token",
                )
            self._revisions.verify(current, token)
        try:
            patched = apply_patch(current, resolved)
        except PatchError as exc:
            raise BlockStoreError(str(exc)) from exc
        normalized = normalize_document(patched)
        report = validate_document(normalized)
        if report.has_errors:
            raise BlockValidationError(report)
        with self._lock:
            self._documents[normalized.id] = normalized
            self._search.replace(normalized)
            self._mentions.replace(normalized)
            self._revisions.issue(normalized)
            self._autosave.acknowledge(normalized.id, normalized.revision)
        return normalized

    def queue_autosave(
        self,
        document_id: str,
        patch: BlockPatch | Mapping[str, Any],
        *,
        token: str = "",
    ) -> AutosaveBatch | None:
        """Queue patch operations for coalesced persistence."""
        current = self.get(document_id)
        resolved = BlockPatch.from_dict(patch) if isinstance(patch, Mapping) else patch
        return self._autosave.record(
            current,
            resolved.entries,
            token=token,
            label=resolved.label,
        )

    def flush_autosave(self, document_id: str | None = None) -> list[BlockDocument]:
        """Persist due (or selected) autosave batches."""
        if document_id is not None:
            batch = self._autosave.flush_document(document_id)
            batches = [batch] if batch is not None else []
        else:
            batches = list(self._autosave.flush())
        return [
            self.apply_patch(
                batch.document_id,
                BlockPatch(
                    batch.document_id,
                    batch.base_revision,
                    batch.entries,
                    batch.label,
                ),
                require_token=False,
            )
            for batch in batches
        ]

    def flush_all_autosave(self) -> list[BlockDocument]:
        """Persist every queued autosave batch immediately."""
        batches = coalesce_batches(self._autosave.flush_all())
        return [
            self.apply_patch(
                batch.document_id,
                BlockPatch(
                    batch.document_id,
                    batch.base_revision,
                    batch.entries,
                    batch.label,
                ),
                require_token=False,
            )
            for batch in batches
        ]

    def diff(
        self,
        left: BlockDocument | Mapping[str, Any] | str,
        right: BlockDocument | Mapping[str, Any] | str,
    ) -> DocumentDiff:
        """Diff two documents supplied by value or by stored id."""
        return diff_documents(self._resolve(left), self._resolve(right))

    def validate(
        self,
        target: BlockDocument | Mapping[str, Any] | str,
    ) -> ValidationReport:
        """Validate a document supplied by value or by stored id."""
        return validate_document(self._resolve(target))

    def token(self, document_id: str) -> RevisionToken:
        """Issue a fresh token for a stored document."""
        return issue_token(self.get(document_id))

    def token_string(self, document_id: str) -> str:
        """Issue an encoded token for a stored document."""
        from redscribe.v2.blocks.revisions import encode_token

        return encode_token(self.token(document_id))

    def search(
        self,
        query: str,
        *,
        block_types: Sequence[BlockType | str] | None = None,
        document_id: str | None = None,
        match_all: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Search indexed blocks."""
        return self._search.search(
            query,
            block_types=block_types,
            document_id=document_id,
            match_all=match_all,
            limit=limit,
            offset=offset,
        )

    def reindex(self) -> int:
        """Rebuild both derived indices from stored documents."""
        with self._lock:
            documents = self.list_documents()
            self._search.reindex(documents)
            self._mentions.clear()
            for document in documents:
                self._mentions.add(document)
            return len(documents)

    def mention_hits(
        self,
        target: str | None = None,
        *,
        kind: MentionKind | str | None = None,
    ) -> list[MentionHit]:
        """Return mentions by target or namespace."""
        if target is not None:
            return self._mentions.for_target(target, kind=kind)
        if kind is not None:
            return self._mentions.for_kind(kind)
        return self._mentions.all()

    def mention_suggestions(
        self,
        query: str,
        *,
        kind: MentionKind | str | None = None,
        limit: int = 12,
    ) -> list[MentionSuggestion]:
        """Return ranked mention autocomplete candidates."""
        return self._mentions.suggestions(query, kind=kind, limit=limit)

    def reindex_mentions_for(self, block_id: str, text: str) -> tuple[Any, ...]:
        """Extract mention tokens for a block without mutating documents."""
        return tuple(item.as_dict() for item in extract_mentions(text, block_id=block_id))

    def replace_blocks(
        self,
        document_id: str,
        markdown: str,
        token: RevisionToken | str | None = None,
    ) -> BlockDocument:
        """Replace all blocks from Markdown-like IR and persist the result."""
        current = self.get(document_id)
        if token is None:
            token = self.token(document_id)
        incoming = current.with_blocks(parse_blocks(markdown) or (make_block(),))
        return self.save(incoming, token)

    def status(self) -> dict[str, Any]:
        """Return a compact status payload for API consumers."""
        with self._lock:
            return {
                "documents": len(self._documents),
                "indexed_blocks": self._search.size(),
                "indexed_mentions": self._mentions.size(),
                "autosave": self._autosave.state(),
                "revision_history": len(self._revisions.history),
            }

    def markdown(self, document_id: str) -> str:
        """Serialize a stored document to Markdown-like IR."""
        return serialize_document(self.get(document_id))

    def block(self, document_id: str, block_id: str) -> Block:
        """Return one block from a stored document."""
        document = self.get(document_id)
        block = document.find(block_id)
        if block is None:
            raise BlockNotFoundError(f"Unknown block: {block_id}")
        return block

    def normalize_detached(self, payload: Mapping[str, Any]) -> BlockDocument:
        """Normalize a document payload without storing it."""
        return normalize_document(payload)

    def _resolve(
        self,
        value: BlockDocument | Mapping[str, Any] | str,
    ) -> BlockDocument:
        if isinstance(value, str):
            return self.get(value)
        if isinstance(value, Mapping):
            return normalize_document(value)
        return value


def create_store_with_sample(*, title: str = "Block notes") -> tuple[BlockStore, BlockDocument]:
    """Build a store seeded with one representative document."""
    store = BlockStore()
    document = store.create(
        title=title,
        blocks=(
            make_block(BlockType.HEADING, title, level=1),
            make_block(BlockType.PARAGRAPH, "Start writing with @[vault](note:vault)"),
        ),
    )
    return store, document
