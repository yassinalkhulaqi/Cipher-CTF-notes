"""A pragmatic Markdown parser and HTML renderer used by the preview and exports."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, replace
from typing import Literal, TypeAlias

from redscribe.content.highlight import tokenize_code

SpanKind = Literal["text", "bold", "italic", "code", "strike", "link", "footnote_ref"]


@dataclass(frozen=True, slots=True)
class Span:
    kind: SpanKind
    text: str
    url: str = ""
    identifier: str = ""
    auto: bool = False


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    text: str
    identifier: str = ""


@dataclass(frozen=True, slots=True)
class Paragraph:
    text: str


@dataclass(frozen=True, slots=True)
class ListItem:
    text: str
    ordered: bool = False
    number: int = 1
    checked: bool | None = None
    indent: int = 0


@dataclass(frozen=True, slots=True)
class ListBlock:
    items: list[ListItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CodeBlock:
    language: str
    code: str


@dataclass(frozen=True, slots=True)
class Quote:
    text: str


@dataclass(frozen=True, slots=True)
class TableBlock:
    headers: list[str]
    rows: list[list[str]]
    aligns: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DefinitionItem:
    term: str
    definitions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DefinitionList:
    items: list[DefinitionItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FootnoteDefinition:
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class Rule:
    pass


Block: TypeAlias = (
    Heading
    | Paragraph
    | ListBlock
    | CodeBlock
    | Quote
    | TableBlock
    | DefinitionList
    | FootnoteDefinition
    | Rule
)


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Switches for the extended renderer.

    The defaults reproduce the historical preview output so existing callers do
    not change behaviour simply by upgrading the content layer.
    """

    heading_ids: bool = False
    heading_id_prefix: str = ""
    footnotes: bool = True
    autolinks: bool = True

    def with_heading_ids(self, prefix: str | None = None) -> RenderOptions:
        return replace(
            self,
            heading_ids=True,
            heading_id_prefix=self.heading_id_prefix if prefix is None else prefix,
        )


@dataclass(frozen=True, slots=True)
class TocEntry:
    level: int
    text: str
    identifier: str


@dataclass(frozen=True, slots=True)
class FootnoteContext:
    entries: dict[str, tuple[int, str]] = field(default_factory=dict)

    def get(self, label: str) -> tuple[int, str] | None:
        return self.entries.get(label)


DEFAULT_RENDER_OPTIONS = RenderOptions()

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([\w.+#-]*)[ \t]*$")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")
_HEADING_ID_RE = re.compile(r"\s*\{#([A-Za-z0-9][\w:.-]*)\}[ \t]*$")
_HR_RE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-+*]|\d{1,9}[.)])[ \t]+(?P<text>.*)$")
_QUOTE_RE = re.compile(r"^ {0,3}>[ \t]?(?P<text>.*)$")
_TASK_RE = re.compile(r"^\[(?P<state>[ xX])\][ \t]+(?P<text>.*)$")
_SETEXT_RE = re.compile(r"^ {0,3}(?P<marker>=+|-+)[ \t]*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_DEFINITION_MARKER_RE = re.compile(r"^ {0,3}:[ \t]+(?P<text>.*)$")
_FOOTNOTE_RE = re.compile(r"^ {0,3}\[\^(?P<label>[^\]\n]+)\]:[ \t]*(?P<text>.*)$")

_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~>])")
_INLINE_RE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<footnote>\[\^(?P<footnote_label>[^\]\n]+)\])"
    r"|(?P<link>\[(?P<link_text>[^\]\n]+)\]\((?P<link_url>[^)\s]+)\))"
    r"|(?P<bold>\*\*(?P<bold_text>.+?)\*\*|__(?P<bold_text2>.+?)__)"
    r"|(?P<strike>~~(?P<strike_text>.+?)~~)"
    r"|(?P<italic>\*(?P<italic_text>[^*\n]+)\*|(?<!\w)_(?P<italic_text2>[^_\n]+)_(?!\w))"
    r"|(?P<url>https?://[^\s<>()]+)"
)
_URL_TRAILING = ".,;:!?)]}"
_ANCHOR_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)


