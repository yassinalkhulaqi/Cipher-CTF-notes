import { createBlock } from "./blocks";
import { refreshMentions } from "./mentions";
import {
  BLOCK_LIMITS,
  type Block,
  type BlockDocument,
  type CalloutTone,
  type ListStyle,
} from "./types";

const HEADING_RE = /^(#{1,6})\s+(.*)$/;
const DIVIDER_RE = /^(?:-{3,}|\*{3,}|_{3,})$/;
const IMAGE_RE = /^!\[([^\]]*)\]\(([^)\s]+)\)$/;
const CALLOUT_RE = /^>\s*\[!([A-Za-z]+)\]\s*(.*)$/;
const QUOTE_RE = /^>\s?(.*)$/;
const TASK_RE = /^[-*+]\s+\[([ xX])\]\s+(.*)$/;
const BULLET_RE = /^[-*+]\s+(.*)$/;
const ORDERED_RE = /^\d+[.)]\s+(.*)$/;
const FENCE_RE = /^(`{3,}|~{3,})\s*([A-Za-z0-9_+#.-]*)\s*$/;
const SEPARATOR_RE = /^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$/;

export function escapeCell(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/\|/g, "\\|").replace(/\n/g, " ");
}

export function unescapeCell(value: string): string {
  return value.replace(/\\\|/g, "|").replace(/\\\\/g, "\\").trim();
}

function escapeParagraphLine(line: string): string {
  if (
    HEADING_RE.test(line) ||
    DIVIDER_RE.test(line) ||
    BULLET_RE.test(line) ||
    ORDERED_RE.test(line) ||
    QUOTE_RE.test(line) ||
    IMAGE_RE.test(line) ||
    TASK_RE.test(line) ||
    FENCE_RE.test(line)
  ) {
    return `\\${line}`;
  }
  return line;
}

function unescapeParagraphLine(line: string): string {
  return /^\\([-#*+>[\]|`])/.test(line) ? line.slice(1) : line;
}

export function serializeBlock(block: Block): string {
  switch (block.type) {
    case "paragraph": {
      const lines = (block.text || "(empty paragraph)")
        .split("\n")
        .map(escapeParagraphLine);
      return lines.join("\n");
    }
    case "heading":
      return `${"#".repeat(Math.max(1, Math.min(BLOCK_LIMITS.maxHeadingLevel, block.level)))} ${block.text}`.trimEnd();
    case "code":
      return `\`\`\`${block.language || "text"}\n${block.text.replace(/\n\n/g, "\n")}\n\`\`\``;
    case "quote":
      return block.text
        .split("\n")
        .map((line) => (line ? `> ${line}` : ">"))
        .join("\n");
    case "list":
      return block.items
        .map((item, index) => serializeListItem(block, item, index))
        .join("\n");
    case "table":
      return serializeTable(block);
    case "callout": {
      const lines = [`> [!${block.tone.toUpperCase()}]`];
      lines.push(
        ...block.text.split("\n").map((line) => (line ? `> ${line}` : ">")),
      );
      return lines.join("\n");
    }
    case "divider":
      return "---";
    case "image":
      return `![${block.alt}](${block.source})`;
  }
}

function serializeListItem(block: Block, item: string, index: number): string {
  if (block.style === "tasks") {
    return `- [${block.checked[index] ? "x" : " "}] ${item}`;
  }
  if (block.style === "ordered") return `${index + 1}. ${item}`;
  return `- ${item}`;
}

function serializeTable(block: Block): string {
  const headers = `| ${block.headers.map(escapeCell).join(" | ")} |`;
  const separator = `| ${block.headers.map(() => "---").join(" | ")} |`;
  const rows = block.rows.map((row) => {
    const cells = [...row];
    while (cells.length < block.headers.length) cells.push("");
    return `| ${cells.slice(0, block.headers.length).map(escapeCell).join(" | ")} |`;
  });
  return [headers, separator, ...rows].join("\n");
}

export function serializeDocument(
  document: BlockDocument,
  includeTitle = false,
): string {
  const parts = document.blocks.map(serializeBlock);
  if (includeTitle && document.title) parts.unshift(`# ${document.title}`);
  return parts.join("\n\n").trim();
}

function splitCells(line: string): string[] {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
  return value.split(/(?<!\\)\|/).map(unescapeCell);
}

function looksLikeBlockStart(line: string): boolean {
  const value = line.trim();
  if (!value) return true;
  return (
    HEADING_RE.test(value) ||
    DIVIDER_RE.test(value) ||
    IMAGE_RE.test(value) ||
    CALLOUT_RE.test(value) ||
    QUOTE_RE.test(value) ||
    TASK_RE.test(value) ||
    BULLET_RE.test(value) ||
    ORDERED_RE.test(value) ||
    FENCE_RE.test(value) ||
    value.startsWith("\\") ||
    value.startsWith("|")
  );
}

function isTableStart(lines: string[], index: number): boolean {
  return (
    index + 1 < lines.length &&
    lines[index].includes("|") &&
    SEPARATOR_RE.test(lines[index + 1])
  );
}

function parseCode(
  lines: string[],
  index: number,
  match: RegExpMatchArray,
): [Block, number] {
  const fence = match[1];
  const body: string[] = [];
  let cursor = index + 1;
  while (cursor < lines.length) {
    if (lines[cursor].trim().startsWith(fence[0].repeat(3))) {
      cursor += 1;
      break;
    }
    body.push(lines[cursor]);
    cursor += 1;
  }
  return [
    createBlock("code", { text: body.join("\n").trim(), language: match[2] }),
    cursor,
  ];
}

