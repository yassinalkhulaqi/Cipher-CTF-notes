import { normalizeId } from "./ids";
import { copyBlock, fillListChecks } from "./blocks";
import {
  BLOCK_LIMITS,
  type Block,
  type BlockDocument,
  type CalloutTone,
  type ListStyle,
} from "./types";

const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

export function normalizeText(
  value: string,
  maxLength: number = BLOCK_LIMITS.maxTextLength,
): string {
  return value
    .replace(/\r\n?/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/\u200b/g, "")
    .replace(CONTROL_CHARS, "")
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/, ""))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim()
    .slice(0, maxLength);
}

export function normalizeItems(items: string[]): string[] {
  const result: string[] = [];
  for (const item of items) {
    const normalized = normalizeText(item, BLOCK_LIMITS.maxItemLength);
    if (normalized) result.push(normalized);
    if (result.length >= BLOCK_LIMITS.maxItems) break;
  }
  return result;
}

export function normalizeTable(
  headers: string[],
  rows: string[][],
): { headers: string[]; rows: string[][] } {
  const normalizedHeaders = normalizeItems(headers).slice(
    0,
    BLOCK_LIMITS.maxTableColumns,
  );
  const width = normalizedHeaders.length;
  const normalizedRows: string[][] = [];
  for (const row of rows.slice(0, BLOCK_LIMITS.maxTableRows)) {
    const cells = row
      .slice(0, BLOCK_LIMITS.maxTableColumns)
      .map((cell) => normalizeText(cell, BLOCK_LIMITS.maxItemLength));
    while (cells.length < width) cells.push("");
    normalizedRows.push(cells.slice(0, width));
  }
  return { headers: normalizedHeaders, rows: normalizedRows };
}

export function normalizeTone(value: string): CalloutTone {
  const allowed: CalloutTone[] = [
    "info",
    "warning",
    "success",
    "danger",
    "note",
    "tip",
  ];
  return allowed.includes(value as CalloutTone)
    ? (value as CalloutTone)
    : "info";
}

export function normalizeStyle(value: string): ListStyle {
  const allowed: ListStyle[] = ["bullet", "ordered", "tasks"];
  return allowed.includes(value as ListStyle) ? (value as ListStyle) : "bullet";
}

export function normalizeBlock(block: Block): Block {
  const result = copyBlock(block);
  const items = normalizeItems(result.items);
  const table = normalizeTable(result.headers, result.rows);
  const level =
    result.type === "heading"
      ? Math.max(1, Math.min(BLOCK_LIMITS.maxHeadingLevel, result.level))
      : 1;
  result.id = normalizeId(result.id);
  result.text = normalizeText(result.text);
  result.level = level;
  result.language =
    result.type === "code" ? normalizeText(result.language, 40) : "";
  result.items = items;
  result.checked = fillListChecks({ ...result, items }).checked;
  result.style = normalizeStyle(result.style);
  result.headers = table.headers;
  result.rows = table.rows;
  result.tone = normalizeTone(result.tone);
  result.alt = result.type === "image" ? normalizeText(result.alt, 500) : "";
  result.source =
    result.type === "image" ? normalizeText(result.source, 2000) : "";
  result.mentions = result.mentions.filter(
    (mention) =>
      mention.target.length > 0 &&
      mention.label.length > 0 &&
      mention.start >= 0 &&
      mention.end <= result.text.length &&
      mention.end > mention.start,
  );
  result.attrs = Object.fromEntries(
    Object.entries(result.attrs).map(([key, value]) => [
      key,
      normalizeText(value),
    ]),
  );
  return result;
}

export function normalizeDocument(document: BlockDocument): BlockDocument {
  const used = new Set<string>();
  const blocks = document.blocks.map((block) => {
    const normalized = normalizeBlock(block);
    if (used.has(normalized.id))
      normalized.id = normalizeId(`${normalized.id}-copy`);
    used.add(normalized.id);
    return normalized;
  });
  const tags = Array.from(
    new Set(
      document.tags
        .map((tag) => normalizeText(tag, 120).toLowerCase())
        .filter(Boolean),
    ),
  );
  return {
    ...document,
    id: normalizeId(document.id, "doc"),
    title: normalizeText(document.title, 300),
    blocks:
      blocks.length > 0
        ? blocks.slice(0, BLOCK_LIMITS.maxBlocks)
        : normalizeDocumentBlocks(),
    revision: Math.max(0, Math.floor(document.revision)),
    tags,
    metadata: Object.fromEntries(
      Object.entries(document.metadata).map(([key, value]) => [
        key,
        normalizeText(value),
      ]),
    ),
  };
}

function normalizeDocumentBlocks(): Block[] {
  return [
    {
      id: normalizeId("block-1"),
      type: "paragraph",
      text: "",
      level: 1,
      language: "",
      items: [],
      checked: [],
      style: "bullet",
      headers: [],
      rows: [],
      tone: "info",
      alt: "",
      source: "",
      mentions: [],
      attrs: {},
    },
  ];
}

export function normalizePatchEntryBlock(
  block: Block | null | undefined,
): Block | null {
  return block ? normalizeBlock(block) : null;
}

export function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function normalizeSearchQuery(query: string): string {
  return normalizeWhitespace(query).slice(0, 200);
}

export function normalizeMentionTarget(target: string): string {
  return normalizeId(target.replace(/^[@#]/, ""), "target").slice(0, 128);
}

export function normalizeDiffText(text: string): string {
  return normalizeText(text).toLowerCase();
}
