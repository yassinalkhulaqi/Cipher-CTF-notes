"""In-memory persistence adapters for the professional block editor.

:class:`BlockStore` keeps documents, append-only revisions, and autosave
snapshots behind one deterministic interface. It is intentionally storage
agnostic: every record is a plain dataclass that can be mapped onto SQLite or a
file-backed adapter without changing callers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from redscribe.v4.blocks_pro.service import (
    AutosaveManager,
    BlockDiff,
    BlockValidator,
    DocumentInvalidError,
    MarkdownCodec,
    Snapshot,
    SnapshotError,
    _utc_now,
)
from redscribe.v4.blocks_pro.types import (
    Block,
    BlockDocument,
    EditOperation,
    canonical_checksum,
)
from redscribe.v4.contracts import new_entity_id


class StorageError(ValueError):
    """Base class for store-level failures."""


class DocumentNotFoundError(StorageError):
    """Raised when a document id is not present in the store."""


class DuplicateDocumentError(StorageError):
    """Raised when a create operation collides with an existing id."""


class RevisionNotFoundError(StorageError):
    """Raised when a revision number is unknown for a document."""


class ConflictError(StorageError):
    """Raised when an optimistic checksum precondition fails."""


@dataclass(frozen=True, slots=True)
class Revision:
    """An append-only immutable version of a document."""

    id: str
    document_id: str
    number: int
    document: BlockDocument
    created_at: str
    checksum: str
    author: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "number": self.number,
            "document": self.document.to_dict(),
            "created_at": self.created_at,
            "checksum": self.checksum,
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Revision:
        raw_document = data.get("document")
        if not isinstance(raw_document, dict):
            raise StorageError("revision document must be a mapping")
        return cls(
            id=str(data.get("id", "")),
            document_id=str(data.get("document_id", "")),
            number=int(str(data.get("number", 0))),
            document=BlockDocument.from_dict(raw_document),
            created_at=str(data.get("created_at", "")),
            checksum=str(data.get("checksum", "")),
            author=str(data.get("author", "")),
        )


class BlockStore:
    """CRUD, revision history, snapshots, export, and search for documents."""

    def __init__(
        self,
        id_factory: Callable[[], str] = new_entity_id,
        clock: Callable[[], str] = _utc_now,
        validator: BlockValidator | None = None,
        autosave: AutosaveManager | None = None,
    ) -> None:
        self.id_factory = id_factory
        self.clock = clock
        self.validator = validator or BlockValidator()
        self.autosave = autosave or AutosaveManager(id_factory=id_factory, clock=clock)
        self._documents: dict[str, BlockDocument] = {}
        self._revisions: dict[str, list[Revision]] = {}

    def create(self, document: BlockDocument, author: str = "local") -> Revision:
        """Store a new document and record its first revision."""
        if document.id in self._documents:
            raise DuplicateDocumentError(f"document already exists: {document.id}")
        return self._commit(document, author)

    def save(
        self,
        document: BlockDocument,
        author: str = "local",
        expected_checksum: str = "",
    ) -> Revision:
        """Create or replace a document with an optional concurrency guard."""
        current = self._documents.get(document.id)
        if current is not None and expected_checksum and current.checksum() != expected_checksum:
            raise ConflictError("document changed since it was loaded")
        return self._commit(document, author)

    def _commit(self, document: BlockDocument, author: str) -> Revision:
        try:
            self.validator.require_valid(document)
        except DocumentInvalidError as exc:
            raise StorageError(str(exc)) from exc
        history = self._revisions.get(document.id, [])
        revision = Revision(
            id=self.id_factory(),
            document_id=document.id,
            number=len(history) + 1,
            document=document,
            created_at=self.clock(),
            checksum=document.checksum(),
            author=author[:120] or "local",
        )
        self._documents[document.id] = document
        self._revisions.setdefault(document.id, []).append(revision)
        return revision

    def get(self, document_id: str) -> BlockDocument:
        document = self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(f"document not found: {document_id}")
        return document

    def find(self, document_id: str) -> BlockDocument | None:
        return self._documents.get(document_id)

    def exists(self, document_id: str) -> bool:
        return document_id in self._documents

    def list(self) -> tuple[BlockDocument, ...]:
        return tuple(self._documents[key] for key in sorted(self._documents))

    def delete(self, document_id: str) -> bool:
        if document_id not in self._documents:
            return False
        del self._documents[document_id]
        self._revisions.pop(document_id, None)
        self.autosave.clear(document_id)
        return True

    def checksum(self, document_id: str) -> str:
        return self.get(document_id).checksum()

    def replace(
        self,
        document_id: str,
        blocks: Sequence[Block],
        title: str | None = None,
        author: str = "local",
        expected_checksum: str = "",
    ) -> Revision:
        """Replace the body of a document with a new block sequence."""
        current = self.get(document_id)
        if expected_checksum and current.checksum() != expected_checksum:
            raise ConflictError("document changed since it was loaded")
        replacement = current.with_blocks(tuple(blocks))
        if title is not None:
            replacement = replacement.with_title(title)
        return self._commit(replacement, author)

    def apply(
        self,
        document_id: str,
        operations: Sequence[EditOperation],
        author: str = "local",
        expected_checksum: str = "",
        differ: BlockDiff | None = None,
    ) -> tuple[Revision, tuple[EditOperation, ...]]:
        """Validate and replay a patch, then commit the resulting document."""
        current = self.get(document_id)
        if expected_checksum and current.checksum() != expected_checksum:
            raise ConflictError("document changed since it was loaded")
        issues = self.validator.validate_operations(operations, current)
        if issues:
            raise StorageError(issues[0].message)
        diff = differ or BlockDiff()
        updated = diff.apply(current, operations)
        revision = self._commit(updated, author)
        return revision, tuple(operations)

    def history(self, document_id: str) -> tuple[Revision, ...]:
        self.get(document_id)
        return tuple(self._revisions.get(document_id, ()))

    def revision(self, document_id: str, number: int) -> Revision:
        for item in self.history(document_id):
            if item.number == number:
                return item
        raise RevisionNotFoundError(f"revision {number} not found for {document_id}")

    def latest_revision(self, document_id: str) -> Revision:
        items = self._revisions.get(document_id, ())
        if not items:
            raise RevisionNotFoundError(f"no revisions for {document_id}")
        return items[-1]

    def restore_revision(self, document_id: str, number: int, author: str = "local") -> Revision:
        target = self.revision(document_id, number)
        return self._commit(target.document, author)

    def prune_history(self, document_id: str, keep: int = 10) -> int:
        """Trim history to the newest ``keep`` revisions; return the removed count."""
        if keep < 1:
            raise StorageError("keep must be >= 1")
        items = self._revisions.get(document_id, [])
        if len(items) <= keep:
            return 0
        removed = len(items) - keep
        self._revisions[document_id] = items[removed:]
        return removed

    def snapshot(self, document_id: str, reason: str = "manual") -> Snapshot:
        return self.autosave.create(self.get(document_id), reason)

    def snapshots(self, document_id: str) -> tuple[Snapshot, ...]:
        return self.autosave.list_for(document_id)

    def restore_snapshot(
        self,
        document_id: str,
        snapshot_id: str,
        expected_checksum: str = "",
        author: str = "local",
    ) -> Revision:
        for item in self.snapshots(document_id):
            if item.id == snapshot_id:
                try:
                    restored = self.autosave.restore(item, expected_checksum)
                except SnapshotError as exc:
                    raise ConflictError(str(exc)) from exc
                return self._commit(restored, author)
        raise SnapshotError(f"snapshot not found: {snapshot_id}")

    def export(self, document_id: str, codec: MarkdownCodec | None = None) -> str:
        encoder = codec or MarkdownCodec(annotate_ids=True)
        return encoder.encode(self.get(document_id))

    def import_markdown(
        self,
        markdown: str,
        document_id: str | None = None,
        codec: MarkdownCodec | None = None,
        author: str = "local",
    ) -> BlockDocument:
        decoder = codec or MarkdownCodec(annotate_ids=True)
        document = decoder.decode(markdown)
        if document_id is not None:
            document = BlockDocument(document_id, document.title, document.blocks)
        return self.create(document, author).document

    def search(self, query: str, limit: int = 20) -> tuple[BlockDocument, ...]:
        """Return documents whose title or block content contains ``query``."""
        needle = query.strip().casefold()
        if not needle or limit < 1:
            return ()
        matches: list[BlockDocument] = []
        for document in self.list():
            haystack = [document.title]
            haystack.extend(block.text for block in document.blocks)
            haystack.extend(item for block in document.blocks for item in block.items)
            if any(needle in value.casefold() for value in haystack):
                matches.append(document)
            if len(matches) >= limit:
                break
        return tuple(matches)

    def stats(self) -> dict[str, int]:
        return {
            "documents": len(self._documents),
            "blocks": sum(len(document.blocks) for document in self._documents.values()),
            "revisions": sum(len(items) for items in self._revisions.values()),
            "snapshots": self.autosave.count(),
        }

    def digest(self) -> str:
        """Return a checksum over the complete ordered store contents."""
        payload = {item.id: item.to_dict() for item in self.list()}
        return canonical_checksum(payload)


__all__ = [
    "BlockStore",
    "ConflictError",
    "DocumentNotFoundError",
    "DuplicateDocumentError",
    "Revision",
    "RevisionNotFoundError",
    "StorageError",
]
