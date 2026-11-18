"""Markdown-like intermediate representation for structured blocks.

The IR is intentionally small and deterministic: each block occupies one
paragraph-sized chunk, and nested geometry (list items, table cells, code
fences) is expressed with plain Markdown markers. It is used for note storage,
copy/paste, and API round trips.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from redscribe.v2.blocks.constants import MAX_HEADING_LEVEL
from redscribe.v2.blocks.mentions import refresh_block_mentions
from redscribe.v2.blocks.model import Block, BlockDocument, make_block, make_document
from redscribe.v2.blocks.types import BlockType, CalloutTone, ListStyle

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_DIVIDER_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
_CALLOUT_RE = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_TASK_RE = re.compile(r"^[-*+]\s+\[([ xX])\]\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*([A-Za-z0-9_+#.-]*)\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$")
_ESCAPED_MARKER_RE = re.compile(r"^\\([-#*+>\[\]|`])")
_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")


def escape_cell(value: str) -> str:
    """Escape a table cell for the Markdown-like IR."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def unescape_cell(value: str) -> str:
    """Unescape a table cell read from the Markdown-like IR."""
    return value.replace("\\|", "|").replace("\\\\", "\\").strip()


def _escape_paragraph_line(line: str) -> str:
    if _HEADING_RE.match(line) or _DIVIDER_RE.match(line) or _BULLET_RE.match(line):
        return f"\\{line}"
    if _ORDERED_RE.match(line) or _QUOTE_RE.match(line) or _IMAGE_RE.match(line):
        return f"\\{line}"
    if _TASK_RE.match(line) or _FENCE_RE.match(line):
        return f"\\{line}"
    return line


def _unescape_paragraph_line(line: str) -> str:
    match = _ESCAPED_MARKER_RE.match(line)
    return line[1:] if match is not None else line


def serialize_block(block: Block) -> str:
    """Serialize one block to a Markdown-like string."""
    if block.type is BlockType.PARAGRAPH:
        lines = [_escape_paragraph_line(line) for line in block.text.split("\n")]
        return "\n".join(lines) or "(empty paragraph)"
    if block.type is BlockType.HEADING:
        return f"{'#' * block.level} {block.text}".rstrip()
    if block.type is BlockType.CODE:
        lang = block.language or "text"
        body = block.text.replace("\n\n", "\n")
        return f"```{lang}\n{body}\n```"
    if block.type is BlockType.QUOTE:
        return "\n".join(f"> {line}" if line else ">" for line in block.text.split("\n"))
    if block.type is BlockType.LIST:
        return "\n".join(_serialize_list_item(block, index) for index in range(len(block.items)))
    if block.type is BlockType.TABLE:
        return _serialize_table(block)
    if block.type is BlockType.CALLOUT:
        tone = block.tone.value.upper()
        payload = [f"> [!{tone}]"]
        payload.extend(f"> {line}" if line else ">" for line in block.text.split("\n"))
        return "\n".join(payload)
    if block.type is BlockType.DIVIDER:
        return "---"
    return f"![{block.alt}]({block.source})"


def _serialize_list_item(block: Block, index: int) -> str:
    item = block.items[index]
    checked = block.checked[index] if index < len(block.checked) else False
    if block.style is ListStyle.TASKS:
        return f"- [{'x' if checked else ' '}] {item}"
    if block.style is ListStyle.ORDERED:
        return f"{index + 1}. {item}"
    return f"- {item}"


def _serialize_table(block: Block) -> str:
    header = "| " + " | ".join(escape_cell(value) for value in block.headers) + " |"
    separator = "| " + " | ".join("---" for _ in block.headers) + " |"
    lines = [header, separator]
    for row in block.rows:
        cells = list(row) + [""] * (len(block.headers) - len(row))
        lines.append(
            "| " + " | ".join(escape_cell(value) for value in cells[: len(block.headers)]) + " |"
        )
    return "\n".join(lines)


def serialize_document(
    document: BlockDocument,
    *,
    include_title: bool = False,
) -> str:
    """Serialize all document blocks into one IR string."""
    blocks = [serialize_block(block) for block in document.blocks]
    if include_title and document.title:
        blocks.insert(0, f"# {document.title}")
    return "\n\n".join(blocks).strip()


def _split_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return [unescape_cell(cell) for cell in _PIPE_SPLIT_RE.split(stripped)]


