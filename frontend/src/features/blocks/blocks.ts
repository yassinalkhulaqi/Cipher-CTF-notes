import { blockId, documentId, nextBlockId } from "./ids";
import {
  BLOCK_LIMITS,
  type Block,
  type BlockDocument,
  type BlockType,
  type CalloutTone,
  type ListStyle,
} from "./types";

export interface BlockOptions {
  id?: string;
  text?: string;
  level?: number;
  language?: string;
  items?: string[];
  checked?: boolean[];
  style?: ListStyle;
  headers?: string[];
  rows?: string[][];
  tone?: CalloutTone;
  alt?: string;
  source?: string;
  attrs?: Record<string, string>;
}

export function createBlock(
  type: BlockType = "paragraph",
  options: BlockOptions = {},
): Block {
  const isHeading = type === "heading";
  const isList = type === "list";
  const isTable = type === "table";
  const isCode = type === "code";
  const isImage = type === "image";
  return {
    id: options.id ?? blockId(),
    type,
    text: options.text ?? "",
    level: isHeading
      ? Math.max(1, Math.min(BLOCK_LIMITS.maxHeadingLevel, options.level ?? 1))
      : 1,
    language: isCode ? (options.language ?? "") : "",
    items: isList ? [...(options.items ?? [])] : [],
    checked: isList ? [...(options.checked ?? [])] : [],
    style: options.style ?? "bullet",
    headers: isTable ? [...(options.headers ?? [])] : [],
    rows: isTable ? (options.rows ?? []).map((row) => [...row]) : [],
    tone: options.tone ?? "info",
    alt: isImage ? (options.alt ?? "") : "",
    source: isImage ? (options.source ?? "") : "",
    mentions: [],
    attrs: { ...(options.attrs ?? {}) },
  };
}

export function cloneBlock(block: Block): Block {
  return {
    ...block,
    id: blockId(),
    items: [...block.items],
    checked: [...block.checked],
    headers: [...block.headers],
    rows: block.rows.map((row) => [...row]),
    mentions: [],
    attrs: { ...block.attrs },
  };
}

export function copyBlock(block: Block): Block {
  return {
    ...block,
    items: [...block.items],
    checked: [...block.checked],
    headers: [...block.headers],
    rows: block.rows.map((row) => [...row]),
    mentions: block.mentions.map((mention) => ({ ...mention })),
    attrs: { ...block.attrs },
  };
}

export function emptyDocument(title = ""): BlockDocument {
  return {
    id: documentId(),
    title,
    blocks: [createBlock("paragraph")],
    revision: 0,
    updatedAt: new Date().toISOString(),
    tags: [],
    metadata: {},
  };
}

export function copyDocument(document: BlockDocument): BlockDocument {
  return {
    ...document,
    blocks: document.blocks.map(copyBlock),
    tags: [...document.tags],
    metadata: { ...document.metadata },
  };
}

export function blockPlainText(block: Block): string {
  switch (block.type) {
    case "list":
      return block.items.join("\n");
    case "table":
      return [
        block.headers.join(" | "),
        ...block.rows.map((row) => row.join(" | ")),
      ].join("\n");
    case "divider":
      return "";
    case "image":
      return [block.alt, block.source].filter(Boolean).join(" ");
    default:
      return block.text;
  }
}

export function documentPlainText(document: BlockDocument): string {
  return document.blocks.map(blockPlainText).filter(Boolean).join("\n\n");
}

export function documentWordCount(document: BlockDocument): number {
  return documentPlainText(document).trim().split(/\s+/).filter(Boolean).length;
}

export function findBlock(document: BlockDocument, id: string): Block | null {
  return document.blocks.find((block) => block.id === id) ?? null;
}

export function blockIndex(document: BlockDocument, id: string): number {
  return document.blocks.findIndex((block) => block.id === id);
}

export function updateBlock(
  document: BlockDocument,
  id: string,
  changes: Partial<Block>,
): BlockDocument {
  return {
    ...document,
    blocks: document.blocks.map((block) =>
      block.id === id ? { ...copyBlock(block), ...changes } : block,
    ),
  };
}

export function updateBlockText(
  document: BlockDocument,
  id: string,
  text: string,
): BlockDocument {
  return updateBlock(document, id, { text });
}

export function insertBlock(
  document: BlockDocument,
  block: Block,
  index?: number,
): BlockDocument {
  const blocks = [...document.blocks];
  const target = Math.max(0, Math.min(index ?? blocks.length, blocks.length));
  blocks.splice(target, 0, block);
  return { ...document, blocks };
}

export function insertAfter(
  document: BlockDocument,
  afterId: string,
  block: Block,
): BlockDocument {
  const index = blockIndex(document, afterId);
  return insertBlock(document, block, index < 0 ? undefined : index + 1);
}

