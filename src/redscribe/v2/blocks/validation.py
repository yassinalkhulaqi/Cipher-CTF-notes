"""Structural validation for block documents and patches."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.blocks.constants import (
    MAX_ALT_LENGTH,
    MAX_BLOCKS,
    MAX_CELL_LENGTH,
    MAX_DOCUMENTS,
    MAX_HEADING_LEVEL,
    MAX_ITEM_LENGTH,
    MAX_ITEMS,
    MAX_LANGUAGE_LENGTH,
    MAX_MENTION_TARGET_LENGTH,
    MAX_PATCH_OPS,
    MAX_SOURCE_LENGTH,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    MAX_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
    MIN_HEADING_LEVEL,
)
from redscribe.v2.blocks.diff import BlockPatch
from redscribe.v2.blocks.model import Block, BlockDocument
from redscribe.v2.blocks.types import BlockType, IssueSeverity

_UNSAFE_SOURCE_RE = re.compile(r"^(?:javascript|data|vbscript):", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation finding with an optional block location."""

    severity: IssueSeverity
    code: str
    message: str
    block_id: str = ""
    field: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "block_id": self.block_id,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The full result of validating a document or patch."""

    target: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.has_errors

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity is IssueSeverity.WARNING for issue in self.issues)

    def count(self, severity: IssueSeverity) -> int:
        """Return the number of issues at one severity."""
        return sum(1 for issue in self.issues if issue.severity is severity)

    def for_block(self, block_id: str) -> tuple[ValidationIssue, ...]:
        """Return issues attached to one block."""
        return tuple(issue for issue in self.issues if issue.block_id == block_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "ok": self.ok,
            "errors": self.count(IssueSeverity.ERROR),
            "warnings": self.count(IssueSeverity.WARNING),
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _issue(
    severity: IssueSeverity,
    code: str,
    message: str,
    block: Block | None = None,
    field: str = "",
) -> ValidationIssue:
    return ValidationIssue(severity, code, message, block.id if block else "", field)


def _length_checks(
    block: Block,
    issues: list[ValidationIssue],
) -> None:
    if len(block.text) > MAX_TEXT_LENGTH:
        issues.append(
            _issue(IssueSeverity.ERROR, "text_too_long", "Block text is too long", block, "text")
        )
    if _CONTROL_RE.search(block.text):
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "control_characters",
                "Block text contains control characters",
                block,
                "text",
            )
        )
    if len(block.language) > MAX_LANGUAGE_LENGTH:
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "language_too_long",
                "Code language is too long",
                block,
                "language",
            )
        )
    if len(block.alt) > MAX_ALT_LENGTH:
        issues.append(
            _issue(IssueSeverity.ERROR, "alt_too_long", "Image alt text is too long", block, "alt")
        )
    if len(block.source) > MAX_SOURCE_LENGTH:
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "source_too_long",
                "Image source is too long",
                block,
                "source",
            )
        )


def validate_block(block: Block) -> ValidationReport:
    """Validate one block and return its issues."""
    issues: list[ValidationIssue] = []
    _length_checks(block, issues)

    if block.type is BlockType.HEADING:
        if not MIN_HEADING_LEVEL <= block.level <= MAX_HEADING_LEVEL:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "invalid_heading_level",
                    f"Heading level must be {MIN_HEADING_LEVEL}-{MAX_HEADING_LEVEL}",
                    block,
                    "level",
                )
            )
        if not block.text.strip():
            issues.append(
                _issue(
                    IssueSeverity.WARNING,
                    "empty_heading",
                    "Heading has no text",
                    block,
                    "text",
                )
            )
    elif block.type is BlockType.CODE:
        if not block.text.strip():
            issues.append(
                _issue(
                    IssueSeverity.WARNING,
                    "empty_code",
                    "Code block is empty",
                    block,
                    "text",
                )
            )
        if any(char in block.language for char in ("\n", " ", ")")):
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "invalid_language",
                    "Code language must be a simple identifier",
                    block,
                    "language",
                )
            )
    elif block.type is BlockType.LIST:
        if not block.items:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "empty_list",
                    "List must contain at least one item",
                    block,
                    "items",
                )
            )
        if len(block.items) > MAX_ITEMS:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "too_many_items",
                    f"List has more than {MAX_ITEMS} items",
                    block,
                    "items",
                )
            )
        for index, item in enumerate(block.items):
            if len(item) > MAX_ITEM_LENGTH:
                issues.append(
                    _issue(
                        IssueSeverity.ERROR,
                        "item_too_long",
                        f"List item {index + 1} is too long",
                        block,
                        "items",
                    )
                )
            if not item.strip():
                issues.append(
                    _issue(
                        IssueSeverity.WARNING,
                        "empty_list_item",
                        f"List item {index + 1} is empty",
                        block,
                        "items",
                    )
                )
        if block.style.value == "tasks" and len(block.checked) != len(block.items):
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "checkbox_mismatch",
                    "Task list needs one checkbox per item",
                    block,
                    "checked",
                )
            )
    elif block.type is BlockType.TABLE:
        if not block.headers:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "empty_table",
                    "Table needs at least one header",
                    block,
                    "headers",
                )
            )
        if len(block.headers) > MAX_TABLE_COLUMNS:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "too_many_columns",
                    f"Table has more than {MAX_TABLE_COLUMNS} columns",
                    block,
                    "headers",
                )
            )
        if len(block.rows) > MAX_TABLE_ROWS:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "too_many_rows",
                    f"Table has more than {MAX_TABLE_ROWS} rows",
                    block,
                    "rows",
                )
            )
        for index, row in enumerate(block.rows):
            if len(row) != len(block.headers):
                issues.append(
                    _issue(
                        IssueSeverity.ERROR,
                        "ragged_table",
                        f"Table row {index + 1} has {len(row)} of {len(block.headers)} cells",
                        block,
                        "rows",
                    )
                )
            for cell in row:
                if len(cell) > MAX_CELL_LENGTH:
                    issues.append(
                        _issue(
                            IssueSeverity.ERROR,
                            "cell_too_long",
                            f"Table cell in row {index + 1} is too long",
                            block,
                            "rows",
                        )
                    )
    elif block.type is BlockType.IMAGE:
        if not block.source:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "missing_source",
                    "Image placeholder needs a source",
                    block,
                    "source",
                )
            )
        elif _UNSAFE_SOURCE_RE.match(block.source):
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "unsafe_source",
                    "Image source uses an unsafe scheme",
                    block,
                    "source",
                )
            )
        if not block.alt.strip():
            issues.append(
                _issue(
                    IssueSeverity.WARNING,
                    "missing_alt",
                    "Image placeholder has no alt text",
                    block,
                    "alt",
                )
            )
    elif block.type is BlockType.PARAGRAPH and not block.text.strip():
        issues.append(
            _issue(
                IssueSeverity.INFO,
                "empty_paragraph",
                "Empty paragraph will render as a spacer",
                block,
                "text",
            )
        )

    seen_mentions: set[tuple[str, str]] = set()
    for mention in block.mentions:
        key = (mention.kind.value, mention.target)
        if key in seen_mentions:
            issues.append(
                _issue(
                    IssueSeverity.WARNING,
                    "duplicate_mention",
                    f"Duplicate mention of {mention.target}",
                    block,
                    "mentions",
                )
            )
        seen_mentions.add(key)
        if len(mention.target) > MAX_MENTION_TARGET_LENGTH:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "mention_target_too_long",
                    "Mention target is too long",
                    block,
                    "mentions",
                )
            )
        if mention.end > len(block.text) or mention.end <= mention.start:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "mention_offsets",
                    "Mention offsets are outside the block text",
                    block,
                    "mentions",
                )
            )
    return ValidationReport(block.id, tuple(issues))


def validate_document(document: BlockDocument) -> ValidationReport:
    """Validate document-level rules and every contained block."""
    issues: list[ValidationIssue] = []
    if not document.id.strip():
        issues.append(_issue(IssueSeverity.ERROR, "missing_id", "Document id is required"))
    if len(document.title) > MAX_TITLE_LENGTH:
        issues.append(
            _issue(
                IssueSeverity.ERROR, "title_too_long", "Document title is too long", None, "title"
            )
        )
    if not document.blocks:
        issues.append(
            _issue(
                IssueSeverity.ERROR, "no_blocks", "Document must contain a block", None, "blocks"
            )
        )
    if len(document.blocks) > MAX_BLOCKS:
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "too_many_blocks",
                f"Document has more than {MAX_BLOCKS} blocks",
                None,
                "blocks",
            )
        )
    if document.revision < 0:
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "negative_revision",
                "Revision cannot be negative",
                None,
                "revision",
            )
        )
    seen: set[str] = set()
    for block in document.blocks:
        if block.id in seen:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "duplicate_block_id",
                    f"Duplicate block id {block.id}",
                    block,
                    "id",
                )
            )
        seen.add(block.id)
        issues.extend(validate_block(block).issues)
    return ValidationReport(document.id, tuple(issues))


def validate_patch(patch: BlockPatch) -> ValidationReport:
    """Validate patch geometry before it reaches the store."""
    issues: list[ValidationIssue] = []
    if not patch.document_id:
        issues.append(
            _issue(IssueSeverity.ERROR, "missing_document_id", "Patch needs a document id")
        )
    if patch.base_revision < 0:
        issues.append(
            _issue(IssueSeverity.ERROR, "negative_revision", "Patch base revision is negative")
        )
    if len(patch.entries) > MAX_PATCH_OPS:
        issues.append(
            _issue(
                IssueSeverity.ERROR,
                "too_many_operations",
                f"Patch has more than {MAX_PATCH_OPS} operations",
            )
        )
    for index, entry in enumerate(patch.entries):
        if not entry.block_id:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "missing_block_id",
                    f"Operation {index + 1} has no block id",
                )
            )
        if entry.operation.value in ("insert", "update") and entry.block is None:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "missing_block",
                    f"Operation {index + 1} has no block payload",
                )
            )
    return ValidationReport(patch.document_id, tuple(issues))


def validate_documents(documents: Sequence[BlockDocument]) -> list[ValidationReport]:
    """Validate a collection and enforce the global document cap."""
    reports = [validate_document(document) for document in documents]
    if len(documents) > MAX_DOCUMENTS:
        reports.append(
            ValidationReport(
                "collection",
                (
                    _issue(
                        IssueSeverity.ERROR,
                        "too_many_documents",
                        f"Collection has more than {MAX_DOCUMENTS} documents",
                    ),
                ),
            )
        )
    return reports


def issues_from_payload(payload: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
    """Decode serialized issues, ignoring unknown fields."""
    issues: list[ValidationIssue] = []
    for value in payload.get("issues", ()):
        if not isinstance(value, Mapping):
            continue
        try:
            severity = IssueSeverity(str(value.get("severity", "info")))
        except ValueError:
            severity = IssueSeverity.INFO
        issues.append(
            ValidationIssue(
                severity=severity,
                code=str(value.get("code", "")),
                message=str(value.get("message", "")),
                block_id=str(value.get("block_id", "")),
                field=str(value.get("field", "")),
            )
        )
    return tuple(issues)
