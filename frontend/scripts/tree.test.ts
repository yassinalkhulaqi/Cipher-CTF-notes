import assert from "node:assert/strict";
import test from "node:test";
import {
  allIds,
  countNotes,
  filterTree,
  flattenVisible,
  indexTree,
  isDescendant,
} from "../src/lib/tree";
import type { TreeNode } from "../src/lib/types";

function note(id: number, title: string, extras: Partial<TreeNode> = {}): TreeNode {
  return {
    id,
    parent_id: null,
    title,
    kind: "note",
    status: "todo",
    difficulty: "medium",
    flag: "",
    tags: "",
    tag_list: [],
    target: "",
    pinned: false,
    trashed: false,
    path: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    children: [],
    ...extras,
  };
}

function folder(
  id: number,
  title: string,
  children: TreeNode[],
  parentId: number | null = null,
): TreeNode {
  return note(id, title, { kind: "folder", children, parent_id: parentId });
}

const tree: TreeNode[] = [
  folder(1, "HTB", [
    note(2, "Blocky writeup", { parent_id: 1, tags: "htb, minecraft" }),
    folder(
      3,
      "Recon",
      [note(4, "Nmap sweep", { parent_id: 3, target: "10.10.10.10" })],
      1,
    ),
  ]),
  note(5, "PicoCTF flags"),
];

test("countNotes counts notes, not folders", () => {
  assert.equal(countNotes(tree), 3);
});

test("flattenVisible walks expanded folders only", () => {
  assert.deepEqual(allIds(tree), [1, 2, 3, 4, 5]);
  const collapsed = flattenVisible(tree, new Set());
  assert.deepEqual(collapsed.map((row) => row.node.id), [1, 5]);
  const expanded = flattenVisible(tree, new Set([1, 3]));
  assert.deepEqual(expanded.map((row) => row.node.id), [1, 2, 3, 4, 5]);
  assert.deepEqual(expanded.map((row) => row.depth), [0, 1, 1, 2, 0]);
});

test("filterTree keeps a matched parent and its matching children", () => {
  const filtered = filterTree(tree, "htb");
  assert.deepEqual(filtered.map((node) => node.id), [1]);
  // Only the children that themselves match are retained.
  assert.deepEqual(filtered[0].children.map((node) => node.id), [2]);
});

test("filterTree keeps folders that contain matching descendants", () => {
  const filtered = filterTree(tree, "nmap");
  assert.deepEqual(filtered.map((node) => node.id), [1]);
  const recon = filtered[0].children.find((node) => node.id === 3);
  assert.ok(recon);
  assert.deepEqual(recon.children.map((node) => node.id), [4]);
});

test("filterTree matches tags and targets", () => {
  assert.deepEqual(filterTree(tree, "minecraft").map((node) => node.id), [1]);
  assert.deepEqual(filterTree(tree, "10.10.10.10").map((node) => node.id), [1]);
});

test("filterTree with an empty needle returns the tree untouched", () => {
  assert.equal(filterTree(tree, ""), tree);
});

test("isDescendant checks containment via the index", () => {
  const index = indexTree(tree);
  assert.equal(isDescendant(index, 4, 1), true);
  assert.equal(isDescendant(index, 4, 3), true);
  assert.equal(isDescendant(index, 1, 4), false);
  assert.equal(isDescendant(index, 5, 1), false);
  assert.equal(isDescendant(index, 1, 1), false);
});
