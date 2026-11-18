"""Block-level diffing and optimistic patch application."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any

from redscribe.v2.blocks.constants import MAX_PATCH_OPS
from redscribe.v2.blocks.model import Block, BlockDocument, new_id
from redscribe.v2.blocks.types import DiffOperation, PatchOperation


class PatchError(ValueError):
    """Raised when a patch cannot be applied to a document."""


def block_signature(block: Block) -> tuple[Any, ...]:
    """Return a hashable signature of everything that affects rendering."""
    return (
        block.type.value,
        block.text,
        block.level,
        block.language,
        block.items,
        block.checked,
        block.style.value,
        block.headers,
        block.rows,
        block.tone.value,
        block.alt,
        block.source,
        tuple(sorted(block.attrs.items())),
    )


def document_signature(document: BlockDocument) -> tuple[Any, ...]:
    """Return a hashable signature for a whole document."""
    return (
        document.title,
        document.tags,
        tuple(sorted(document.metadata.items())),
        tuple(block_signature(block) for block in document.blocks),
    )


def content_hash(document: BlockDocument) -> str:
    """Return a stable SHA-256 digest of document content."""
    payload = json.dumps(
        [block.as_dict() for block in document.blocks],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """One read-only change between two document states."""

    operation: DiffOperation
    block_id: str
    index: int
    previous_index: int | None = None
    block: Block | None = None
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "block_id": self.block_id,
            "index": self.index,
            "previous_index": self.previous_index,
            "block": self.block.as_dict() if self.block is not None else None,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class DocumentDiff:
    """The ordered delta between two documents."""

    left_id: str
    right_id: str
    left_revision: int
    right_revision: int
    entries: tuple[DiffEntry, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.entries)

    def counts(self) -> dict[str, int]:
        """Return the number of changes by operation."""
        counts = {item.value: 0 for item in DiffOperation}
        for entry in self.entries:
            counts[entry.operation.value] += 1
        return counts

    def block_ids(self) -> list[str]:
        """Return touched block ids in first-seen order."""
        return list(dict.fromkeys(entry.block_id for entry in self.entries))

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "left_revision": self.left_revision,
            "right_revision": self.right_revision,
            "changed": self.changed,
            "counts": self.counts(),
            "entries": [entry.as_dict() for entry in self.entries],
        }


def _describe(operation: DiffOperation, block: Block | None) -> str:
    label = block.type.value if block is not None else "block"
    text = block.plain_text.replace("\n", " ")[:60] if block is not None else ""
    return f"{operation.value} {label}: {text}" if text else f"{operation.value} {label}"


def _addition_operation(left: BlockDocument, block: Block) -> DiffOperation:
    previous = left.find(block.id)
    if previous is None:
        return DiffOperation.ADD
    if block_signature(previous) != block_signature(block):
        return DiffOperation.REPLACE
    return DiffOperation.MOVE


def diff_documents(left: BlockDocument, right: BlockDocument) -> DocumentDiff:
    """Compute a deterministic block-level diff from ``left`` to ``right``."""
    left_signatures = [block_signature(block) for block in left.blocks]
    right_signatures = [block_signature(block) for block in right.blocks]
    matcher = SequenceMatcher(None, left_signatures, right_signatures, autojunk=False)
    entries: list[DiffEntry] = []
    left_ids = left.block_ids

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                old = left.blocks[i1 + offset]
                new = right.blocks[j1 + offset]
                if old.id != new.id:
                    entries.append(
                        DiffEntry(
                            DiffOperation.REPLACE,
                            old.id,
                            j1 + offset,
                            i1 + offset,
                            new,
                            _describe(DiffOperation.REPLACE, new),
                        )
                    )
        elif tag == "delete":
            for offset in range(i1, i2):
                block = left.blocks[offset]
                entries.append(
                    DiffEntry(
                        DiffOperation.REMOVE,
                        block.id,
                        offset,
                        offset,
                        None,
                        _describe(DiffOperation.REMOVE, block),
                    )
                )
        elif tag == "insert":
            for offset in range(j1, j2):
                block = right.blocks[offset]
                previous = left_ids.index(block.id) if block.id in left_ids else None
                operation = _addition_operation(left, block)
                entries.append(
                    DiffEntry(
                        operation,
                        block.id,
                        offset,
                        previous,
                        block,
                        _describe(operation, block),
                    )
                )
        else:
            for offset in range(i1, i2):
                block = left.blocks[offset]
                entries.append(
                    DiffEntry(
                        DiffOperation.REMOVE,
                        block.id,
                        j1,
                        offset,
                        None,
                        _describe(DiffOperation.REMOVE, block),
                    )
                )
            for offset in range(j1, j2):
                block = right.blocks[offset]
                previous = left_ids.index(block.id) if block.id in left_ids else None
                operation = _addition_operation(left, block)
                entries.append(
                    DiffEntry(
                        operation,
                        block.id,
                        offset,
                        previous,
                        block,
                        _describe(operation, block),
                    )
                )

    kept_ids = {
        entry.block_id
        for entry in entries
        if entry.operation in (DiffOperation.MOVE, DiffOperation.REPLACE)
    }
    simplified = [
        entry
        for entry in entries
        if entry.operation is not DiffOperation.REMOVE or entry.block_id not in kept_ids
    ]

    return DocumentDiff(
        left_id=left.id,
        right_id=right.id,
        left_revision=left.revision,
        right_revision=right.revision,
        entries=tuple(simplified),
    )


@dataclass(frozen=True, slots=True)
class PatchEntry:
    """One reversible editing operation."""

    operation: PatchOperation
    block_id: str
    block: Block | None = None
    index: int | None = None
    previous_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "block_id": self.block_id,
            "block": self.block.as_dict() if self.block is not None else None,
            "index": self.index,
            "previous_index": self.previous_index,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PatchEntry:
        try:
            operation = PatchOperation(str(value.get("operation", "")))
        except ValueError as exc:
            raise PatchError(f"Unknown patch operation: {value.get('operation')}") from exc
        raw_block = value.get("block")
        block = Block.from_dict(raw_block) if isinstance(raw_block, Mapping) else None
        return cls(
            operation=operation,
            block_id=str(value.get("block_id", "")),
            block=block,
            index=value.get("index") if isinstance(value.get("index"), int) else None,
            previous_index=value.get("previous_index")
            if isinstance(value.get("previous_index"), int)
            else None,
        )


@dataclass(frozen=True, slots=True)
class BlockPatch:
    """A set of editing operations guarded by a base revision."""

    document_id: str
    base_revision: int
    entries: tuple[PatchEntry, ...] = ()
    label: str = ""

    @property
    def size(self) -> int:
        return len(self.entries)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "base_revision": self.base_revision,
            "label": self.label,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BlockPatch:
        raw_entries = value.get("entries", ())
        if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
            raise PatchError("Patch entries must be a list")
        revision = value.get("base_revision", 0)
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise PatchError("base_revision must be an integer")
        return cls(
            document_id=str(value.get("document_id", "")),
            base_revision=revision,
            entries=tuple(
                PatchEntry.from_dict(item) for item in raw_entries if isinstance(item, Mapping)
            ),
            label=str(value.get("label", "")),
        )


def make_patch(
    document: BlockDocument,
    entries: Iterable[PatchEntry] = (),
    *,
    label: str = "",
) -> BlockPatch:
    """Create a patch rooted at a document's current revision."""
    values = tuple(entries)
    if len(values) > MAX_PATCH_OPS:
        raise PatchError(f"A patch may contain at most {MAX_PATCH_OPS} operations")
    return BlockPatch(document.id, document.revision, values, label)