def parse_markdown(text: str) -> list[Block]:
    """Parse Markdown into a small, renderer-friendly block model."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    lines = normalized.split("\n")
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            block: Block
            block, index = _parse_fence(lines, index, fence)
            blocks.append(block)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            title, identifier = _split_heading_id(heading.group(2))
            blocks.append(Heading(len(heading.group(1)), title, identifier))
            index += 1
            continue

        if _HR_RE.match(line):
            blocks.append(Rule())
            index += 1
            continue

        if _QUOTE_RE.match(line):
            quote_lines: list[str] = []
            while index < len(lines):
                match = _QUOTE_RE.match(lines[index])
                if not match:
                    break
                quote_lines.append(match.group("text"))
                index += 1
            blocks.append(Quote("\n".join(quote_lines).strip()))
            continue

        footnote = _FOOTNOTE_RE.match(line)
        if footnote:
            block, index = _parse_footnote(lines, index, footnote)
            blocks.append(block)
            continue

        list_match = _LIST_RE.match(line)
        if list_match:
            list_block, index = _parse_list(lines, index)
            blocks.append(list_block)
            continue

        if _looks_like_table(lines, index):
            table_block, index = _parse_table(lines, index)
            blocks.append(table_block)
            continue

        if _looks_like_definition(lines, index):
            definition_block, index = _parse_definition(lines, index)
            blocks.append(definition_block)
            continue

        setext = _setext_heading(lines, index)
        if setext is not None:
            level, title, identifier = setext
            blocks.append(Heading(level, title, identifier))
            index += 2
            continue

        paragraph_lines = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not _starts_block(lines, index):
            paragraph_lines.append(lines[index].strip())
            index += 1
        blocks.append(Paragraph(" ".join(paragraph_lines)))
    return blocks


def _split_heading_id(text: str) -> tuple[str, str]:
    match = _HEADING_ID_RE.search(text)
    if match is None:
        return re.sub(r"[ \t]+#+[ \t]*$", "", text).strip(), ""
    cleaned = re.sub(r"[ \t]+#+[ \t]*$", "", text[: match.start()]).strip()
    return cleaned, match.group(1)


def _parse_fence(lines: list[str], index: int, opening: re.Match[str]) -> tuple[CodeBlock, int]:
    marker = opening.group(1)
    language = opening.group(2)
    fence_character = marker[0]
    minimum = len(marker)
    code_lines: list[str] = []
    index += 1
    while index < len(lines):
        candidate = lines[index]
        closing = re.match(
            rf"^ {{0,3}}{re.escape(fence_character)}{{{minimum},}}[ \t]*$", candidate
        )
        if closing:
            index += 1
            break
        code_lines.append(candidate)
        index += 1
    return CodeBlock(language.lower(), "\n".join(code_lines)), index


def _parse_footnote(
    lines: list[str], index: int, opening: re.Match[str]
) -> tuple[FootnoteDefinition, int]:
    label = opening.group("label").strip()
    parts = [opening.group("text").strip()]
    index += 1
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line[:1] not in (" ", "\t"):
            break
        if _FOOTNOTE_RE.match(line) or _starts_block(lines, index):
            break
        parts.append(line.strip())
        index += 1
    return FootnoteDefinition(label, " ".join(part for part in parts if part)), index


def _parse_list(lines: list[str], index: int) -> tuple[ListBlock, int]:
    items: list[ListItem] = []
    while index < len(lines):
        match = _LIST_RE.match(lines[index])
        if not match:
            break
        indent = len(match.group("indent").expandtabs(4))
        marker = match.group("marker")
        ordered = marker[0].isdigit()
        number = int(marker[:-1]) if ordered else 1
        item_text = match.group("text").strip()
        checked: bool | None = None
        task = _TASK_RE.match(item_text)
        if task:
            checked = task.group("state").lower() == "x"
            item_text = task.group("text").strip()
        index += 1
        continuation: list[str] = []
        while index < len(lines) and lines[index].strip():
            next_line = lines[index]
            if _starts_block(lines, index):
                break
            if not next_line.startswith((" ", "\t")):
                break
            continuation.append(next_line.strip())
            index += 1
        if continuation:
            item_text = " ".join([item_text, *continuation]).strip()
        items.append(ListItem(item_text, ordered, number, checked, indent))
    return ListBlock(items), index


def _looks_like_table(lines: list[str], index: int) -> bool:
    if "|" not in lines[index] or index + 1 >= len(lines):
        return False
    return _is_table_separator(lines[index + 1])


def _is_table_separator(line: str) -> bool:
    if "-" not in line:
        return False
    cells = _split_table_row(line)
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    return cells


def _parse_table(lines: list[str], index: int) -> tuple[TableBlock, int]:
    headers = _split_table_row(lines[index])
    separator = _split_table_row(lines[index + 1])
    aligns: list[str] = []
    for cell in separator:
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        else:
            aligns.append("left")
    rows: list[list[str]] = []
    index += 2
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        row = _split_table_row(lines[index])
        row = (row + [""] * len(headers))[: len(headers)]
        rows.append(row)
        index += 1
    return TableBlock(headers, rows, aligns), index


def _looks_like_definition(lines: list[str], index: int) -> bool:
    if _DEFINITION_MARKER_RE.match(lines[index]) or _starts_block(lines, index):
        return False
    return index + 1 < len(lines) and bool(_DEFINITION_MARKER_RE.match(lines[index + 1]))


def _parse_definition(lines: list[str], index: int) -> tuple[DefinitionList, int]:
    items: list[DefinitionItem] = []
    while index < len(lines) and _looks_like_definition(lines, index):
        term = lines[index].strip()
        index += 1
        definitions: list[str] = []
        while index < len(lines):
            match = _DEFINITION_MARKER_RE.match(lines[index])
            if match is None:
                break
            definitions.append(match.group("text").strip())
            index += 1
        items.append(DefinitionItem(term, definitions))
    return DefinitionList(items), index


def _setext_heading(lines: list[str], index: int) -> tuple[int, str, str] | None:
    if index + 1 >= len(lines):
        return None
    marker = _SETEXT_RE.match(lines[index + 1])
    if marker is None or not lines[index].strip():
        return None
    if _starts_block(lines, index):
        return None
    level = 1 if marker.group("marker").startswith("=") else 2
    title, identifier = _split_heading_id(lines[index].strip())
    return level, title, identifier


def _starts_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if _FENCE_RE.match(line) or _HEADING_RE.match(line) or _HR_RE.match(line):
        return True
    if _QUOTE_RE.match(line) or _LIST_RE.match(line):
        return True
    if _FOOTNOTE_RE.match(line) or _DEFINITION_MARKER_RE.match(line):
        return True
    return _looks_like_table(lines, index)


def parse_inline(text: str) -> list[Span]:
    """Parse inline Markdown spans (bold, italic, code, links, strike, footnotes)."""
    protected, placeholders = _protect_escapes(text)
    spans: list[Span] = []
    position = 0
    for match in _INLINE_RE.finditer(protected):
        if match.start() > position:
            spans.append(Span("text", _restore(protected[position : match.start()], placeholders)))
        if match.group("code"):
            value = match.group("code")[1:-1]
            spans.append(Span("code", _restore(value, placeholders)))
        elif match.group("footnote"):
            label = _restore(match.group("footnote_label") or "", placeholders)
            spans.append(Span("footnote_ref", label, identifier=label))
        elif match.group("link"):
            label = _restore(match.group("link_text"), placeholders)
            url = _restore(match.group("link_url"), placeholders)
            spans.append(Span("link", label, url))
        elif match.group("bold"):
            value = match.group("bold_text") or match.group("bold_text2") or ""
            spans.append(Span("bold", _restore(value, placeholders)))
        elif match.group("strike"):
            spans.append(Span("strike", _restore(match.group("strike_text") or "", placeholders)))
        elif match.group("italic"):
            value = match.group("italic_text") or match.group("italic_text2") or ""
            spans.append(Span("italic", _restore(value, placeholders)))
        elif match.group("url"):
            url = match.group("url")
            trailing = ""
            while url and url[-1] in _URL_TRAILING:
                trailing = url[-1] + trailing
                url = url[:-1]
            if url:
                spans.append(Span("link", url, url, auto=True))
            if trailing:
                spans.append(Span("text", trailing))
        position = match.end()
    if position < len(protected):
        spans.append(Span("text", _restore(protected[position:], placeholders)))
    return _merge_text(spans)


def _protect_escapes(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = chr(0xE000 + len(placeholders))
        placeholders[key] = match.group(1)
        return key

    return _ESCAPE_RE.sub(replace, text), placeholders


def _restore(text: str, placeholders: dict[str, str]) -> str:
    if not placeholders:
        return text
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def _merge_text(spans: list[Span]) -> list[Span]:
    merged: list[Span] = []
    for span in spans:
        if merged and span.kind == "text" and merged[-1].kind == "text":
            merged[-1] = Span("text", merged[-1].text + span.text)
        elif span.text or span.kind == "link":
            merged.append(span)
    return merged


def safe_url(url: str) -> str | None:
    """Allow only link schemes that are safe to open from notes and exports."""
    candidate = url.strip()
    if not candidate or any(character.isspace() or ord(character) < 32 for character in candidate):
        return None
    lowered = candidate.lower()
    if lowered.startswith(("http://", "https://", "mailto:")):
        return candidate
    if lowered.startswith("#"):
        return candidate
    return None


def inline_html(
    spans: list[Span],
    *,
    footnotes: FootnoteContext | None = None,
    options: RenderOptions | None = None,
) -> str:
    parts: list[str] = []
    for span in spans:
        text = html.escape(span.text)
        if span.kind == "bold":
            parts.append(f"<strong>{text}</strong>")
        elif span.kind == "italic":
            parts.append(f"<em>{text}</em>")
        elif span.kind == "code":
            parts.append(f"<code>{text}</code>")
        elif span.kind == "strike":
            parts.append(f"<del>{text}</del>")
        elif span.kind == "footnote_ref":
            parts.append(_footnote_ref_html(span, footnotes))
        elif span.kind == "link":
            url = safe_url(span.url)
            if (span.auto and options is not None and not options.autolinks) or url is None:
                parts.append(text)
            else:
                parts.append(
                    f'<a href="{html.escape(url, quote=True)}" '
                    f'target="_blank" rel="noreferrer noopener">{text}</a>'
                )
        else:
            parts.append(text)
    return "".join(parts)


def _footnote_ref_html(span: Span, footnotes: FootnoteContext | None) -> str:
    label = span.identifier or span.text
    entry = footnotes.get(label) if footnotes is not None else None
    if entry is None:
        return html.escape(f"[^{span.text}]")
    number, anchor = entry
    return (
        f'<sup class="footnote-ref" id="fnref-{html.escape(anchor, quote=True)}">'
        f'<a href="#fn-{html.escape(anchor, quote=True)}">[{number}]</a></sup>'
    )


def render_markdown_body(text: str, *, options: RenderOptions | None = None) -> str:
    """Render a Markdown document body to HTML without a page wrapper."""
    return render_blocks(parse_markdown(text), options=options)


def render_blocks(blocks: list[Block], *, options: RenderOptions | None = None) -> str:
    """Render parsed blocks, collecting footnotes into a trailing section."""
    opts = options or DEFAULT_RENDER_OPTIONS
    definitions: dict[str, str] = {}
    definition_order: list[str] = []
    for block in blocks:
        if opts.footnotes and isinstance(block, FootnoteDefinition):
            label = block.label.casefold()
            if label not in definitions:
                definition_order.append(label)
            definitions[label] = block.text

    context = _footnote_context(blocks, definitions, definition_order, opts)
    identifiers = _assign_heading_identifiers(blocks, opts)
    parts: list[str] = []
    for index, block in enumerate(blocks):
        if isinstance(block, FootnoteDefinition):
            continue
        parts.append(_render_block(block, identifiers.get(index, ""), context, opts))
    if context.entries:
        parts.append(_footnotes_html(definitions, context, opts))
    return "\n".join(parts)


def _render_block(
    block: Block, identifier: str, context: FootnoteContext, options: RenderOptions
) -> str:
    if isinstance(block, Heading):
        level = min(6, max(1, block.level))
        attribute = f' id="{html.escape(identifier, quote=True)}"' if identifier else ""
        body = inline_html(parse_inline(block.text), footnotes=context, options=options)
        return f"<h{level}{attribute}>{body}</h{level}>"
    if isinstance(block, Paragraph):
        body = inline_html(parse_inline(block.text), footnotes=context, options=options)
        return f"<p>{body}</p>"
    if isinstance(block, ListBlock):
        return _list_html(block, context, options)
    if isinstance(block, CodeBlock):
        return _code_html(block)
    if isinstance(block, Quote):
        paragraphs = [
            f"<p>{inline_html(parse_inline(line), footnotes=context, options=options)}</p>"
            for line in block.text.split("\n")
            if line.strip()
        ]
        return f"<blockquote>{''.join(paragraphs) or ' '}</blockquote>"
    if isinstance(block, TableBlock):
        return _table_html(block, context, options)
    if isinstance(block, DefinitionList):
        return _definition_html(block, context, options)
    return "<hr>"


def _list_html(block: ListBlock, context: FootnoteContext, options: RenderOptions) -> str:
    ordered = bool(block.items) and all(item.ordered for item in block.items)
    tag = "ol" if ordered else "ul"
    classes = "task-list" if any(item.checked is not None for item in block.items) else "list"
    rows: list[str] = [f'<{tag} class="{classes}">']
    for position, item in enumerate(block.items, start=1):
        margin = item.indent // 2 * 18
        style = f' style="margin-left:{margin}px"' if margin else ""
        checkbox = ""
        if item.checked is not None:
            checked = " checked" if item.checked else ""
            checkbox = f'<input type="checkbox" disabled{checked}> '
        value = ""
        if ordered and item.number != position:
            value = f' value="{item.number}"'
        body = inline_html(parse_inline(item.text), footnotes=context, options=options)
        rows.append(f"<li{value}{style}>{checkbox}{body}</li>")
    rows.append(f"</{tag}>")
    return "\n".join(rows)


def _code_html(block: CodeBlock) -> str:
    tokens = tokenize_code(block.code, block.language)
    pieces = [
        f'<span class="tok-{html.escape(token.kind, quote=True)}">{html.escape(token.text)}</span>'
        for token in tokens
    ]
    language = html.escape(block.language or "text")
    return (
        f'<div class="codeblock"><div class="code-lang">{language}</div>'
        f"<pre><code>{''.join(pieces)}</code></pre></div>"
    )


def _table_html(block: TableBlock, context: FootnoteContext, options: RenderOptions) -> str:
    headers = "".join(
        f'<th style="text-align:{_align(block, index)}">'
        f"{inline_html(parse_inline(cell), footnotes=context, options=options)}</th>"
        for index, cell in enumerate(block.headers)
    )
    rows: list[str] = []
    for row in block.rows:
        cells = "".join(
            f'<td style="text-align:{_align(block, index)}">'
            f"{inline_html(parse_inline(cell), footnotes=context, options=options)}</td>"
            for index, cell in enumerate(row)
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + headers
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _definition_html(
    block: DefinitionList, context: FootnoteContext, options: RenderOptions
) -> str:
    rows: list[str] = ['<dl class="definition-list">']
    for item in block.items:
        term = inline_html(parse_inline(item.term), footnotes=context, options=options)
        rows.append(f"<dt>{term}</dt>")
        for definition in item.definitions:
            body = inline_html(parse_inline(definition), footnotes=context, options=options)
            rows.append(f"<dd>{body}</dd>")
    rows.append("</dl>")
    return "\n".join(rows)


def _align(block: TableBlock, index: int) -> str:
    if index < len(block.aligns):
        return block.aligns[index]
    return "left"


def _footnote_context(
    blocks: list[Block],
    definitions: dict[str, str],
    definition_order: list[str],
    options: RenderOptions,
) -> FootnoteContext:
    if not options.footnotes or not definitions:
        return FootnoteContext()
    ordered: list[str] = []
    for block in blocks:
        if isinstance(block, FootnoteDefinition):
            continue
        for text in _block_inline_texts(block):
            for span in parse_inline(text):
                if span.kind != "footnote_ref":
                    continue
                label = (span.identifier or span.text).casefold()
                if label in definitions and label not in ordered:
                    ordered.append(label)
    ordered.extend(label for label in definition_order if label not in ordered)
    entries = {
        label: (number, heading_anchor(label)) for number, label in enumerate(ordered, start=1)
    }
    return FootnoteContext(entries)


def _block_inline_texts(block: Block) -> list[str]:
    if isinstance(block, (Heading, Paragraph, Quote)):
        return [block.text]
    if isinstance(block, ListBlock):
        return [item.text for item in block.items]
    if isinstance(block, TableBlock):
        return [*block.headers, *(cell for row in block.rows for cell in row)]
    if isinstance(block, DefinitionList):
        return [
            *[item.term for item in block.items],
            *[definition for item in block.items for definition in item.definitions],
        ]
    return []


def _footnotes_html(
    definitions: dict[str, str], context: FootnoteContext, options: RenderOptions
) -> str:
    rows: list[str] = ['<section class="footnotes"><h2 class="footnotes-title">Footnotes</h2><ol>']
    by_anchor = {anchor: (label, number) for label, (number, anchor) in context.entries.items()}
    for anchor, (label, number) in by_anchor.items():
        body = inline_html(parse_inline(definitions[label]), footnotes=context, options=options)
        rows.append(
            f'<li id="fn-{html.escape(anchor, quote=True)}" value="{number}">'
            f"<p>{body}</p>"
            f'<a class="footnote-backref" href="#fnref-{html.escape(anchor, quote=True)}">[back]</a>'
            "</li>"
        )
    rows.append("</ol></section>")
    return "\n".join(rows)


def heading_anchor(text: str, prefix: str = "") -> str:
    """Return a stable, URL-safe anchor for a heading label or footnote."""
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    slug = _ANCHOR_RE.sub("-", cleaned.casefold()).strip("-")
    return f"{prefix}{slug}" if slug else f"{prefix}section"


def _assign_heading_identifiers(blocks: list[Block], options: RenderOptions) -> dict[int, str]:
    identifiers: dict[int, str] = {}
    used: set[str] = set()
    for index, block in enumerate(blocks):
        if not isinstance(block, Heading) or not options.heading_ids:
            continue
        base = f"{options.heading_id_prefix}{block.identifier or heading_anchor(block.text)}"
        candidate = base
        counter = 2
        while candidate.casefold() in used:
            candidate = f"{base}-{counter}"
            counter += 1
        used.add(candidate.casefold())
        identifiers[index] = candidate
    return identifiers


def collect_toc(blocks: list[Block], *, options: RenderOptions | None = None) -> list[TocEntry]:
    """Collect heading links for a table of contents."""
    opts = options or DEFAULT_RENDER_OPTIONS
    if not opts.heading_ids:
        opts = opts.with_heading_ids()
    identifiers = _assign_heading_identifiers(blocks, opts)
    entries: list[TocEntry] = []
    for index, block in enumerate(blocks):
        if isinstance(block, Heading) and index in identifiers:
            entries.append(TocEntry(block.level, block.text, identifiers[index]))
    return entries


def render_toc_html(
    entries: list[TocEntry],
    *,
    title: str = "Contents",
    max_level: int = 6,
    options: RenderOptions | None = None,
) -> str:
    """Render a compact, nested-looking table of contents from heading links."""
    rows: list[str] = [
        f'<nav class="toc" aria-label="{html.escape(title, quote=True)}">',
        f'<div class="toc-title">{html.escape(title)}</div>',
        "<ol>",
    ]
    for entry in entries:
        if entry.level > max_level:
            continue
        anchor = html.escape(entry.identifier, quote=True)
        rows.append(
            f'<li class="toc-level-{entry.level}"><a href="#{anchor}">'
            f"{inline_html(parse_inline(entry.text), options=options)}</a></li>"
        )
    rows.extend(("</ol>", "</nav>"))
    return "\n".join(rows)


def render_html(
    text: str,
    title: str,
    *,
    subtitle: str = "",
    meta: list[tuple[str, str]] | None = None,
    options: RenderOptions | None = None,
    toc: bool = False,
    toc_title: str = "Contents",
) -> str:
    """Render a standalone, print-friendly HTML document."""
    meta = meta or []
    opts = options or DEFAULT_RENDER_OPTIONS
    if toc:
        opts = opts.with_heading_ids()
    meta_html = "".join(
        f'<div class="meta-item"><span>{html.escape(label)}</span>'
        f"<strong>{html.escape(value)}</strong></div>"
        for label, value in meta
        if value
    )
    subtitle_html = f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    toc_html = ""
    if toc:
        entries = collect_toc(parse_markdown(text), options=opts)
        if entries:
            toc_html = render_toc_html(entries, title=toc_title, options=opts)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{DOCUMENT_CSS}
</style>
</head>
<body>
<main class="page">
<header class="doc-header">
  <div class="brand">REDSCRIBE</div>
  <h1>{html.escape(title)}</h1>
  {subtitle_html}
  <div class="meta">{meta_html}</div>
</header>
{toc_html}
<article class="markdown">
{render_markdown_body(text, options=opts)}
</article>
<footer class="doc-footer">Generated by RedScribe · local-first security notes</footer>
</main>
</body>
</html>
"""


