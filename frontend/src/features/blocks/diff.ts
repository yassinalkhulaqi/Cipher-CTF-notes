import { blockPlainText } from "./blocks";
import { copyBlock } from "./blocks";
import {
  type Block,
  type BlockDocument,
  type BlockPatch,
  type DiffEntry,
  type DocumentDiff,
  type PatchEntry,
} from "./types";

export function blockSignature(block: Block): string {
  return JSON.stringify({
    type: block.type,
    text: block.text,
    level: block.level,
    language: block.language,
    items: block.items,
    checked: block.checked,
    style: block.style,
    headers: block.headers,
    rows: block.rows,
    tone: block.tone,
    alt: block.alt,
    source: block.source,
    attrs: block.attrs,
  });
}

export function documentSignature(document: BlockDocument): string {
  return JSON.stringify({
    title: document.title,
    tags: document.tags,
    blocks: document.blocks.map(blockSignature),
  });
}

function lcsTable(left: string[], right: string[]): number[][] {
  const table: number[][] = Array.from({ length: left.length + 1 }, () =>
    Array<number>(right.length + 1).fill(0),
  );
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        left[i] === right[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

function describe(
  operation: DiffEntry["operation"],
  block: Block | null,
): string {
  const label = block ? block.type : "block";
  const text = block
    ? blockPlainText(block).replace(/\s+/g, " ").slice(0, 60)
    : "";
  return text ? `${operation} ${label}: ${text}` : `${operation} ${label}`;
}

export function diffDocuments(
  left: BlockDocument,
  right: BlockDocument,
): DocumentDiff {
  const leftSignatures = left.blocks.map(blockSignature);
  const rightSignatures = right.blocks.map(blockSignature);
  const table = lcsTable(leftSignatures, rightSignatures);
  const leftSignatureSet = new Set(leftSignatures);
  const entries: DiffEntry[] = [];
  let i = 0;
  let j = 0;
  while (i < left.blocks.length && j < right.blocks.length) {
    if (leftSignatures[i] === rightSignatures[j]) {
      if (left.blocks[i].id !== right.blocks[j].id) {
        entries.push({
          operation: "replace",
          blockId: left.blocks[i].id,
          index: j,
          previousIndex: i,
          block: copyBlock(right.blocks[j]),
          description: describe("replace", right.blocks[j]),
        });
      }
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      const block = left.blocks[i];
      entries.push({
        operation: "remove",
        blockId: block.id,
        index: j,
        previousIndex: i,
        block: null,
        description: describe("remove", block),
      });
      i += 1;
    } else {
      const block = right.blocks[j];
      const moved =
        leftSignatureSet.has(rightSignatures[j]) &&
        left.blocks.some((candidate) => candidate.id === block.id);
      entries.push({
        operation: moved ? "move" : "add",
        blockId: block.id,
        index: j,
        previousIndex: moved
          ? left.blocks.findIndex((candidate) => candidate.id === block.id)
          : null,
        block: copyBlock(block),
        description: describe(moved ? "move" : "add", block),
      });
      j += 1;
    }
  }
  while (i < left.blocks.length) {
    const block = left.blocks[i];
    entries.push({
      operation: "remove",
      blockId: block.id,
      index: right.blocks.length,
      previousIndex: i,
      block: null,
      description: describe("remove", block),
    });
    i += 1;
  }
  while (j < right.blocks.length) {
    const block = right.blocks[j];
    const moved =
      leftSignatureSet.has(rightSignatures[j]) &&
      left.blocks.some((candidate) => candidate.id === block.id);
    entries.push({
      operation: moved ? "move" : "add",
      blockId: block.id,
      index: j,
      previousIndex: moved
        ? left.blocks.findIndex((candidate) => candidate.id === block.id)
        : null,
      block: copyBlock(block),
      description: describe(moved ? "move" : "add", block),
    });
    j += 1;
  }
  return {
    leftId: left.id,
    rightId: right.id,
    leftRevision: left.revision,
    rightRevision: right.revision,
    entries,
  };
}

export function diffCounts(diff: DocumentDiff): Record<string, number> {
  const counts: Record<string, number> = {
    add: 0,
    remove: 0,
    replace: 0,
    move: 0,
  };
  for (const entry of diff.entries) counts[entry.operation] += 1;
  return counts;
}

export function makePatch(
  document: BlockDocument,
  entries: PatchEntry[] = [],
  label = "",
): BlockPatch {
  return {
    documentId: document.id,
    baseRevision: document.revision,
    entries,
    label,
  };
}

export function insertEntry(block: Block, index: number): PatchEntry {
  return {
    operation: "insert",
    blockId: block.id,
    block: copyBlock(block),
    index,
  };
}

export function updateEntry(block: Block, previousIndex = 0): PatchEntry {
  return {
    operation: "update",
    blockId: block.id,
    block: copyBlock(block),
    index: previousIndex,
  };
}

export function deleteEntry(blockId: string, previousIndex = 0): PatchEntry {
  return { operation: "delete", blockId, previousIndex };
}

export function moveEntry(
  blockId: string,
  index: number,
  previousIndex: number,
): PatchEntry {
  return { operation: "move", blockId, index, previousIndex };
}

export function patchFromDiff(
  left: BlockDocument,
  right: BlockDocument,
): BlockPatch {
  const diff = diffDocuments(left, right);
  const entries: PatchEntry[] = diff.entries.map((entry) => {
    if (entry.operation === "add" && entry.block)
      return insertEntry(entry.block, entry.index);
    if (entry.operation === "remove")
      return deleteEntry(entry.blockId, entry.previousIndex ?? 0);
    if (entry.operation === "replace" && entry.block) {
      return updateEntry(entry.block, entry.previousIndex ?? 0);
    }
    return moveEntry(entry.blockId, entry.index, entry.previousIndex ?? 0);
  });
  return makePatch(left, entries, "diff");
}

export function applyPatch(
  document: BlockDocument,
  patch: BlockPatch,
  requireRevision = true,
): BlockDocument {
  if (patch.documentId && patch.documentId !== document.id) {
    throw new Error("Patch targets a different document");
  }
  if (requireRevision && patch.baseRevision !== document.revision) {
    throw new Error(
      `Revision conflict: patch base ${patch.baseRevision}, current ${document.revision}`,
    );
  }
  const blocks = document.blocks.map(copyBlock);
  for (const entry of patch.entries) {
    const position = blocks.findIndex((block) => block.id === entry.blockId);
    if (entry.operation === "insert") {
      if (!entry.block) throw new Error("Insert operation requires a block");
      if (position >= 0)
        throw new Error(`Block ${entry.block.id} already exists`);
      const index = clampIndex(entry.index ?? blocks.length, blocks.length);
      blocks.splice(index, 0, copyBlock(entry.block));
    } else if (entry.operation === "update") {
      if (!entry.block) throw new Error("Update operation requires a block");
      if (position < 0)
        throw new Error(`Block ${entry.blockId} does not exist`);
      blocks[position] = copyBlock(entry.block);
    } else if (entry.operation === "delete") {
      if (position < 0)
        throw new Error(`Block ${entry.blockId} does not exist`);
      blocks.splice(position, 1);
    } else if (entry.operation === "move") {
      if (position < 0)
        throw new Error(`Block ${entry.blockId} does not exist`);
      const [block] = blocks.splice(position, 1);
      blocks.splice(
        clampIndex(entry.index ?? blocks.length, blocks.length),
        0,
        block,
      );
    }
  }
  return {
    ...document,
    blocks,
    revision: patch.baseRevision + 1,
    updatedAt: new Date().toISOString(),
  };
}

function clampIndex(index: number, length: number): number {
  return Math.max(0, Math.min(Math.floor(index), length));
}

export function mergeEntries(entries: PatchEntry[]): PatchEntry[] {
  const merged: PatchEntry[] = [];
  for (const entry of entries) {
    const same = merged
      .map((item, index) => ({ item, index }))
      .filter((candidate) => candidate.item.blockId === entry.blockId);
    const last = same.at(-1);
    if (entry.operation === "delete") {
      for (const candidate of [...same].reverse())
        merged.splice(candidate.index, 1);
      merged.push(entry);
      continue;
    }
    if (entry.operation === "insert") {
      const deleted = [...same]
        .reverse()
        .find((candidate) => candidate.item.operation === "delete");
      for (const candidate of [...same].reverse()) {
        if (
          candidate.item.operation === "insert" ||
          candidate.item.operation === "delete"
        ) {
          merged.splice(candidate.index, 1);
        }
      }
      if (deleted) {
        merged.push({
          operation: "update",
          blockId: entry.blockId,
          block: entry.block,
          index: entry.index ?? deleted.item.previousIndex ?? 0,
          previousIndex: deleted.item.previousIndex ?? null,
        });
      } else {
        merged.push(entry);
      }
      continue;
    }
    if (entry.operation === "update") {
      if (
        last &&
        (last.item.operation === "insert" || last.item.operation === "update")
      ) {
        merged[last.index] =
          last.item.operation === "insert"
            ? { ...entry, operation: "insert" }
            : entry;
      } else {
        merged.push(entry);
      }
      continue;
    }
    for (const candidate of [...same].reverse())
      merged.splice(candidate.index, 1);
    merged.push(entry);
  }
  return merged;
}

export function invertPatch(
  before: BlockDocument,
  after: BlockDocument,
): BlockPatch {
  return patchFromDiff(after, before);
}

export function patchSummary(patch: BlockPatch): Record<string, number> {
  const summary: Record<string, number> = {
    insert: 0,
    update: 0,
    delete: 0,
    move: 0,
  };
  for (const entry of patch.entries) summary[entry.operation] += 1;
  return summary;
}

export function patchTouchedBlocks(patch: BlockPatch): string[] {
  return Array.from(new Set(patch.entries.map((entry) => entry.blockId)));
}

export function rebasePatch(patch: BlockPatch, revision: number): BlockPatch {
  return { ...patch, baseRevision: revision };
}

export function patchEquals(left: BlockPatch, right: BlockPatch): boolean {
  return (
    left.documentId === right.documentId &&
    left.baseRevision === right.baseRevision &&
    JSON.stringify(left.entries) === JSON.stringify(right.entries)
  );
}

export function patchIsEmpty(patch: BlockPatch): boolean {
  return patch.entries.length === 0;
}