export function removeBlock(
  document: BlockDocument,
  id: string,
): BlockDocument {
  const remaining = document.blocks.filter((block) => block.id !== id);
  return {
    ...document,
    blocks: remaining.length > 0 ? remaining : [createBlock("paragraph")],
  };
}

export function moveBlock(
  document: BlockDocument,
  id: string,
  index: number,
): BlockDocument {
  const source = blockIndex(document, id);
  if (source < 0) return document;
  const blocks = [...document.blocks];
  const [block] = blocks.splice(source, 1);
  const target = Math.max(0, Math.min(index, blocks.length));
  blocks.splice(target, 0, block);
  return { ...document, blocks };
}

export function moveBlockBy(
  document: BlockDocument,
  id: string,
  offset: number,
): BlockDocument {
  return moveBlock(document, id, blockIndex(document, id) + offset);
}

export function duplicateBlock(
  document: BlockDocument,
  id: string,
): BlockDocument {
  const index = blockIndex(document, id);
  if (index < 0) return document;
  return insertBlock(document, cloneBlock(document.blocks[index]), index + 1);
}

export function replaceBlocks(
  document: BlockDocument,
  blocks: Block[],
): BlockDocument {
  return {
    ...document,
    blocks:
      blocks.length > 0 ? blocks.map(copyBlock) : [createBlock("paragraph")],
  };
}

export function changeBlockType(
  document: BlockDocument,
  id: string,
  type: BlockType,
): BlockDocument {
  const existing = findBlock(document, id);
  if (!existing) return document;
  const replacement = createBlock(type, {
    id: existing.id,
    text: blockPlainText(existing),
    level: existing.level,
    language: existing.language,
    items: existing.items,
    checked: existing.checked,
    style: existing.style,
    headers: existing.headers,
    rows: existing.rows,
    tone: existing.tone,
    alt: existing.alt,
    source: existing.source,
    attrs: existing.attrs,
  });
  return updateBlock(document, id, replacement);
}

export function blockSummary(block: Block): string {
  const text = blockPlainText(block).replace(/\s+/g, " ").trim();
  if (text) return text.slice(0, 80);
  if (block.type === "divider") return "Divider";
  if (block.type === "image") return "Image placeholder";
  if (block.type === "table") return "Empty table";
  return `Empty ${block.type}`;
}

export function nextSiblingId(
  document: BlockDocument,
  id: string,
): string | null {
  const index = blockIndex(document, id);
  if (index < 0 || index + 1 >= document.blocks.length) return null;
  return document.blocks[index + 1].id;
}

export function previousSiblingId(
  document: BlockDocument,
  id: string,
): string | null {
  const index = blockIndex(document, id);
  if (index <= 0) return null;
  return document.blocks[index - 1].id;
}

export function blockIds(document: BlockDocument): string[] {
  return document.blocks.map((block) => block.id);
}

export function ensureEditableBlocks(document: BlockDocument): BlockDocument {
  if (document.blocks.length > 0) return document;
  return replaceBlocks(document, [createBlock("paragraph")]);
}

export function appendBlock(
  document: BlockDocument,
  type: BlockType,
): BlockDocument {
  const block = createBlock(type);
  return insertBlock(document, block);
}

export function fillListChecks(block: Block): Block {
  if (block.type !== "list") return block;
  return {
    ...block,
    checked: block.items.map((_, index) => block.checked[index] ?? false),
  };
}

export function addListItem(block: Block, text = ""): Block {
  if (block.type !== "list") return block;
  return {
    ...block,
    items: [...block.items, text],
    checked: [...block.checked, false],
  };
}

export function removeListItem(block: Block, index: number): Block {
  if (block.type !== "list") return block;
  const items = [...block.items];
  const checked = [...block.checked];
  items.splice(index, 1);
  checked.splice(index, 1);
  return { ...block, items, checked };
}

export function addTableRow(block: Block): Block {
  if (block.type !== "table") return block;
  const width = Math.max(1, block.headers.length);
  return {
    ...block,
    rows: [...block.rows, Array.from({ length: width }, () => "")],
  };
}

export function addTableColumn(block: Block): Block {
  if (block.type !== "table") return block;
  return {
    ...block,
    headers: [...block.headers, `Column ${block.headers.length + 1}`],
    rows: block.rows.map((row) => [...row, ""]),
  };
}

export function ensureBlockCapacity(document: BlockDocument): BlockDocument {
  if (document.blocks.length <= BLOCK_LIMITS.maxBlocks) return document;
  return {
    ...document,
    blocks: document.blocks.slice(0, BLOCK_LIMITS.maxBlocks),
  };
}

export function emptyBlockId(document: BlockDocument): string | null {
  for (const block of document.blocks) {
    if (!blockPlainText(block).trim()) return block.id;
  }
  return null;
}

export function freshBlock(type: BlockType, taken: string[]): Block {
  return createBlock(type, { id: nextBlockId(taken) });
}