function parseList(lines: string[], index: number): [Block, number] {
  const items: string[] = [];
  const checked: boolean[] = [];
  let style: ListStyle = "bullet";
  let cursor = index;
  while (cursor < lines.length) {
    const line = lines[cursor].trim();
    if (!line) break;
    const task = TASK_RE.exec(line);
    const ordered = ORDERED_RE.exec(line);
    const bullet = BULLET_RE.exec(line);
    if (task) {
      style = "tasks";
      checked.push(task[1].toLowerCase() === "x");
      items.push(task[2].trim());
    } else if (ordered) {
      style = "ordered";
      checked.push(false);
      items.push(ordered[1].trim());
    } else if (bullet) {
      if (style === "ordered") break;
      checked.push(false);
      items.push(bullet[1].trim());
    } else {
      break;
    }
    cursor += 1;
  }
  return [createBlock("list", { items, checked, style }), cursor];
}

function parseTable(lines: string[], index: number): [Block, number] {
  const headers = splitCells(lines[index]);
  const rows: string[][] = [];
  let cursor = index + 2;
  while (cursor < lines.length && lines[cursor].trim().includes("|")) {
    rows.push(splitCells(lines[cursor]));
    cursor += 1;
  }
  return [createBlock("table", { headers, rows }), cursor];
}

function parseQuoted(lines: string[], index: number): [Block, number] {
  const payload: string[] = [];
  let cursor = index;
  while (cursor < lines.length) {
    const match = QUOTE_RE.exec(lines[cursor].trim());
    if (!match) break;
    payload.push(match[1]);
    cursor += 1;
  }
  return [createBlock("quote", { text: payload.join("\n").trim() }), cursor];
}

function parseCallout(
  lines: string[],
  index: number,
  match: RegExpMatchArray,
): [Block, number] {
  const allowed: CalloutTone[] = [
    "info",
    "warning",
    "success",
    "danger",
    "note",
    "tip",
  ];
  const rawTone = match[1].toLowerCase() as CalloutTone;
  const tone = allowed.includes(rawTone) ? rawTone : "info";
  const payload = [match[2]];
  let cursor = index + 1;
  while (cursor < lines.length) {
    const quote = QUOTE_RE.exec(lines[cursor].trim());
    if (!quote) break;
    payload.push(quote[1]);
    cursor += 1;
  }
  return [
    createBlock("callout", { text: payload.join("\n").trim(), tone }),
    cursor,
  ];
}

function parseParagraph(lines: string[], index: number): [Block, number] {
  const payload: string[] = [];
  let cursor = index;
  while (cursor < lines.length && lines[cursor].trim()) {
    if (cursor > index && looksLikeBlockStart(lines[cursor])) break;
    payload.push(unescapeParagraphLine(lines[cursor]));
    cursor += 1;
  }
  return [
    createBlock("paragraph", { text: payload.join("\n").trim() }),
    cursor,
  ];
}

export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    let block: Block;
    const fence = FENCE_RE.exec(line);
    const heading = HEADING_RE.exec(line);
    const image = IMAGE_RE.exec(line);
    const callout = CALLOUT_RE.exec(line);
    if (fence) {
      [block, index] = parseCode(lines, index, fence);
    } else if (heading) {
      block = createBlock("heading", {
        text: heading[2].trim(),
        level: Math.min(BLOCK_LIMITS.maxHeadingLevel, heading[1].length),
      });
      index += 1;
    } else if (DIVIDER_RE.test(line)) {
      block = createBlock("divider");
      index += 1;
    } else if (image) {
      block = createBlock("image", { alt: image[1], source: image[2] });
      index += 1;
    } else if (callout) {
      [block, index] = parseCallout(lines, index, callout);
    } else if (QUOTE_RE.test(line)) {
      [block, index] = parseQuoted(lines, index);
    } else if (isTableStart(lines, index)) {
      [block, index] = parseTable(lines, index);
    } else if (
      TASK_RE.test(line) ||
      BULLET_RE.test(line) ||
      ORDERED_RE.test(line)
    ) {
      [block, index] = parseList(lines, index);
    } else {
      [block, index] = parseParagraph(lines, index);
    }
    const hasBody = blockPlainTextForParse(block).length > 0;
    if (hasBody || ["divider", "image", "table"].includes(block.type)) {
      blocks.push(refreshMentions(block));
    }
  }
  return blocks;
}

function blockPlainTextForParse(block: Block): string {
  if (block.type === "list") return block.items.join("\n");
  if (block.type === "table") return block.headers.join(" ");
  if (block.type === "image") return block.source;
  return block.text;
}

export function parseDocument(
  markdown: string,
  options: { id?: string; title?: string; tags?: string[] } = {},
): BlockDocument {
  const blocks = parseBlocks(markdown);
  const withTitle =
    options.title &&
    !blocks.some(
      (block) => block.type === "heading" && block.text === options.title,
    )
      ? [createBlock("heading", { text: options.title, level: 1 }), ...blocks]
      : blocks;
  return {
    id: options.id ?? `doc-${Date.now().toString(36)}`,
    title: options.title ?? "",
    blocks: withTitle.length > 0 ? withTitle : [createBlock("paragraph")],
    revision: 0,
    updatedAt: new Date().toISOString(),
    tags: [...(options.tags ?? [])],
    metadata: {},
  };
}

export function markdownRoundTrip(document: BlockDocument): string {
  return serializeDocument(parseDocument(serializeDocument(document)));
}
