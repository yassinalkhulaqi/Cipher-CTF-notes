/** Resizable pane-tree operations with per-pane context and persistence. */

import type {
  PaneNode,
  PaneOrientation,
  PaneSpec,
  WorkspaceSnapshot,
} from "./types";

export class WorkspaceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkspaceError";
  }
}

const MIN_RATIO = 0.1;
const MAX_RATIO = 0.9;
const PANE_ID = /^[a-z][a-z0-9_.:-]{0,79}$/;

export function parseOrientation(value: string): PaneOrientation {
  if (value === "row" || value === "horizontal") return "horizontal";
  if (value === "column" || value === "vertical") return "vertical";
  throw new WorkspaceError(`Unknown pane orientation: ${value}`);
}

export function makePane(id: string, title = id, contextRef = ""): PaneSpec {
  if (!PANE_ID.test(id)) throw new WorkspaceError(`Invalid pane id: ${id}`);
  if (!title.trim()) throw new WorkspaceError("Pane title cannot be blank");
  return {
    id,
    title,
    kind: "note",
    context_ref: contextRef,
    size: 1,
    min_size: MIN_RATIO,
    pinned: false,
    closable: true,
  };
}

export function leaf(pane: PaneSpec): PaneNode {
  return { pane: { ...pane } };
}

export function branch(
  first: PaneNode,
  second: PaneNode,
  orientation: PaneOrientation,
  ratio = 0.5,
): PaneNode {
  if (ratio < MIN_RATIO || ratio > MAX_RATIO)
    throw new WorkspaceError("Split ratio is out of range");
  return { orientation, ratio, children: [first, second] };
}

export function leaves(node: PaneNode): PaneSpec[] {
  if (node.pane) return [{ ...node.pane }];
  return (node.children ?? []).flatMap((child) => leaves(child));
}

export function paths(
  node: PaneNode,
  prefix: number[] = [],
): Record<string, number[]> {
  const result: Record<string, number[]> = {};
  const walk = (current: PaneNode, path: number[]): void => {
    if (current.pane) {
      result[current.pane.id] = path;
      return;
    }
    (current.children ?? []).forEach((child, index) =>
      walk(child, [...path, index]),
    );
  };
  walk(node, prefix);
  return result;
}

export function findPane(node: PaneNode, id: string): number[] | null {
  return paths(node)[id] ?? null;
}

export function nodeAt(node: PaneNode, path: number[]): PaneNode {
  let current = node;
  for (const index of path) {
    if (!current.children || index >= current.children.length) {
      throw new WorkspaceError(`Invalid pane path: ${path.join(".")}`);
    }
    current = current.children[index];
  }
  return current;
}

function replaceAt(
  node: PaneNode,
  path: number[],
  replacement: PaneNode,
): PaneNode {
  if (!path.length) return replacement;
  const [index, ...rest] = path;
  if (
    !node.children ||
    node.children[index] === undefined ||
    !node.orientation
  ) {
    throw new WorkspaceError(`Invalid pane path: ${path.join(".")}`);
  }
  const children = [...node.children];
  children[index] = replaceAt(children[index], rest, replacement);
  return branch(children[0], children[1], node.orientation, node.ratio ?? 0.5);
}

export function insertPane(
  node: PaneNode,
  paneId: string,
  pane: PaneSpec,
  orientation: PaneOrientation,
  ratio = 0.5,
  after = true,
): PaneNode {
  const path = findPane(node, paneId);
  if (!path) throw new WorkspaceError(`Unknown pane: ${paneId}`);
  if (leaves(node).some((item) => item.id === pane.id)) {
    throw new WorkspaceError(`Pane already exists: ${pane.id}`);
  }
  const target = nodeAt(node, path);
  if (!target.pane) throw new WorkspaceError("Can only split a leaf pane");
  const first = after ? target : leaf(pane);
  const second = after ? leaf(pane) : target;
  return replaceAt(
    node,
    path,
    branch(first, second, orientation, after ? ratio : 1 - ratio),
  );
}

export function removePane(node: PaneNode, paneId: string): PaneNode {
  const path = findPane(node, paneId);
  if (!path) throw new WorkspaceError(`Unknown pane: ${paneId}`);
  if (!path.length) throw new WorkspaceError("Cannot close the last pane");
  const target = nodeAt(node, path);
  if (target.pane && !target.pane.closable)
    throw new WorkspaceError(`Pane is pinned: ${paneId}`);
  const parentPath = path.slice(0, -1);
  const sibling = nodeAt(node, [...parentPath, 1 - path[path.length - 1]]);
  return replaceAt(node, parentPath, sibling);
}

export function resizePane(
  node: PaneNode,
  paneId: string,
  size: number,
): PaneNode {
  if (size < MIN_RATIO || size > MAX_RATIO)
    throw new WorkspaceError("Pane size is out of range");
  const path = findPane(node, paneId);
  if (!path || !path.length)
    throw new WorkspaceError(`Pane has no resizable parent: ${paneId}`);
  const parent = nodeAt(node, path.slice(0, -1));
  if (!parent.orientation || !parent.children) {
    throw new WorkspaceError(`Pane has no resizable parent: ${paneId}`);
  }
  const ratio = path[path.length - 1] === 0 ? size : 1 - size;
  return replaceAt(
    node,
    path.slice(0, -1),
    branch(parent.children[0], parent.children[1], parent.orientation, ratio),
  );
}

