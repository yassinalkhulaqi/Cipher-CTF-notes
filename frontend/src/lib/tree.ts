import type { NodeSummary, TreeNode } from "./types";

export interface FlatNode {
  node: TreeNode;
  depth: number;
  parentId: number | null;
}

export function indexTree(tree: TreeNode[]): Map<number, TreeNode> {
  const index = new Map<number, TreeNode>();
  const walk = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      index.set(node.id, node);
      walk(node.children);
    }
  };
  walk(tree);
  return index;
}

export function flattenVisible(
  tree: TreeNode[],
  expanded: ReadonlySet<number>,
): FlatNode[] {
  const rows: FlatNode[] = [];
  const walk = (nodes: TreeNode[], depth: number, parentId: number | null) => {
    for (const node of nodes) {
      rows.push({ node, depth, parentId });
      if (node.kind === "folder" && expanded.has(node.id)) {
        walk(node.children, depth + 1, node.id);
      }
    }
  };
  walk(tree, 0, null);
  return rows;
}

export function collectFolders(tree: TreeNode[]): { id: number; title: string; depth: number }[] {
  const folders: { id: number; title: string; depth: number }[] = [];
  const walk = (nodes: TreeNode[], depth: number) => {
    for (const node of nodes) {
      if (node.kind === "folder") {
        folders.push({ id: node.id, title: node.title, depth });
        walk(node.children, depth + 1);
      }
    }
  };
  walk(tree, 0);
  return folders;
}

export function countNotes(tree: TreeNode[]): number {
  let count = 0;
  const walk = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (node.kind === "note") count += 1;
      walk(node.children);
    }
  };
  walk(tree);
  return count;
}

export function ancestorsOf(index: Map<number, TreeNode>, id: number): number[] {
  const ancestors: number[] = [];
  let node = index.get(id);
  while (node && node.parent_id !== null) {
    ancestors.push(node.parent_id);
    node = index.get(node.parent_id);
  }
  return ancestors;
}

export function expandAncestors(
  index: Map<number, TreeNode>,
  id: number,
  expanded: Set<number>,
): void {
  for (const ancestor of ancestorsOf(index, id)) expanded.add(ancestor);
}

export function filterTree(tree: TreeNode[], query: string): TreeNode[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return tree;

  const matches = (node: TreeNode): boolean => {
    const haystack = [
      node.title,
      node.path,
      node.target,
      node.tags,
      node.flag,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  };

  const filter = (nodes: TreeNode[]): TreeNode[] => {
    const result: TreeNode[] = [];
    for (const node of nodes) {
      const children = filter(node.children);
      if (matches(node) || children.length > 0) {
        result.push({ ...node, children });
      }
    }
    return result;
  };

  return filter(tree);
}

export function allIds(tree: TreeNode[]): number[] {
  const ids: number[] = [];
  const walk = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      ids.push(node.id);
      walk(node.children);
    }
  };
  walk(tree);
  return ids;
}

export function isDescendant(
  index: Map<number, TreeNode>,
  maybeChild: number,
  maybeParent: number,
): boolean {
  let node = index.get(maybeChild);
  while (node && node.parent_id !== null) {
    if (node.parent_id === maybeParent) return true;
    node = index.get(node.parent_id);
  }
  return false;
}

export function parentForSelection(
  index: Map<number, TreeNode>,
  selectedId: number | null,
): number | null {
  if (selectedId === null) return null;
  const node = index.get(selectedId);
  if (!node) return null;
  return node.kind === "folder" ? node.id : node.parent_id;
}

export function summaryToTree(node: NodeSummary): TreeNode {
  return { ...node, children: [] };
}