def _insert_entry(block: Block, index: int) -> PatchEntry:
    return PatchEntry(PatchOperation.INSERT, block.id, block=block, index=index)


def _update_entry(block: Block, previous_index: int) -> PatchEntry:
    return PatchEntry(PatchOperation.UPDATE, block.id, block=block, index=previous_index)


def _delete_entry(block_id: str, previous_index: int) -> PatchEntry:
    return PatchEntry(PatchOperation.DELETE, block_id, previous_index=previous_index)


def patch_from_diff(
    left: BlockDocument,
    right: BlockDocument,
    diff: DocumentDiff | None = None,
) -> BlockPatch:
    """Convert a diff into a patch that transforms ``left`` into ``right``."""
    delta = diff if diff is not None else diff_documents(left, right)
    entries: list[PatchEntry] = []
    for entry in delta.entries:
        if entry.operation is DiffOperation.ADD and entry.block is not None:
            entries.append(_insert_entry(entry.block, entry.index))
        elif entry.operation is DiffOperation.REMOVE:
            entries.append(_delete_entry(entry.block_id, entry.previous_index or 0))
        elif entry.operation is DiffOperation.REPLACE and entry.block is not None:
            entries.append(_update_entry(entry.block, entry.previous_index or 0))
        elif entry.operation is DiffOperation.MOVE and entry.block is not None:
            entries.append(
                PatchEntry(
                    PatchOperation.MOVE,
                    entry.block_id,
                    block=entry.block,
                    index=entry.index,
                    previous_index=entry.previous_index,
                )
            )
    return BlockPatch(left.id, left.revision, tuple(entries), "diff")