def _is_table_start(lines: Sequence[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    return _SEPARATOR_RE.match(lines[index + 1]) is not None


def _looks_like_block_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return bool(
        _HEADING_RE.match(stripped)
        or _DIVIDER_RE.match(stripped)
        or _IMAGE_RE.match(stripped)
        or _CALLOUT_RE.match(stripped)
        or _QUOTE_RE.match(stripped)
        or _TASK_RE.match(stripped)
        or _BULLET_RE.match(stripped)
        or _ORDERED_RE.match(stripped)
        or _FENCE_RE.match(stripped)
        or _ESCAPED_MARKER_RE.match(stripped)
        or stripped.startswith("|")
    )


def _parse_code(lines: Sequence[str], index: int, match: re.Match[str]) -> tuple[Block, int]:
    fence = match.group(1)
    language = match.group(2)
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        candidate = lines[cursor].strip()
        if candidate.startswith(fence[0] * 3):
            cursor += 1
            break
        body.append(lines[cursor])
        cursor += 1
    block = make_block(
        BlockType.CODE,
        "\n".join(body).strip("\n"),
        language=language,
    )
    return block, cursor


def _parse_list(lines: Sequence[str], index: int) -> tuple[Block, int]:
    items: list[str] = []
    checked: list[bool] = []
    style = ListStyle.BULLET
    cursor = index
    while cursor < len(lines):
        line = lines[cursor].strip()
        if not line:
            break
        task = _TASK_RE.match(line)
        if task is not None:
            style = ListStyle.TASKS
            checked.append(task.group(1).casefold() == "x")
            items.append(task.group(2).strip())
        elif (ordered := _ORDERED_RE.match(line)) is not None:
            style = ListStyle.ORDERED
            checked.append(False)
            items.append(ordered.group(1).strip())
        elif (bullet := _BULLET_RE.match(line)) is not None:
            if style is ListStyle.ORDERED:
                break
            checked.append(False)
            items.append(bullet.group(1).strip())
        else:
            break
        cursor += 1
    block = make_block(BlockType.LIST, items=items, checked=checked, style=style)
    return block, cursor


def _parse_table(lines: Sequence[str], index: int) -> tuple[Block, int]:
    headers = _split_cells(lines[index])
    rows: list[list[str]] = []
    cursor = index + 2
    while cursor < len(lines):
        line = lines[cursor].strip()
        if not line or "|" not in line:
            break
        rows.append(_split_cells(line))
        cursor += 1
    block = make_block(BlockType.TABLE, headers=headers, rows=rows)
    return block, cursor


def _parse_quote(lines: Sequence[str], index: int) -> tuple[Block, int]:
    payload: list[str] = []
    cursor = index
    while cursor < len(lines):
        match = _QUOTE_RE.match(lines[cursor].strip())
        if match is None:
            break
        payload.append(match.group(1))
        cursor += 1
    return make_block(BlockType.QUOTE, "\n".join(payload).strip()), cursor


def _parse_callout(
    lines: Sequence[str],
    index: int,
    match: re.Match[str],
) -> tuple[Block, int]:
    try:
        tone = CalloutTone(match.group(1).casefold())
    except ValueError:
        tone = CalloutTone.INFO
    payload = [match.group(2)]
    cursor = index + 1
    while cursor < len(lines):
        quote = _QUOTE_RE.match(lines[cursor].strip())
        if quote is None:
            break
        payload.append(quote.group(1))
        cursor += 1
    block = make_block(BlockType.CALLOUT, "\n".join(payload).strip(), tone=tone)
    return block, cursor


def _parse_paragraph(lines: Sequence[str], index: int) -> tuple[Block, int]:
    payload: list[str] = []
    cursor = index
    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            break
        if cursor > index and _looks_like_block_start(line):
            break
        payload.append(_unescape_paragraph_line(line))
        cursor += 1
    return make_block(BlockType.PARAGRAPH, "\n".join(payload).strip()), cursor


def parse_blocks(markdown: str) -> tuple[Block, ...]:
    """Parse a Markdown-like string into an ordered tuple of blocks."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if (fence := _FENCE_RE.match(line)) is not None:
            block, index = _parse_code(lines, index, fence)
        elif (heading := _HEADING_RE.match(line)) is not None:
            level = min(MAX_HEADING_LEVEL, len(heading.group(1)))
            block = make_block(
                BlockType.HEADING,
                heading.group(2).strip(),
                level=level,
            )
            index += 1
        elif _DIVIDER_RE.match(line) is not None:
            block = make_block(BlockType.DIVIDER)
            index += 1
        elif (image := _IMAGE_RE.match(line)) is not None:
            block = make_block(BlockType.IMAGE, alt=image.group(1), source=image.group(2))
            index += 1
        elif (callout := _CALLOUT_RE.match(line)) is not None:
            block, index = _parse_callout(lines, index, callout)
        elif _QUOTE_RE.match(line) is not None:
            block, index = _parse_quote(lines, index)
        elif _is_table_start(lines, index):
            block, index = _parse_table(lines, index)
        elif (
            _TASK_RE.match(line) is not None
            or _BULLET_RE.match(line) is not None
            or _ORDERED_RE.match(line) is not None
        ):
            block, index = _parse_list(lines, index)
        else:
            block, index = _parse_paragraph(lines, index)
        if block.plain_text or block.type in (
            BlockType.DIVIDER,
            BlockType.IMAGE,
            BlockType.TABLE,
        ):
            blocks.append(refresh_block_mentions(block))
    return tuple(blocks)


def parse_document(
    markdown: str,
    *,
    document_id: str | None = None,
    title: str = "",
    tags: Sequence[str] = (),
) -> BlockDocument:
    """Parse Markdown-like IR into a new block document."""
    blocks = parse_blocks(markdown)
    if title and not any(
        block.type is BlockType.HEADING and block.text == title for block in blocks
    ):
        heading = make_block(BlockType.HEADING, title, level=1)
        blocks = (heading, *blocks)
    return make_document(document_id, title, blocks, tags=tags)


def markdown_roundtrip(document: BlockDocument) -> str:
    """Serialize and reparse a document, returning stable IR text."""
    return serialize_document(parse_document(serialize_document(document)))


def replace_document_blocks(
    document: BlockDocument,
    markdown: str,
) -> BlockDocument:
    """Return a copy with blocks replaced by parsed IR content."""
    return replace(document, blocks=parse_blocks(markdown))
