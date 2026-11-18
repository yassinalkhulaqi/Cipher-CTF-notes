"""Bridge between structured block documents and vault note bodies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from redscribe.domain.models import Node
from redscribe.storage.db import Vault
from redscribe.v2.blocks.diff import BlockPatch
from redscribe.v2.blocks.markdown import parse_document, serialize_document
from redscribe.v2.blocks.mentions import MentionHit, MentionSuggestion
from redscribe.v2.blocks.model import BlockDocument, make_block
from redscribe.v2.blocks.normalize import normalize_document
from redscribe.v2.blocks.revisions import RevisionToken, verify_token
from redscribe.v2.blocks.search import SearchResult
from redscribe.v2.blocks.store import BlockStore
from redscribe.v2.blocks.types import MentionKind
from redscribe.v2.blocks.validation import validate_document

DOCUMENT_PREFIX = "note-"


def document_id_for_note(note_id: int) -> str:
    """Return the canonical block document id for a vault note."""
    return f"{DOCUMENT_PREFIX}{note_id}"


def note_id_for_document(document_id: str) -> int | None:
    """Extract a note id from a canonical document id."""
    if not document_id.startswith(DOCUMENT_PREFIX):
        return None
    suffix = document_id[len(DOCUMENT_PREFIX) :]
    return int(suffix) if suffix.isdigit() else None


def document_from_note(node: Node) -> BlockDocument:
    """Parse a vault note into a structured block document."""
    return normalize_document(
        parse_document(
            node.content,
            document_id=document_id_for_note(node.id),
            title=node.title,
            tags=node.tag_list,
        )
    )


def note_content_from_document(document: BlockDocument) -> str:
    """Render a document body suitable for ``Vault.update_node``."""
    return serialize_document(document)


class BlockVaultService:
    """Coordinate vault note content with the in-memory block store."""

    def __init__(self, vault: Vault, store: BlockStore | None = None) -> None:
        self._vault = vault
        self._store = store or BlockStore()

    @property
    def store(self) -> BlockStore:
        return self._store

    @property
    def vault(self) -> Vault:
        return self._vault

    def load(self, note_id: int, *, refresh: bool = False) -> BlockDocument:
        """Load a note into the block store and return its document."""
        document_id = document_id_for_note(note_id)
        existing = self._store.find(document_id)
        if existing is not None and not refresh:
            return existing
        node = self._vault.get_node(note_id)
        if node is None:
            raise LookupError(f"Note does not exist: {note_id}")
        document = document_from_note(node)
        metadata = dict(document.metadata)
        metadata.update(
            {
                "note_id": str(note_id),
                "target": node.target,
                "status": node.status,
            }
        )
        document = replace(document, metadata=metadata)
        return self._store.put(document)

    def load_many(self, note_ids: Sequence[int], *, refresh: bool = False) -> list[BlockDocument]:
        """Load several notes and return their documents."""
        return [self.load(note_id, refresh=refresh) for note_id in note_ids]

    def load_all_notes(self, *, refresh: bool = False) -> list[BlockDocument]:
        """Load every live note in the vault into the block store."""
        return self.load_many(
            [node.id for node in self._vault.live_nodes() if node.is_note],
            refresh=refresh,
        )

    def save(
        self,
        note_id: int,
        document: BlockDocument,
        token: RevisionToken | str,
    ) -> BlockDocument:
        """Validate a document, write its IR to the note, and advance revision."""
        current = self.load(note_id)
        verify_token(current, token)
        incoming = normalize_document(replace(document, revision=current.revision))
        report = validate_document(incoming)
        if report.has_errors:
            raise ValueError("Block document is invalid")
        advanced = current.with_blocks(incoming.blocks).advanced()
        advanced = replace(
            advanced,
            title=incoming.title,
            tags=incoming.tags,
            metadata={**dict(incoming.metadata), "note_id": str(note_id)},
        )
        content = note_content_from_document(advanced)
        if not content.strip():
            content = "(empty paragraph)"
        self._vault.update_node(note_id, content=content)
        return self._store.put(advanced)

    def save_patch(
        self,
        note_id: int,
        patch: BlockPatch | Mapping[str, Any],
        token: RevisionToken | str,
    ) -> BlockDocument:
        """Apply a patch to a note document and persist the result."""
        current = self.load(note_id)
        verify_token(current, token)
        patched = self._store.apply_patch(current.id, patch, token)
        content = note_content_from_document(patched)
        self._vault.update_node(note_id, content=content or "(empty paragraph)")
        return patched

    def autosave(
        self,
        note_id: int,
        patch: BlockPatch | Mapping[str, Any],
        *,
        token: str = "",
    ) -> Any:
        """Queue autosave operations for a note document."""
        document = self.load(note_id)
        return self._store.queue_autosave(document.id, patch, token=token)

    def flush(self, document_id: str | None = None) -> list[BlockDocument]:
        """Persist queued autosave batches back into vault notes."""
        batches = list(self._store.autosave.flush_all() if document_id is None else [])
        if document_id is not None:
            batch = self._store.autosave.flush_document(document_id)
            batches = [batch] if batch is not None else []
        saved: list[BlockDocument] = []
        for batch in batches:
            note_id = note_id_for_document(batch.document_id)
            if note_id is None:
                continue
            patched = self._store.apply_patch(
                batch.document_id,
                BlockPatch(
                    batch.document_id,
                    batch.base_revision,
                    batch.entries,
                    batch.label,
                ),
                require_token=False,
            )
            content = note_content_from_document(patched)
            self._vault.update_node(note_id, content=content or "(empty paragraph)")
            saved.append(patched)
        return saved

    def sync_note(self, note_id: int, document: BlockDocument) -> str:
        """Write an already-patched document body back to its vault note."""
        content = note_content_from_document(document) or "(empty paragraph)"
        self._vault.update_node(note_id, content=content)
        return content

    def token(self, note_id: int) -> RevisionToken:
        """Issue a token for the current state of a note document."""
        return self._store.token(self.load(note_id).id)

    def search(self, query: str, **options: Any) -> list[SearchResult]:
        """Search all loaded note blocks."""
        return self._store.search(query, **options)

    def mentions(
        self,
        target: str | None = None,
        *,
        kind: MentionKind | str | None = None,
    ) -> list[MentionHit]:
        """Return note-document mentions."""
        return self._store.mention_hits(target, kind=kind)

    def suggestions(
        self,
        query: str,
        *,
        kind: MentionKind | str | None = None,
        limit: int = 12,
    ) -> list[MentionSuggestion]:
        """Return mention suggestions from loaded notes."""
        return self._store.mention_suggestions(query, kind=kind, limit=limit)

    def status(self) -> dict[str, Any]:
        """Return block-editor telemetry for the service and vault."""
        payload = self._store.status()
        payload["loaded_notes"] = sum(
            1
            for document_id in self._store.list_ids()
            if note_id_for_document(document_id) is not None
        )
        return payload

    def reset(self) -> None:
        """Clear all in-memory block state."""
        self._store.reset()


def ensure_document_block(document: BlockDocument) -> BlockDocument:
    """Ensure a document has at least one editable block."""
    if document.blocks:
        return document
    return replace(document, blocks=(make_block(),))
