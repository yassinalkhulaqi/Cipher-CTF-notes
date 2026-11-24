/** Pure virtualization math shared by tree, table, and list primitives. */

import type { TreeRow, TreeSource, VirtualWindow } from "./types";

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function computeWindow(
  count: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  overscan = 4,
): VirtualWindow {
  if (count <= 0 || rowHeight <= 0 || viewportHeight <= 0) {
    return {
      start: 0,
      end: 0,
      offsetTop: 0,
      totalHeight: 0,
      rendered: 0,
    };
  }
  const safeScroll = Math.max(0, scrollTop);
  const padding = Math.max(0, Math.trunc(overscan));
  const start = clamp(Math.floor(safeScroll / rowHeight) - padding, 0, count);
  const visible = Math.ceil(viewportHeight / rowHeight) + 1;
  const end = clamp(start + visible + padding * 2, start, count);
  return {
    start,
    end,
    offsetTop: start * rowHeight,
    totalHeight: count * rowHeight,
    rendered: end - start,
  };
}

export function sliceWindow<T>(rows: readonly T[], window: VirtualWindow): T[] {
  return rows.slice(window.start, window.end);
}

export function flattenTree(
  roots: readonly TreeSource[],
  expanded: ReadonlySet<string>,
  depth = 0,
  parent = "",
): TreeRow[] {
  const rows: TreeRow[] = [];
  for (const root of roots) {
    const hasChildren = Boolean(root.children?.length);
    const isExpanded = hasChildren && expanded.has(root.key);
    rows.push({
      key: root.key,
      label: root.label,
      depth,
      hasChildren,
      expanded: isExpanded,
      parent,
      kind: root.kind,
      count: root.count,
    });
    if (isExpanded && root.children) {
      rows.push(...flattenTree(root.children, expanded, depth + 1, root.key));
    }
  }
  return rows;
}

export function toggleExpanded(expanded: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(expanded);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

export function treeRowHeight(depth: number, base = 30): number {
  return base + Math.min(6, Math.max(0, depth)) * 2;
}

export function estimateListHeight(count: number, rowHeight: number, headerHeight = 0): number {
  return Math.max(0, count) * Math.max(0, rowHeight) + Math.max(0, headerHeight);
}

export function ratioLoaded(rendered: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(1, Math.max(0, rendered / total));
}

export function scrollToIndex(index: number, rowHeight: number): number {
  return Math.max(0, index) * Math.max(0, rowHeight);
}