export function updatePane(
  node: PaneNode,
  paneId: string,
  changes: Partial<PaneSpec>,
): PaneNode {
  const path = findPane(node, paneId);
  if (!path) throw new WorkspaceError(`Unknown pane: ${paneId}`);
  const target = nodeAt(node, path);
  if (!target.pane) throw new WorkspaceError(`Node is not a pane: ${paneId}`);
  return replaceAt(
    node,
    path,
    leaf({ ...target.pane, ...changes, id: paneId }),
  );
}

export function paneNodeFromData(data: PaneNode | undefined): PaneNode {
  if (!data) throw new WorkspaceError("Pane tree snapshot needs a root");
  if (data.pane) return leaf(data.pane);
  if (!data.orientation || !data.children || data.children.length !== 2) {
    throw new WorkspaceError(
      "Pane split needs an orientation and two children",
    );
  }
  return branch(
    paneNodeFromData(data.children[0]),
    paneNodeFromData(data.children[1]),
    parseOrientation(data.orientation),
    data.ratio ?? 0.5,
  );
}

export interface PanePersistence {
  load(): WorkspaceSnapshot | null;
  save(snapshot: WorkspaceSnapshot): void;
}

export class MemoryPanePersistence implements PanePersistence {
  private stored: WorkspaceSnapshot | null = null;

  load(): WorkspaceSnapshot | null {
    return this.stored ? structuredClone(this.stored) : null;
  }

  save(snapshot: WorkspaceSnapshot): void {
    this.stored = structuredClone(snapshot);
  }
}

export class WorkspaceModel {
  private snapshotData: WorkspaceSnapshot;
  private readonly persistence: PanePersistence | null;

  constructor(
    snapshot?: WorkspaceSnapshot,
    persistence: PanePersistence | null = null,
  ) {
    this.snapshotData = snapshot
      ? structuredClone(snapshot)
      : WorkspaceModel.initial();
    this.persistence = persistence;
  }

  static initial(): WorkspaceSnapshot {
    const pane = makePane("pane:main", "Main workspace");
    return { id: "main", active_pane: pane.id, tree: { root: leaf(pane) } };
  }

  snapshot(): WorkspaceSnapshot {
    return structuredClone(this.snapshotData);
  }

  panes(): PaneSpec[] {
    return leaves(this.snapshotData.tree.root);
  }

  active(): PaneSpec {
    const found = this.panes().find(
      (pane) => pane.id === this.snapshotData.active_pane,
    );
    if (!found) throw new WorkspaceError("Active pane is missing");
    return found;
  }

  activate(paneId: string): PaneSpec {
    if (!findPane(this.snapshotData.tree.root, paneId)) {
      throw new WorkspaceError(`Unknown pane: ${paneId}`);
    }
    this.snapshotData.active_pane = paneId;
    return this.active();
  }

  split(
    paneId: string,
    orientation: string,
    paneIdNew: string,
    title = "",
    ratio = 0.5,
  ): PaneSpec {
    const identifier = paneIdNew || `pane:${this.panes().length + 1}`;
    this.snapshotData.tree.root = insertPane(
      this.snapshotData.tree.root,
      paneId,
      makePane(identifier, title || `Pane ${this.panes().length + 1}`),
      parseOrientation(orientation),
      ratio,
    );
    this.snapshotData.active_pane = identifier;
    return this.active();
  }

  resize(paneId: string, size: number): void {
    this.snapshotData.tree.root = resizePane(
      this.snapshotData.tree.root,
      paneId,
      size,
    );
  }

  close(paneId: string): PaneSpec {
    this.snapshotData.tree.root = removePane(
      this.snapshotData.tree.root,
      paneId,
    );
    if (
      !this.panes().some((pane) => pane.id === this.snapshotData.active_pane)
    ) {
      this.snapshotData.active_pane = this.panes()[0].id;
    }
    return this.active();
  }

  setContext(paneId: string, contextRef: string): PaneSpec {
    this.snapshotData.tree.root = updatePane(
      this.snapshotData.tree.root,
      paneId,
      {
        context_ref: contextRef,
      },
    );
    return this.panes().find((pane) => pane.id === paneId) as PaneSpec;
  }

  rename(paneId: string, title: string): PaneSpec {
    this.snapshotData.tree.root = updatePane(
      this.snapshotData.tree.root,
      paneId,
      { title },
    );
    return this.panes().find((pane) => pane.id === paneId) as PaneSpec;
  }

  restore(snapshot: WorkspaceSnapshot): void {
    const restored: WorkspaceSnapshot = structuredClone(snapshot);
    const paneIds = leaves(restored.tree.root).map((pane) => pane.id);
    if (!paneIds.includes(restored.active_pane)) {
      throw new WorkspaceError("Active pane must be part of the workspace");
    }
    this.snapshotData = restored;
  }

  save(): WorkspaceSnapshot {
    const snapshot = this.snapshot();
    this.persistence?.save(snapshot);
    return snapshot;
  }

  load(): boolean {
    const snapshot = this.persistence?.load();
    if (!snapshot) return false;
    this.restore(snapshot);
    return true;
  }
}
