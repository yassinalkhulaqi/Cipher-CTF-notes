import assert from "node:assert/strict";
import test from "node:test";

import {
  DeferredQueue,
  graphNodeTask,
  planChunks,
  projectTask,
  shouldDefer,
} from "../src/features/performance/deferredGraph";
import {
  FRAME_BUDGET_MS,
  FrameMonitor,
  formatFrameStats,
  frameTone,
  percentile,
  summarizeFrames,
} from "../src/features/performance/frameMonitor";
import {
  buildFreshness,
  freshnessLabel,
  freshnessTone,
  shouldRefresh,
} from "../src/features/performance/freshness";
import {
  clamp,
  computeWindow,
  estimateListHeight,
  flattenTree,
  ratioLoaded,
  scrollToIndex,
  sliceWindow,
  toggleExpanded,
  treeRowHeight,
} from "../src/features/performance/virtual";
import type { TreeSource } from "../src/features/performance/types";

const tree: TreeSource[] = [
  {
    key: "root-a",
    label: "Root A",
    kind: "folder",
    count: 2,
    children: [
      { key: "child-a", label: "Child A", kind: "note", count: 0 },
      {
        key: "child-b",
        label: "Child B",
        kind: "folder",
        count: 1,
        children: [{ key: "grand", label: "Grand", kind: "note", count: 0 }],
      },
    ],
  },
  { key: "root-b", label: "Root B", kind: "note", count: 0 },
];

test("virtual window renders a small slice of a 20k tree", () => {
  const window = computeWindow(20000, 320000, 720, 32, 4);
  assert.equal(window.start, 9996);
  assert.equal(window.rendered, 32);
  assert.equal(window.totalHeight, 640000);
  assert.equal(window.offsetTop, window.start * 32);
  assert.ok(ratioLoaded(window.rendered, 20000) < 0.01);
});

test("virtual window handles empty and degenerate inputs", () => {
  assert.deepEqual(computeWindow(0, 0, 720, 32), {
    start: 0,
    end: 0,
    offsetTop: 0,
    totalHeight: 0,
    rendered: 0,
  });
  assert.equal(computeWindow(10, -100, 0, 32).rendered, 0);
  assert.equal(computeWindow(10, -100, 720, 0).rendered, 0);
  assert.equal(computeWindow(5, 99999, 100, 20).start, 5);
});

test("slice window returns exactly the rendered rows", () => {
  const rows = Array.from({ length: 100 }, (_, index) => index);
  const window = computeWindow(100, 200, 100, 20, 2);
  assert.deepEqual(
    sliceWindow(rows, window),
    rows.slice(window.start, window.end),
  );
  assert.equal(sliceWindow(rows, window).length, window.rendered);
});

test("flatten tree respects expanded state and parent links", () => {
  const collapsed = flattenTree(tree, new Set());
  assert.deepEqual(
    collapsed.map((row) => row.key),
    ["root-a", "root-b"],
  );

  const expanded = flattenTree(tree, new Set(["root-a"]));
  assert.deepEqual(
    expanded.map((row) => row.key),
    ["root-a", "child-a", "child-b", "root-b"],
  );
  assert.equal(expanded[1].parent, "root-a");
  assert.equal(expanded[1].depth, 1);
  assert.equal(expanded[1].expanded, false);

  const deep = flattenTree(tree, new Set(["root-a", "child-b"]));
  assert.equal(deep[3].key, "grand");
  assert.equal(deep[3].depth, 2);
  assert.equal(deep[3].parent, "child-b");
});

test("toggle expanded is immutable and idempotent per key", () => {
  const original = new Set(["a"]);
  const added = toggleExpanded(original, "b");
  assert.deepEqual([...added].sort(), ["a", "b"]);
  assert.deepEqual([...original], ["a"]);
  const removed = toggleExpanded(added, "a");
  assert.deepEqual([...removed], ["b"]);
});

test("layout helpers clamp and measure", () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-5, 0, 3), 0);
  assert.equal(treeRowHeight(0), 30);
  assert.equal(treeRowHeight(9), 42);
  assert.equal(estimateListHeight(100, 20, 40), 2040);
  assert.equal(scrollToIndex(12, 24), 288);
  assert.equal(scrollToIndex(-2, 24), 0);
});

test("frame monitor captures deltas with a bounded ring", () => {
  const monitor = new FrameMonitor(4);
  assert.equal(monitor.record(0), null);
  assert.equal(monitor.record(10), 10);
  assert.equal(monitor.record(25), 15);
  assert.equal(monitor.record(30), 5);
  assert.equal(monitor.record(60), 30);
  assert.equal(monitor.record(70), 10);
  assert.equal(monitor.size, 4);
  assert.deepEqual(monitor.values(), [15, 5, 30, 10]);
  assert.equal(monitor.sample(0), 15);
  monitor.reset();
  assert.equal(monitor.size, 0);
});

test("frame statistics and tones", () => {
  assert.equal(percentile([1, 2, 3, 4], 0.5), 2.5);
  assert.equal(percentile([], 0.9), 0);
  const stats = summarizeFrames([8, 12, 16, 20], FRAME_BUDGET_MS);
  assert.equal(stats.samples, 4);
  assert.equal(stats.average, 14);
  assert.equal(stats.worst, 20);
  assert.equal(stats.tone, "warn");
  assert.equal(frameTone(4), "good");
  assert.equal(frameTone(30), "bad");
  assert.ok(formatFrameStats(stats).includes("p95"));
});

test("deferred graph chunks respect per-frame cost", () => {
  const tasks = Array.from({ length: 40 }, (_, index) =>
    graphNodeTask(`node-${index}`, 3),
  );
  const chunks = planChunks(tasks, 10);
  assert.equal(chunks.length, 14);
  assert.ok(chunks.every((chunk) => chunk.cost <= 9.001));
  assert.equal(chunks[0].index, 0);
  assert.equal(chunks[0].tasks.length, 3);
  assert.equal(projectTask(tasks[0]), "node-0:node-0:3");
  assert.equal(shouldDefer(121), true);
  assert.equal(shouldDefer(120), false);
});

test("deferred queue drains incrementally and can reset", () => {
  const queue = new DeferredQueue(10);
  queue.enqueue(graphNodeTask("a", 4));
  queue.enqueueAll([graphNodeTask("b", 4), graphNodeTask("c", 4)]);
  assert.equal(queue.remaining, 3);
  const first = queue.take();
  assert.equal(first?.tasks.length, 2);
  assert.equal(queue.remaining, 1);
  assert.equal(queue.done, false);
  assert.equal(queue.drain().length, 1);
  assert.equal(queue.done, true);
  assert.equal(queue.take(), null);
  queue.reset();
  assert.equal(queue.remaining, 0);
});

test("freshness reflects generation lag and wall lag", () => {
  const fresh = buildFreshness(10, 10, 100, 104);
  assert.equal(fresh.stale, false);
  assert.equal(freshnessTone(fresh), "good");
  assert.equal(freshnessLabel(fresh), "fresh · 4.0s");
  assert.equal(shouldRefresh(fresh), false);

  const stale = buildFreshness(12, 10, 100, 101);
  assert.equal(stale.stale, true);
  assert.equal(freshnessLabel(stale), "2 generations behind");
  assert.equal(freshnessTone(stale), "bad");
  assert.equal(shouldRefresh(stale), true);

  const old = buildFreshness(4, 4, 0, 40);
  assert.equal(old.stale, true);
  assert.equal(freshnessTone(old), "bad");
});