def invert_patch(
    before: BlockDocument,
    after: BlockDocument,
) -> BlockPatch:
    """Build a patch that restores ``before`` from ``after``."""
    return patch_from_diff(after, before)


def _position(blocks: Sequence[Block], block_id: str) -> int:
    for index, block in enumerate(blocks):
        if block.id == block_id:
            return index
    return -1


def apply_patch(
    document: BlockDocument,
    patch: BlockPatch,
    *,
    require_revision: bool = True,
) -> BlockDocument:
    """Apply a patch and return an advanced document."""
    if patch.document_id and patch.document_id != document.id:
        raise PatchError("Patch targets a different document")
    if require_revision and patch.base_revision != document.revision:
        raise PatchError(
            f"Revision conflict: patch base {patch.base_revision}, current {document.revision}"
        )
    blocks = list(document.blocks)
    for entry in patch.entries:
        if entry.operation is PatchOperation.INSERT:
            if entry.block is None:
                raise PatchError("Insert operation requires a block")
            if _position(blocks, entry.block.id) >= 0:
                raise PatchError(f"Block {entry.block.id} already exists")
            index = entry.index if entry.index is not None else len(blocks)
            blocks.insert(max(0, min(index, len(blocks))), entry.block)
        elif entry.operation is PatchOperation.UPDATE:
            if entry.block is None:
                raise PatchError("Update operation requires a block")
            position = _position(blocks, entry.block_id)
            if position < 0:
                raise PatchError(f"Block {entry.block_id} does not exist")
            blocks[position] = entry.block
        elif entry.operation is PatchOperation.DELETE:
            position = _position(blocks, entry.block_id)
            if position < 0:
                raise PatchError(f"Block {entry.block_id} does not exist")
            blocks.pop(position)
        elif entry.operation is PatchOperation.MOVE:
            position = _position(blocks, entry.block_id)
            if position < 0:
                raise PatchError(f"Block {entry.block_id} does not exist")
            block = blocks.pop(position)
            index = entry.index if entry.index is not None else len(blocks)
            blocks.insert(max(0, min(index, len(blocks))), block)
    return document.with_blocks(blocks).advanced(patch.base_revision + 1)


def merge_entries(entries: Sequence[PatchEntry]) -> tuple[PatchEntry, ...]:
    """Coalesce redundant operations while preserving their net effect."""
    merged: list[PatchEntry] = []
    for entry in entries:
        same = [index for index, item in enumerate(merged) if item.block_id == entry.block_id]
        if entry.operation is PatchOperation.DELETE:
            for index in reversed(same):
                merged.pop(index)
            merged.append(entry)
            continue
        if entry.operation is PatchOperation.INSERT:
            deleted = next(
                (
                    merged[index]
                    for index in reversed(same)
                    if merged[index].operation is PatchOperation.DELETE
                ),
                None,
            )
            for index in reversed(same):
                if merged[index].operation in (PatchOperation.INSERT, PatchOperation.DELETE):
                    merged.pop(index)
            if deleted is not None:
                merged.append(
                    replace(
                        entry,
                        operation=PatchOperation.UPDATE,
                        index=entry.index
                        if entry.index is not None
                        else deleted.previous_index or 0,
                        previous_index=deleted.previous_index,
                    )
                )
            else:
                merged.append(entry)
            continue
        if entry.operation is PatchOperation.UPDATE:
            if same:
                index = same[-1]
                previous = merged[index]
                if previous.operation is PatchOperation.INSERT:
                    merged[index] = replace(
                        entry,
                        operation=PatchOperation.INSERT,
                        index=previous.index,
                        previous_index=previous.previous_index,
                    )
                    continue
                if previous.operation is PatchOperation.UPDATE:
                    merged[index] = entry
                    continue
            merged.append(entry)
            continue
        for index in reversed(same):
            merged.pop(index)
        merged.append(entry)
    return tuple(merged)


def patch_summary(patch: BlockPatch) -> dict[str, int]:
    """Return per-operation counts for a patch."""
    summary = {item.value: 0 for item in PatchOperation}
    for entry in patch.entries:
        summary[entry.operation.value] += 1
    return summary


def rebase_patch(patch: BlockPatch, revision: int) -> BlockPatch:
    """Return a copy of a patch rooted at a newer revision."""
    return replace(patch, base_revision=revision)


def ensure_patch_id(patch: BlockPatch, document_id: str) -> BlockPatch:
    """Attach a document id when a patch was decoded without one."""
    return replace(patch, document_id=patch.document_id or document_id)


def new_block_id(existing: Sequence[str]) -> str:
    """Generate a block id that is absent from ``existing``."""
    taken = set(existing)
    candidate = new_id()
    while candidate in taken:
        candidate = new_id()
    return candidate
