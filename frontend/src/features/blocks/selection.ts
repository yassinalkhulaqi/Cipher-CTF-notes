import { blockIndex, findBlock } from "./blocks";
import {
  type BlockDocument,
  type SelectionPoint,
  type SelectionRange,
} from "./types";

export function selectionPoint(blockId: string, offset = 0): SelectionPoint {
  return { blockId, offset: Math.max(0, Math.floor(offset)) };
}

export function selectionRange(point: SelectionPoint): SelectionRange {
  return { anchor: { ...point }, focus: { ...point } };
}

export function isCollapsed(selection: SelectionRange): boolean {
  return (
    selection.anchor.blockId === selection.focus.blockId &&
    selection.anchor.offset === selection.focus.offset
  );
}

export function selectionStart(selection: SelectionRange): SelectionPoint {
  const { anchor, focus } = selection;
  if (anchor.blockId === focus.blockId) {
    return {
      blockId: anchor.blockId,
      offset: Math.min(anchor.offset, focus.offset),
    };
  }
  return { ...anchor };
}

export function selectionEnd(selection: SelectionRange): SelectionPoint {
  const { anchor, focus } = selection;
  if (anchor.blockId === focus.blockId) {
    return {
      blockId: anchor.blockId,
      offset: Math.max(anchor.offset, focus.offset),
    };
  }
  return { ...focus };
}

export function selectionLength(selection: SelectionRange): number {
  if (isCollapsed(selection)) return 0;
  return Math.abs(selection.focus.offset - selection.anchor.offset);
}

export function selectionText(
  document: BlockDocument,
  selection: SelectionRange,
): string {
  if (selection.anchor.blockId !== selection.focus.blockId) return "";
  const block = findBlock(document, selection.anchor.blockId);
  if (!block) return "";
  const start = Math.min(selection.anchor.offset, selection.focus.offset);
  const end = Math.max(selection.anchor.offset, selection.focus.offset);
  return block.text.slice(start, end);
}

export function moveSelectionTo(
  _selection: SelectionRange,
  blockId: string,
  offset = 0,
): SelectionRange {
  return {
    anchor: selectionPoint(blockId, offset),
    focus: selectionPoint(blockId, offset),
  };
}

export function extendSelection(
  selection: SelectionRange,
  blockId: string,
  offset: number,
): SelectionRange {
  return {
    anchor: { ...selection.anchor },
    focus: selectionPoint(blockId, offset),
  };
}

export function clampSelection(
  document: BlockDocument,
  selection: SelectionRange,
): SelectionRange {
  const clamp = (point: SelectionPoint): SelectionPoint => {
    const block = findBlock(document, point.blockId) ?? document.blocks[0];
    return {
      blockId: block?.id ?? point.blockId,
      offset: Math.max(0, Math.min(point.offset, block?.text.length ?? 0)),
    };
  };
  return { anchor: clamp(selection.anchor), focus: clamp(selection.focus) };
}

export function selectionBlockIds(
  document: BlockDocument,
  selection: SelectionRange,
): string[] {
  const first = blockIndex(document, selection.anchor.blockId);
  const second = blockIndex(document, selection.focus.blockId);
  if (first < 0 || second < 0) return [];
  const start = Math.min(first, second);
  const end = Math.max(first, second);
  return document.blocks.slice(start, end + 1).map((block) => block.id);
}

export function selectionFollowsDocument(
  oldDocument: BlockDocument,
  newDocument: BlockDocument,
  selection: SelectionRange,
): SelectionRange {
  const anchorIndex = blockIndex(oldDocument, selection.anchor.blockId);
  const focusIndex = blockIndex(oldDocument, selection.focus.blockId);
  const anchor =
    anchorIndex >= 0
      ? newDocument.blocks[Math.min(anchorIndex, newDocument.blocks.length - 1)]
      : null;
  const focus =
    focusIndex >= 0
      ? newDocument.blocks[Math.min(focusIndex, newDocument.blocks.length - 1)]
      : null;
  if (!anchor || !focus) return clampSelection(newDocument, selection);
  return {
    anchor: {
      blockId: anchor.id,
      offset: Math.min(selection.anchor.offset, anchor.text.length),
    },
    focus: {
      blockId: focus.id,
      offset: Math.min(selection.focus.offset, focus.text.length),
    },
  };
}

export function selectionLabel(
  document: BlockDocument,
  selection: SelectionRange,
): string {
  const length = selectionLength(selection);
  if (length > 0) return `${length} chars selected`;
  const block = findBlock(document, selection.focus.blockId);
  return block ? `${block.type} · ${selection.focus.offset}` : "No selection";
}

export function caretAfterText(
  document: BlockDocument,
  blockId: string,
): SelectionRange {
  const block = findBlock(document, blockId);
  return selectionRange(selectionPoint(blockId, block?.text.length ?? 0));
}

export function caretBeforeText(
  _document: BlockDocument,
  blockId: string,
): SelectionRange {
  return selectionRange(selectionPoint(blockId, 0));
}

export function selectionEquals(
  left: SelectionRange,
  right: SelectionRange,
): boolean {
  return (
    left.anchor.blockId === right.anchor.blockId &&
    left.anchor.offset === right.anchor.offset &&
    left.focus.blockId === right.focus.blockId &&
    left.focus.offset === right.focus.offset
  );
}