DOCUMENT_CSS = """
:root {
  color-scheme: dark;
  --bg: #0b0d12;
  --surface: #10131a;
  --surface-2: #161a24;
  --border: #252c39;
  --text: #e9edf5;
  --muted: #9aa5b8;
  --accent: #ff4d6d;
  --green: #22c55e;
  --blue: #3b82f6;
  --amber: #f59e0b;
  --red: #ef4444;
  --purple: #a855f7;
  --code: #0b0e16;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.65 "Segoe UI", Inter, Helvetica, Arial, sans-serif;
}
.page { max-width: 880px; margin: 0 auto; padding: 56px 32px 72px; }
.doc-header { border-bottom: 1px solid var(--border); padding-bottom: 28px; margin-bottom: 36px; }
.brand { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.24em; }
h1 { font-size: 38px; line-height: 1.15; margin: 14px 0 8px; letter-spacing: -0.02em; }
.subtitle { color: var(--muted); margin: 0 0 18px; font-size: 17px; }
.meta { display: flex; flex-wrap: wrap; gap: 10px 26px; margin-top: 18px; }
.meta-item { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.meta-item span { color: var(--muted); text-transform: uppercase; letter-spacing: 0.12em; }
.meta-item strong { font-size: 13px; font-weight: 600; }
.markdown h1, .markdown h2, .markdown h3, .markdown h4 { line-height: 1.25; margin: 1.6em 0 0.55em; }
.markdown h1 { font-size: 30px; color: #fff; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
.markdown h2 { font-size: 24px; color: var(--accent); }
.markdown h3 { font-size: 19px; }
.markdown h4, .markdown h5, .markdown h6 { font-size: 16px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
.markdown p { margin: 0.75em 0; }
.markdown a { color: var(--blue); text-decoration: none; border-bottom: 1px solid rgba(96,165,250,.35); }
.markdown code {
  font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace;
  font-size: 0.88em; background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 0.12em 0.35em;
}
.markdown blockquote {
  margin: 1em 0; padding: 0.2em 0 0.2em 18px; border-left: 3px solid var(--accent);
  color: var(--muted); background: rgba(255,77,109,.04);
}
.markdown blockquote p { margin: 0.35em 0; }
.markdown hr { border: 0; border-top: 1px solid var(--border); margin: 2em 0; }
.markdown ul, .markdown ol { padding-left: 24px; margin: 0.7em 0; }
.markdown li { margin: 0.28em 0; }
.task-list { list-style: none; padding-left: 4px; }
.task-list input { accent-color: var(--accent); margin-right: 6px; }
.definition-list { margin: 0.8em 0; }
.definition-list dt { color: var(--text); font-weight: 600; margin-top: 0.6em; }
.definition-list dd { margin: 0.2em 0 0.4em 20px; color: var(--muted); }
.toc {
  margin: 0 0 32px; padding: 16px 20px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--surface);
}
.toc-title { color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; }
.toc ol { list-style: none; margin: 10px 0 0; padding: 0; }
.toc li { margin: 3px 0; font-size: 14px; }
.toc .toc-level-3 { padding-left: 16px; }
.toc .toc-level-4, .toc .toc-level-5, .toc .toc-level-6 { padding-left: 32px; }
.footnotes {
  margin-top: 48px; padding-top: 18px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 14px;
}
.footnotes-title { font-size: 16px; color: var(--text); }
.footnotes ol { padding-left: 22px; }
.footnotes li { margin: 6px 0; }
.footnote-ref a, .footnote-backref { text-decoration: none; }
.codeblock { margin: 1.1em 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--code); }
.code-lang {
  padding: 6px 12px; border-bottom: 1px solid var(--border); background: var(--surface);
  color: var(--muted); font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  font-family: "Cascadia Mono", Consolas, monospace;
}
.codeblock pre { margin: 0; padding: 14px 16px; overflow-x: auto; }
.codeblock code { background: none; border: 0; padding: 0; font-size: 13.5px; line-height: 1.55; }
.tok-keyword { color: var(--accent); font-weight: 600; }
.tok-builtin { color: var(--blue); }
.tok-string { color: var(--green); }
.tok-comment { color: #697089; font-style: italic; }
.tok-number { color: var(--purple); }
.tok-variable { color: var(--amber); }
.table-wrap { overflow-x: auto; margin: 1em 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { border: 1px solid var(--border); padding: 8px 10px; vertical-align: top; }
th { background: var(--surface-2); color: var(--text); font-weight: 600; }
tr:nth-child(even) td { background: rgba(255,255,255,.015); }
.doc-footer { margin-top: 56px; padding-top: 18px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }
@media print {
  :root { color-scheme: light; --bg: #fff; --surface: #fff; --surface-2: #f4f5f8; --border: #d8deeb; --text: #1b2030; --muted: #626c82; --code: #f7f8fb; }
  body { background: #fff; }
  .page { max-width: none; padding: 24px; }
  .codeblock, table, blockquote, .footnotes, .toc { break-inside: avoid; }
  .toc { background: none; }
}
"""
