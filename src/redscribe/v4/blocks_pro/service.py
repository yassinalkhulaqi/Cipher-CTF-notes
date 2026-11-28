"""Domain services for the v4 block editor: codec, diff, autosave, validation.

All services are deterministic when given an injected identifier factory or
clock. They operate only on the immutable values from
:mod:`redscribe.v4.blocks_pro.types` and never perform I/O.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from redscribe.v4.blocks_pro.types import (
    KNOWN_LANGUAGES,
    LEGAL_HEADING_LEVELS,
    LIST_STYLES,
    MAX_BLOCKS,
    Block,
    BlockDocument,
    BlockKind,
    BlockOp,
    EditOperation,
    InlineMark,
    ValidationIssue,
    ValidationSeverity,
)
from redscribe.v4.contracts import new_entity_id

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")
ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")
BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
DIVIDER_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
ANNOTATION_RE = re.compile(r"^<!--\s*block:([A-Za-z0-9][A-Za-z0-9_-]{0,79})\s*-->$")
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
LIST_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MAX_DIFF_CELLS = 500_000


class CodecError(ValueError):
    """Raised when markdown cannot be decoded into a document."""


class DiffError(ValueError):
    """Raised when a diff cannot be computed or replayed."""


class SnapshotError(ValueError):
    """Raised when a snapshot is malformed, stale, or tampered with."""


class DocumentInvalidError(ValueError):
    """Raised when a document violates structural invariants."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, accepting a trailing ``Z``."""
    if not value:
        raise ValueError("empty timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class MarkdownCodec:
    """Lossless encoder/decoder between documents and annotated markdown."""

    def __init__(
        self,
        annotate_ids: bool = True,
        id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.annotate_ids = annotate_ids
        self.id_factory = id_factory

    def with_annotations(self, annotate_ids: bool) -> MarkdownCodec:
        return MarkdownCodec(annotate_ids=annotate_ids, id_factory=self.id_factory)

    def encode(self, document: BlockDocument) -> str:
        """Serialize a document with stable block ordering and annotations."""
        sections = [f"# {document.title}"]
        for block in document.blocks:
            sections.append(self.encode_block(block))
        return "\n\n".join(sections).rstrip() + "\n"

    def encode_block(self, block: Block) -> str:
        """Serialize one block, optionally prefixed with its identity marker."""
        body = self._render(block)
        if self.annotate_ids:
            return f"<!-- block:{block.id} -->\n{body}"
        return body

    def _render(self, block: Block) -> str:
        if block.kind is BlockKind.HEADING:
            return f"{'#' * block.level} {block.text}"
        if block.kind is BlockKind.DIVIDER:
            return "---"
        if block.kind is BlockKind.CODE:
            language = block.language or "text"
            return f"```{language}\n{block.text}\n```"
        if block.kind is BlockKind.QUOTE:
            lines = block.text.split("\n") or [""]
            return "\n".join(f"> {line}" for line in lines)
        if block.kind is BlockKind.LIST:
            style = block.attr("style", "bullet")
            if style == "ordered":
                return "\n".join(f"{index + 1}. {item}" for index, item in enumerate(block.items))
            return "\n".join(f"- {item}" for item in block.items)
        if block.kind is BlockKind.TABLE:
            columns = [part.strip() for part in block.attr("header", "").split("|") if part.strip()]
            header = "| " + " | ".join(columns) + " |" if columns else "| |"
            separator = "| " + " | ".join("---" for _ in columns) + " |" if columns else "| --- |"
            rows = [
                "| " + " | ".join(part.strip() for part in row.split("|")) + " |"
                for row in block.items
            ]
            return "\n".join([header, separator, *rows])
        return block.text

    def decode(self, markdown: str) -> BlockDocument:
        """Parse annotated markdown into a document."""
        if not isinstance(markdown, str):
            raise CodecError("markdown must be a string")
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        title = ""
        if lines and lines[0].startswith("# "):
            title = lines[0][2:].strip()
            lines = lines[1:]
        blocks = self._decode_blocks(lines)
        return BlockDocument(
            id=new_entity_id(),
            title=title,
            blocks=tuple(blocks),
        )

    def decode_with_id(self, markdown: str, document_id: str) -> BlockDocument:
        """Decode markdown while preserving an externally supplied document id."""
        document = self.decode(markdown)
        return BlockDocument(document_id, document.title, document.blocks)

    def round_trip(self, document: BlockDocument) -> BlockDocument:
        """Encode and decode a document, preserving ids via annotations."""
        codec = self.with_annotations(True)
        return codec.decode_with_id(codec.encode(document), document.id)

    def _decode_blocks(self, lines: Sequence[str]) -> list[Block]:
        blocks: list[Block] = []
        pending_id: str | None = None
        index = 0
        total = len(lines)
        while index < total:
            line = lines[index]
            if not line.strip():
                index += 1
                continue
            annotation = ANNOTATION_RE.match(line.strip())
            if annotation is not None:
                pending_id = annotation.group(1)
                index += 1
                continue
            parsed, consumed = self._parse_block(lines, index)
            if parsed is None or consumed <= 0:
                raise CodecError(f"unrecognized markdown at line {index + 1}")
            block_id = pending_id or self.id_factory()
            pending_id = None
            blocks.append(
                Block(
                    id=block_id,
                    kind=parsed.kind,
                    text=parsed.text,
                    level=parsed.level,
                    language=parsed.language,
                    items=parsed.items,
                    attrs=parsed.attrs,
                )
            )
            index += consumed
        return blocks

    def _parse_block(self, lines: Sequence[str], start: int) -> tuple[Block | None, int]:
        line = lines[start]
        heading = HEADING_RE.match(line)
        if heading is not None:
            return (
                Block("pending", BlockKind.HEADING, heading.group(2), len(heading.group(1))),
                1,
            )
        if DIVIDER_RE.match(line.strip()):
            return Block("pending", BlockKind.DIVIDER), 1
        fence = FENCE_RE.match(line.strip())
        if fence is not None:
            return self._parse_fence(lines, start, fence.group(1) or "text")
        if line.startswith("> "):
            return self._parse_quote(lines, start)
        if BULLET_RE.match(line) or ORDERED_RE.match(line):
            return self._parse_list(lines, start)
        if line.strip().startswith("|"):
            return self._parse_table(lines, start)
        return self._parse_paragraph(lines, start)

    def _parse_fence(
        self,
        lines: Sequence[str],
        start: int,
        language: str,
    ) -> tuple[Block | None, int]:
        body: list[str] = []
        cursor = start + 1
        while cursor < len(lines) and lines[cursor].strip() != "```":
            body.append(lines[cursor])
            cursor += 1
        if cursor >= len(lines):
            raise CodecError("unterminated fenced code block")
        return Block(
            "pending",
            BlockKind.CODE,
            "\n".join(body),
            language=language,
        ), cursor - start + 1

    def _parse_quote(self, lines: Sequence[str], start: int) -> tuple[Block, int]:
        body: list[str] = []
        cursor = start
        while cursor < len(lines) and lines[cursor].startswith("> "):
            body.append(lines[cursor][2:])
            cursor += 1
        return Block("pending", BlockKind.QUOTE, "\n".join(body)), cursor - start

    def _parse_list(self, lines: Sequence[str], start: int) -> tuple[Block, int]:
        items: list[str] = []
        style = "bullet"
        cursor = start
        while cursor < len(lines):
            current = lines[cursor]
            ordered = ORDERED_RE.match(current)
            bullet = BULLET_RE.match(current)
            if ordered is not None:
                style = "ordered"
                items.append(ordered.group(1))
            elif bullet is not None:
                value = bullet.group(1)
                task = LIST_TASK_RE.match(value)
                if task is not None:
                    style = "task"
                    marker = "x" if task.group(1).lower() == "x" else " "
                    items.append(f"[{marker}] {task.group(2)}")
                else:
                    items.append(value)
            else:
                break
            cursor += 1
        return (
            Block(
                "pending",
                BlockKind.LIST,
                items=tuple(items),
                attrs=(("style", style),),
            ),
            cursor - start,
        )

    def _parse_table(self, lines: Sequence[str], start: int) -> tuple[Block, int]:
        table_lines: list[str] = []
        cursor = start
        while cursor < len(lines) and lines[cursor].strip().startswith("|"):
            table_lines.append(lines[cursor].strip())
            cursor += 1
        if len(table_lines) < 2 or not TABLE_SEPARATOR_RE.match(table_lines[1]):
            raise CodecError("table must contain a header and separator row")
        header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
        rows: list[str] = []
        for row in table_lines[2:]:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            rows.append("|".join(cells))
        return (
            Block(
                "pending",
                BlockKind.TABLE,
                items=tuple(rows),
                attrs=(("header", "|".join(header)),),
            ),
            cursor - start,
        )

    def _parse_paragraph(self, lines: Sequence[str], start: int) -> tuple[Block, int]:
        body: list[str] = []
        cursor = start
        while cursor < len(lines) and lines[cursor].strip():
            current = lines[cursor]
            if cursor > start and (
                HEADING_RE.match(current)
                or DIVIDER_RE.match(current.strip())
                or FENCE_RE.match(current.strip())
                or BULLET_RE.match(current)
                or ORDERED_RE.match(current)
                or current.startswith("> ")
                or current.strip().startswith("|")
            ):
                break
            body.append(current)
            cursor += 1
        return Block("pending", BlockKind.PARAGRAPH, "\n".join(body)), cursor - start


def apply_mark(text: str, mark: InlineMark | str, target: str, href: str = "") -> str:
    """Apply an inline markdown mark to a selected substring."""
    resolved = mark if isinstance(mark, InlineMark) else InlineMark.parse(mark)
    return resolved.apply(text, target, href)


def strip_markdown(text: str) -> str:
    """Remove inline markdown decorations for plain-text search."""
    without_links = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), text)
    for token in ("**", "`", "*"):
        without_links = without_links.replace(token, "")
    return without_links


