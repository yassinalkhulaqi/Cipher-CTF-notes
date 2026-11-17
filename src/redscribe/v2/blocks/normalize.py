"""Normalization rules applied at every block-editor boundary."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from redscribe.v2.blocks.constants import (
    MAX_ALT_LENGTH,
    MAX_CELL_LENGTH,
    MAX_HEADING_LEVEL,
    MAX_ITEM_LENGTH,
    MAX_ITEMS,
    MAX_LANGUAGE_LENGTH,
    MAX_MENTIONS_PER_BLOCK,
    MAX_SOURCE_LENGTH,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    MAX_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
    MIN_HEADING_LEVEL,
)
from redscribe.v2.blocks.model import (
    Block,
    BlockDocument,
    Mention,
    make_block,
    new_id,
    valid_id,
)
from redscribe.v2.blocks.types import BlockType, CalloutTone, ListStyle

_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")
_WS_RUN = re.compile(r"[ \t]{2,}")


def normalize_text(value: str, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Normalize unicode, line endings, and whitespace without losing lines."""
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = "\n".join(_TRAILING_SPACES.sub("", line) for line in text.split("\n"))
    text = _WS_RUN.sub(" ", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()[:max_length]


def normalize_id(value: str, *, fallback_prefix: str = "blk") -> str:
    """Return a safe identifier, generating one for invalid values."""
    candidate = unicodedata.normalize("NFKC", value).strip()
    if valid_id(candidate):
        return candidate
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", candidate).strip("-")
    if valid_id(cleaned):
        return cleaned[:128]
    return new_id(fallback_prefix)


def normalize_items(items: Iterable[str]) -> tuple[str, ...]:
    """Trim and cap a list of item strings."""
    values: list[str] = []
    for item in items:
        cleaned = normalize_text(item, max_length=MAX_ITEM_LENGTH)
        if cleaned:
            values.append(cleaned)
        if len(values) >= MAX_ITEMS:
            break
    return tuple(values)


def normalize_table(
    headers: Iterable[str],
    rows: Iterable[Sequence[str]],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Normalize a rectangular table and pad short rows with empty cells."""
    header_values = normalize_items(headers)[:MAX_TABLE_COLUMNS]
    columns = len(header_values)
    normalized_rows: list[tuple[str, ...]] = []
    for row in rows:
        if len(normalized_rows) >= MAX_TABLE_ROWS:
            break
        cells = [
            normalize_text(cell, max_length=MAX_CELL_LENGTH)
            for cell in list(row)[:MAX_TABLE_COLUMNS]
        ]
        cells.extend([""] * (columns - len(cells)))
        normalized_rows.append(tuple(cells[:columns]))
    return header_values, tuple(normalized_rows)


def normalize_mentions(mentions: Iterable[Mention], block: Block) -> tuple[Mention, ...]:
    """Keep unique mentions whose offsets fit inside the block text."""
    seen: set[tuple[str, str]] = set()
    result: list[Mention] = []
    for mention in mentions:
        key = (mention.kind.value, mention.target)
        if key in seen or len(result) >= MAX_MENTIONS_PER_BLOCK:
            continue
        if not mention.target or not mention.label:
            continue
        if mention.start < 0 or mention.end > len(block.text) or mention.end <= mention.start:
            continue
        seen.add(key)
        result.append(replace(mention, block_id=block.id, start=mention.start, end=mention.end))
    return tuple(result)


def normalize_block(value: Block | Mapping[str, Any]) -> Block:
    """Return a canonical block from a block or partial mapping."""
    from redscribe.v2.blocks.mentions import extract_mentions

    block = value if isinstance(value, Block) else Block.from_dict(value)
    text = normalize_text(block.text)
    items = normalize_items(block.items)
    headers, rows = normalize_table(block.headers, block.rows)
    level = block.level
    if block.type is BlockType.HEADING:
        level = min(MAX_HEADING_LEVEL, max(MIN_HEADING_LEVEL, level))
    else:
        level = MIN_HEADING_LEVEL
    base = replace(
        block,
        id=normalize_id(block.id),
        text=text,
        level=level,
        language=normalize_text(block.language, max_length=MAX_LANGUAGE_LENGTH),
        items=items,
        checked=tuple((list(block.checked) + [False] * len(items))[: len(items)]),
        headers=headers,
        rows=rows,
        tone=block.tone if isinstance(block.tone, CalloutTone) else CalloutTone.INFO,
        style=block.style if isinstance(block.style, ListStyle) else ListStyle.BULLET,
        alt=normalize_text(block.alt, max_length=MAX_ALT_LENGTH),
        source=normalize_text(block.source, max_length=MAX_SOURCE_LENGTH),
        attrs={
            str(key): normalize_text(item, max_length=MAX_TEXT_LENGTH)
            for key, item in block.attrs.items()
        },
    )
    mentions = block.mentions or extract_mentions(text, block_id=base.id)
    return replace(base, mentions=normalize_mentions(mentions, base))


def normalize_blocks(blocks: Iterable[Block | Mapping[str, Any]]) -> tuple[Block, ...]:
    """Normalize a sequence and assign unique ids to duplicates."""
    normalized: list[Block] = []
    used: set[str] = set()
    for value in blocks:
        block = normalize_block(value)
        if block.id in used:
            block = replace(block, id=new_id())
        used.add(block.id)
        normalized.append(block)
    return tuple(normalized)


def normalize_document(
    value: BlockDocument | Mapping[str, Any],
    *,
    require_blocks: bool = True,
) -> BlockDocument:
    """Return a canonical document and preserve its revision counter."""
    document = value if isinstance(value, BlockDocument) else BlockDocument.from_dict(value)
    blocks = normalize_blocks(document.blocks)
    if not blocks and require_blocks:
        blocks = (make_block(),)
    tags = tuple(
        dict.fromkeys(
            tag.casefold()
            for tag in (normalize_text(item, max_length=120) for item in document.tags)
            if tag
        )
    )
    return replace(
        document,
        id=normalize_id(document.id, fallback_prefix="doc"),
        title=normalize_text(document.title, max_length=MAX_TITLE_LENGTH),
        blocks=blocks,
        tags=tags,
        metadata={
            str(key): normalize_text(item, max_length=MAX_TEXT_LENGTH)
            for key, item in document.metadata.items()
        },
    )


def normalize_payload(value: object) -> dict[str, Any]:
    """Coerce an arbitrary mapping-like payload into a plain dict."""
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}
