/** Virtualization, navigation, and selection model for the hex viewer. */

import type { HexRowData, HexWindowData } from "./types";
import { clamp } from "./format";

export const DEFAULT_ROW_HEIGHT = 22;
export const DEFAULT_OVERSCAN = 6;

export interface VisibleSlice<T> {
  start: number;
  end: number;
  items: T[];
}

export function visibleRows<T>(
  rows: readonly T[],
  scrollTop: number,
  viewportHeight: number,
  rowHeight = DEFAULT_ROW_HEIGHT,
  overscan = DEFAULT_OVERSCAN,
): VisibleSlice<T> {
  if (rows.length === 0) return { start: 0, end: 0, items: [] };
  const safeHeight = Math.max(1, rowHeight);
  const first = Math.floor(Math.max(0, scrollTop) / safeHeight);
  const count = Math.ceil(Math.max(1, viewportHeight) / safeHeight);
  const start = Math.max(0, first - Math.max(0, overscan));
  const end = Math.min(rows.length, first + count + Math.max(0, overscan));
  return { start, end, items: rows.slice(start, end) };
}

export function rowIndexForOffset(
  window: HexWindowData,
  offset: number,
): number {
  if (window.rows.length === 0) return 0;
  const first = window.rows[0].offset;
  const last = window.rows[window.rows.length - 1];
  return clamp(
    Math.floor((offset - first) / Math.max(1, window.bytes_per_row)),
    0,
    window.rows.length - 1,
  );
}

export function rowForOffset(
  window: HexWindowData,
  offset: number,
): HexRowData | null {
  if (!window.rows.length) return null;
  const index = rowIndexForOffset(window, offset);
  const row = window.rows[index];
  if (offset < row.offset || offset >= row.offset + row.cells.length)
    return null;
  return row;
}

export interface CellPosition {
  row: number;
  column: number;
  offset: number;
}

export function cellForOffset(
  window: HexWindowData,
  offset: number,
): CellPosition | null {
  const row = rowForOffset(window, offset);
  if (!row) return null;
  const index = rowIndexForOffset(window, offset);
  return { row: index, column: offset - row.offset, offset };
}

export function offsetForCell(
  window: HexWindowData,
  rowIndex: number,
  column: number,
): number | null {
  const row = window.rows[rowIndex];
  if (!row) return null;
  const bounded = clamp(column, 0, Math.max(0, row.cells.length - 1));
  return row.offset + bounded;
}

export function selectionBounds(
  anchor: number | null,
  head: number | null,
): { start: number; end: number } | null {
  if (anchor === null || head === null) return null;
  return { start: Math.min(anchor, head), end: Math.max(anchor, head) };
}

export function markSelection(
  window: HexWindowData,
  bounds: { start: number; end: number } | null,
): HexWindowData {
  const rows = window.rows.map((row) => ({
    ...row,
    selected:
      bounds !== null &&
      row.offset <= bounds.end &&
      row.offset + row.cells.length >= bounds.start,
  }));
  return {
    ...window,
    rows,
    selection_start: bounds ? bounds.start : null,
    selection_end: bounds ? bounds.end : null,
  };
}

export function selectedByteCount(window: HexWindowData): number {
  return window.rows.reduce(
    (total, row) => (row.selected ? total + row.cells.length : total),
    0,
  );
}

export function navigateOffset(
  current: number,
  delta: number,
  total: number,
): number {
  if (total <= 0) return 0;
  return clamp(current + delta, 0, Math.max(0, total - 1));
}

export function pageWindow(
  offset: number,
  bytesPerRow: number,
  rowsPerPage: number,
  total: number,
): { start: number; length: number } {
  const stride = Math.max(1, bytesPerRow) * Math.max(1, rowsPerPage);
  const start = Math.floor(Math.max(0, offset) / stride) * stride;
  return { start, length: Math.max(1, Math.min(stride, total - start)) };
}

export function scrollToRow(
  rowIndex: number,
  rowHeight = DEFAULT_ROW_HEIGHT,
): number {
  return Math.max(0, rowIndex) * Math.max(1, rowHeight);
}

export function describeSelection(window: HexWindowData): string {
  if (window.selection_start === null || window.selection_end === null) {
    return "No selection";
  }
  return `${window.selection_start.toString(16)}..${window.selection_end.toString(16)} (${selectedByteCount(window)} bytes)`;
}