def markdown_summary(markdown: str) -> dict[str, int]:
    """Count lines, headings, fences, and blank lines in markdown text."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    return {
        "lines": len(lines),
        "blank": sum(1 for line in lines if not line.strip()),
        "headings": sum(1 for line in lines if HEADING_RE.match(line)),
        "fences": sum(1 for line in lines if FENCE_RE.match(line.strip())),
    }


@dataclass(frozen=True, slots=True)
class LineDelta:
    """One line-level change produced by :meth:`BlockDiff.line_diff`."""

    op: str
    text: str
    left_index: int
    right_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "op": self.op,
            "text": self.text,
            "left_index": self.left_index,
            "right_index": self.right_index,
        }


def _lcs_indices(left: Sequence[object], right: Sequence[object]) -> tuple[tuple[int, int], ...]:
    rows = len(left)
    columns = len(right)
    if rows * columns > MAX_DIFF_CELLS:
        raise DiffError("document pair is too large for a full diff")
    table = [[0] * (columns + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(columns - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if left[i] == right[j]
                else max(table[i + 1][j], table[i][j + 1])
            )
    pairs: list[tuple[int, int]] = []
    i = j = 0
    while i < rows and j < columns:
        if left[i] == right[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return tuple(pairs)


class BlockDiff:
    """LCS-based block and line differ with replay support."""

    def __init__(self, ignore_level: bool = False) -> None:
        self.ignore_level = ignore_level

    def _key(self, block: Block) -> tuple[str, str]:
        payload = block.to_dict()
        if self.ignore_level and block.kind is BlockKind.HEADING:
            payload["level"] = 1
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return block.id, hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _require_unique(document: BlockDocument) -> None:
        seen: set[str] = set()
        for block in document.blocks:
            if block.id in seen:
                raise DiffError(f"duplicate block id in document: {block.id}")
            seen.add(block.id)

    def compare(
        self,
        left: BlockDocument,
        right: BlockDocument,
    ) -> tuple[EditOperation, ...]:
        """Return the minimal ordered operation list transforming left into right."""
        self._require_unique(left)
        self._require_unique(right)
        left_ids = [block.id for block in left.blocks]
        right_ids = [block.id for block in right.blocks]
        matched = _lcs_indices(left_ids, right_ids)
        matched_left = {pair[0] for pair in matched}
        matched_right = {pair[1] for pair in matched}
        matched_right_left = {right_index: left_index for left_index, right_index in matched}
        left_by_id = {block.id: (index, block) for index, block in enumerate(left.blocks)}
        right_by_id = {block.id: (index, block) for index, block in enumerate(right.blocks)}
        operations: list[EditOperation] = []
        for index, block in enumerate(right.blocks):
            if index in matched_right:
                previous_index = matched_right_left[index]
                if self._key(left.blocks[previous_index]) != self._key(block):
                    operations.append(
                        EditOperation(BlockOp.UPDATE, block.id, index=index, block=block)
                    )
                continue
            previous = left_by_id.get(block.id)
            if previous is None:
                operations.append(EditOperation(BlockOp.INSERT, block.id, index=index, block=block))
            else:
                if self._key(previous[1]) != self._key(block):
                    operations.append(
                        EditOperation(BlockOp.UPDATE, block.id, index=index, block=block)
                    )
                operations.append(
                    EditOperation(
                        BlockOp.MOVE,
                        block.id,
                        index=previous[0],
                        target_index=index,
                    )
                )
        for index, block in enumerate(left.blocks):
            if index not in matched_left and block.id not in right_by_id:
                operations.append(EditOperation(BlockOp.DELETE, block.id, index=index))
        rank = {
            BlockOp.INSERT: 0,
            BlockOp.UPDATE: 1,
            BlockOp.MOVE: 2,
            BlockOp.DELETE: 3,
        }
        operations.sort(
            key=lambda item: (
                item.target_index if item.target_index is not None else item.index,
                rank[item.op],
                item.block_id,
            )
        )
        return tuple(operations)

    def apply(
        self,
        document: BlockDocument,
        operations: Sequence[EditOperation],
    ) -> BlockDocument:
        """Replay operations against a document and return the result."""
        blocks = list(document.blocks)
        for op in sorted(
            (item for item in operations if item.op is BlockOp.DELETE),
            key=lambda item: item.index,
            reverse=True,
        ):
            if op.index >= len(blocks) or blocks[op.index].id != op.block_id:
                raise DiffError(f"cannot delete {op.block_id} at index {op.index}")
            del blocks[op.index]
        for op in sorted(
            (item for item in operations if item.op is BlockOp.INSERT),
            key=lambda item: item.index,
        ):
            if op.block is None:
                raise DiffError("insert operation is missing its block")
            position = min(op.index, len(blocks))
            blocks.insert(position, op.block)
        for op in (item for item in operations if item.op is BlockOp.UPDATE):
            if op.block is None:
                raise DiffError("update operation is missing its block")
            found = False
            for index, block in enumerate(blocks):
                if block.id == op.block_id:
                    blocks[index] = op.block
                    found = True
                    break
            if not found:
                raise DiffError(f"cannot update missing block {op.block_id}")
        for op in sorted(
            (item for item in operations if item.op is BlockOp.MOVE),
            key=lambda item: item.target_index or 0,
        ):
            positions = [index for index, block in enumerate(blocks) if block.id == op.block_id]
            if not positions:
                raise DiffError(f"cannot move missing block {op.block_id}")
            current = positions[0]
            moved = blocks.pop(current)
            target = min(op.target_index or 0, len(blocks))
            blocks.insert(target, moved)
        return BlockDocument(document.id, document.title, tuple(blocks))

    def line_diff(self, left: str, right: str) -> tuple[LineDelta, ...]:
        """Produce a line-level add/remove diff using the same LCS engine."""
        left_lines = left.replace("\r\n", "\n").split("\n")
        right_lines = right.replace("\r\n", "\n").split("\n")
        matched = _lcs_indices(left_lines, right_lines)
        matched_left = {pair[0] for pair in matched}
        matched_right = {pair[1] for pair in matched}
        deltas: list[LineDelta] = []
        for index, line in enumerate(left_lines):
            if index not in matched_left:
                deltas.append(LineDelta("remove", line, index, -1))
        for index, line in enumerate(right_lines):
            if index not in matched_right:
                deltas.append(LineDelta("add", line, -1, index))
        return tuple(deltas)

    def summary(self, operations: Sequence[EditOperation]) -> dict[str, int]:
        """Count operations by kind."""
        result = {kind.value: 0 for kind in BlockOp}
        for op in operations:
            result[op.op.value] += 1
        return result


@dataclass(frozen=True, slots=True)
class Snapshot:
    """An immutable autosave point with a content checksum."""

    id: str
    document_id: str
    document: BlockDocument
    created_at: str
    checksum: str
    reason: str
    revision: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "document": self.document.to_dict(),
            "created_at": self.created_at,
            "checksum": self.checksum,
            "reason": self.reason,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Snapshot:
        raw_document = data.get("document")
        if not isinstance(raw_document, dict):
            raise SnapshotError("snapshot document must be a mapping")
        return cls(
            id=str(data.get("id", "")),
            document_id=str(data.get("document_id", "")),
            document=BlockDocument.from_dict(raw_document),
            created_at=str(data.get("created_at", "")),
            checksum=str(data.get("checksum", "")),
            reason=str(data.get("reason", "")),
            revision=int(str(data.get("revision", 0))),
        )


class AutosaveManager:
    """Create, verify, prune, and restore document snapshots."""

    def __init__(
        self,
        id_factory: Callable[[], str] = new_entity_id,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.id_factory = id_factory
        self.clock = clock
        self._snapshots: dict[str, list[Snapshot]] = {}

    def create(self, document: BlockDocument, reason: str = "manual") -> Snapshot:
        cleaned = reason.strip()
        if not cleaned or len(cleaned) > 60:
            raise SnapshotError("reason must be 1-60 characters")
        revision = 1 + max(
            (item.revision for item in self._snapshots.get(document.id, [])),
            default=0,
        )
        snapshot = Snapshot(
            id=self.id_factory(),
            document_id=document.id,
            document=document,
            created_at=self.clock(),
            checksum=document.checksum(),
            reason=cleaned,
            revision=revision,
        )
        self._snapshots.setdefault(document.id, []).append(snapshot)
        return snapshot

    def verify(self, snapshot: Snapshot) -> bool:
        return snapshot.checksum == snapshot.document.checksum()

    def restore(self, snapshot: Snapshot, expected_checksum: str = "") -> BlockDocument:
        if not self.verify(snapshot):
            raise SnapshotError("snapshot checksum does not match its document")
        if expected_checksum and expected_checksum != snapshot.checksum:
            raise SnapshotError("snapshot is stale")
        return snapshot.document

    def prune(
        self,
        snapshots: Sequence[Snapshot],
        max_count: int = 5,
        max_age_hours: float = 72.0,
        now: str | None = None,
    ) -> tuple[list[Snapshot], list[Snapshot]]:
        """Return kept and removed snapshots by age then count."""
        if max_count < 1:
            raise SnapshotError("max_count must be >= 1")
        if max_age_hours < 0:
            raise SnapshotError("max_age_hours must be >= 0")
        reference = parse_timestamp(now or self.clock())
        cutoff = reference - timedelta(hours=max_age_hours)
        recent: list[Snapshot] = []
        removed: list[Snapshot] = []
        for snapshot in snapshots:
            try:
                created = parse_timestamp(snapshot.created_at)
            except ValueError:
                removed.append(snapshot)
                continue
            if created < cutoff:
                removed.append(snapshot)
            else:
                recent.append(snapshot)
        if len(recent) > max_count:
            removed.extend(recent[: len(recent) - max_count])
            recent = recent[len(recent) - max_count :]
        return recent, removed

    def prune_all(
        self,
        max_count: int = 5,
        max_age_hours: float = 72.0,
        now: str | None = None,
    ) -> tuple[list[Snapshot], list[Snapshot]]:
        """Prune every tracked document and return all kept/removed snapshots."""
        kept: list[Snapshot] = []
        removed: list[Snapshot] = []
        for document_id in sorted(self._snapshots):
            recent, dropped = self.prune(
                self._snapshots[document_id], max_count, max_age_hours, now
            )
            self._snapshots[document_id] = recent
            kept.extend(recent)
            removed.extend(dropped)
        return kept, removed

    def list_for(self, document_id: str) -> tuple[Snapshot, ...]:
        return tuple(self._snapshots.get(document_id, ()))

    def latest(self, document_id: str) -> Snapshot | None:
        items = self._snapshots.get(document_id, ())
        return items[-1] if items else None

    def remove(self, snapshot_id: str) -> bool:
        for document_id, items in list(self._snapshots.items()):
            remaining = [item for item in items if item.id != snapshot_id]
            if len(remaining) != len(items):
                self._snapshots[document_id] = remaining
                return True
        return False

    def clear(self, document_id: str | None = None) -> None:
        if document_id is None:
            self._snapshots.clear()
        else:
            self._snapshots.pop(document_id, None)

    def count(self) -> int:
        return sum(len(items) for items in self._snapshots.values())


class BlockValidator:
    """Check structural invariants across documents and operations."""

    def __init__(self, max_heading_level: int = 6) -> None:
        if max_heading_level not in LEGAL_HEADING_LEVELS:
            raise ValueError("max_heading_level must be a legal heading level")
        self.max_heading_level = max_heading_level

    def validate(self, document: BlockDocument) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        if not document.title.strip():
            issues.append(ValidationIssue("title", "title.empty", "title must not be blank"))
        if len(document.blocks) > MAX_BLOCKS:
            issues.append(ValidationIssue("blocks", "blocks.too_many", "too many blocks"))
        seen: set[str] = set()
        for index, block in enumerate(document.blocks):
            path = f"blocks[{index}]"
            if block.id in seen:
                issues.append(
                    ValidationIssue(f"{path}.id", "block.duplicate_id", "duplicate block id")
                )
            seen.add(block.id)
            issues.extend(self._validate_block(block, path))
        return tuple(issues)

    def _validate_block(self, block: Block, path: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if block.kind is BlockKind.HEADING:
            if block.level > self.max_heading_level:
                issues.append(
                    ValidationIssue(f"{path}.level", "heading.level", "heading level too deep")
                )
            if not block.text.strip():
                issues.append(
                    ValidationIssue(f"{path}.text", "heading.empty", "heading must not be blank")
                )
        if block.kind is BlockKind.CODE and not block.language:
            issues.append(
                ValidationIssue(
                    f"{path}.language",
                    "code.language",
                    "code block should declare a language",
                    ValidationSeverity.WARNING,
                )
            )
        if block.kind is BlockKind.CODE and block.language not in KNOWN_LANGUAGES:
            issues.append(
                ValidationIssue(
                    f"{path}.language",
                    "code.language_unknown",
                    "language is not in the known set",
                    ValidationSeverity.WARNING,
                )
            )
        if block.kind is BlockKind.LIST:
            if not block.items:
                issues.append(
                    ValidationIssue(f"{path}.items", "list.empty", "list must have items")
                )
            style = block.attr("style", "bullet")
            if style not in LIST_STYLES:
                issues.append(ValidationIssue(f"{path}.style", "list.style", "unknown list style"))
        if block.kind is BlockKind.TABLE:
            columns = [part for part in block.attr("header", "").split("|") if part]
            if not columns:
                issues.append(
                    ValidationIssue(f"{path}.header", "table.header", "table needs a header row")
                )
            for row_index, row in enumerate(block.items):
                if len(row.split("|")) != len(columns):
                    issues.append(
                        ValidationIssue(
                            f"{path}.items[{row_index}]",
                            "table.width",
                            "row width does not match header",
                        )
                    )
        if block.kind is BlockKind.DIVIDER and (block.text or block.items):
            issues.append(
                ValidationIssue(f"{path}.text", "divider.content", "divider must be empty")
            )
        if block.kind is BlockKind.PARAGRAPH and "\n\n" in block.text:
            issues.append(
                ValidationIssue(f"{path}.text", "paragraph.break", "paragraph has a blank line")
            )
        return issues

    def is_valid(self, document: BlockDocument) -> bool:
        return all(
            issue.severity is not ValidationSeverity.ERROR for issue in self.validate(document)
        )

    def require_valid(self, document: BlockDocument) -> None:
        errors = [
            issue for issue in self.validate(document) if issue.severity is ValidationSeverity.ERROR
        ]
        if errors:
            raise DocumentInvalidError(errors[0].message)

    def validate_operation(
        self,
        operation: EditOperation,
        document: BlockDocument,
    ) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        size = len(document.blocks)
        if operation.op in {BlockOp.INSERT, BlockOp.UPDATE} and operation.block is None:
            issues.append(
                ValidationIssue("operation.block", "operation.block_missing", "block is required")
            )
        if operation.op is BlockOp.INSERT:
            if operation.index > size:
                issues.append(
                    ValidationIssue(
                        "operation.index", "operation.index", "insert index out of range"
                    )
                )
            if document.get(operation.block_id) is not None:
                issues.append(
                    ValidationIssue("operation.id", "operation.duplicate", "block id already used")
                )
        if operation.op is BlockOp.DELETE and document.get(operation.block_id) is None:
            issues.append(
                ValidationIssue("operation.id", "operation.missing", "block id does not exist")
            )
        if operation.op is BlockOp.UPDATE and document.get(operation.block_id) is None:
            issues.append(
                ValidationIssue("operation.id", "operation.missing", "block id does not exist")
            )
        if operation.op is BlockOp.MOVE:
            if document.get(operation.block_id) is None:
                issues.append(
                    ValidationIssue("operation.id", "operation.missing", "block id does not exist")
                )
            if operation.target_index is not None and operation.target_index > size:
                issues.append(
                    ValidationIssue(
                        "operation.target", "operation.target", "target index out of range"
                    )
                )
        return tuple(issues)

    def validate_operations(
        self,
        operations: Sequence[EditOperation],
        document: BlockDocument,
    ) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        for position, operation in enumerate(operations):
            for issue in self.validate_operation(operation, document):
                issues.append(
                    ValidationIssue(
                        f"operations[{position}].{issue.path}", issue.code, issue.message
                    )
                )
        touched: set[str] = set()
        for operation in operations:
            if operation.op in {BlockOp.DELETE, BlockOp.MOVE, BlockOp.UPDATE}:
                if operation.block_id in touched:
                    issues.append(
                        ValidationIssue(
                            "operations",
                            "operation.conflict",
                            "block targeted by more than one destructive operation",
                        )
                    )
                touched.add(operation.block_id)
        return tuple(issues)


__all__ = [
    "AutosaveManager",
    "BlockDiff",
    "BlockValidator",
    "CodecError",
    "DiffError",
    "DocumentInvalidError",
    "LineDelta",
    "MarkdownCodec",
    "Snapshot",
    "SnapshotError",
    "apply_mark",
    "markdown_summary",
    "parse_timestamp",
    "strip_markdown",
]
