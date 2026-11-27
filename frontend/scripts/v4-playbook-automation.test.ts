/** Node tests for the v4 playbook automation frontend slice. */

import assert from "node:assert/strict";
import test from "node:test";

import {
  PlaybookAutomationClient,
  V4ApiError,
  type PlaybookDagV4,
  type RunRecordV4,
  type ScheduleV4,
} from "../src/features/playbook-automation/client";
import {
  canvasSummary,
  traceRows,
} from "../src/features/playbook-automation/DagCanvas";
import {
  canDryRun,
  edgeSegments,
  initialPlaybookAutomationState,
  layoutDag,
  reducePlaybookAutomation,
  scheduleLabel,
  selectedNode,
  statusTone,
  topologicalOrder,
  traceSummary,
  visibleRuns,
} from "../src/features/playbook-automation/state";

function dag(): PlaybookDagV4 {
  return {
    id: "pb-1",
    name: "Chain",
    description: "data only",
    nodes: [
      { id: "a", label: "A", kind: "setup", depends_on: [], params: {} },
      {
        id: "b",
        label: "B",
        kind: "collect",
        depends_on: ["a"],
        params: { target: "x" },
      },
      { id: "c", label: "C", kind: "report", depends_on: ["b"], params: {} },
    ],
    edges: [
      { source: "a", target: "b", label: "" },
      { source: "b", target: "c", label: "" },
    ],
  };
}

function run(status: RunRecordV4["status"], id = "run-1"): RunRecordV4 {
  return {
    id,
    playbook_id: "pb-1",
    status,
    started_at: "2026-01-05T09:30:00.000Z",
    finished_at: "",
    trace: [],
    trigger: "manual",
  };
}

function schedule(): ScheduleV4 {
  return {
    id: "s-1",
    playbook_id: "pb-1",
    frequency: "daily",
    interval_minutes: 60,
    minute: 30,
    hour: 7,
    day_of_week: [],
    day_of_month: 1,
    next_run: "2026-01-06T07:30:00.000Z",
    enabled: true,
  };
}

test("initial state is deterministic and inert", () => {
  const state = initialPlaybookAutomationState(dag());
  assert.equal(state.dag.nodes.length, 3);
  assert.equal(state.selectedNodeId, "a");
  assert.equal(state.validation, null);
  assert.deepEqual(state.trace, []);
  assert.deepEqual(state.runs, []);
  assert.equal(state.busy, false);
  assert.equal(canDryRun(state), true);
  assert.deepEqual(state.dag.nodes[1]?.params, { target: "x" });
});

test("topological order breaks ties lexicographically", () => {
  const tied = dag();
  tied.nodes = [
    { id: "z", label: "Z", kind: "setup", depends_on: [], params: {} },
    { id: "a", label: "A", kind: "setup", depends_on: [], params: {} },
    { id: "m", label: "M", kind: "setup", depends_on: [], params: {} },
  ];
  tied.edges = [];
  assert.deepEqual(topologicalOrder(tied), ["a", "m", "z"]);
  assert.deepEqual(topologicalOrder(dag()), ["a", "b", "c"]);
});

test("cycle does not produce a full topological order", () => {
  const cyclic = dag();
  cyclic.nodes = [
    { id: "a", label: "A", kind: "setup", depends_on: ["b"], params: {} },
    { id: "b", label: "B", kind: "collect", depends_on: ["a"], params: {} },
  ];
  cyclic.edges = [];
  assert.deepEqual(topologicalOrder(cyclic), []);
});

test("layout and edge segments are deterministic", () => {
  const cells = layoutDag(dag());
  assert.deepEqual(
    cells.map((cell) => [cell.id, cell.column, cell.row]),
    [
      ["a", 0, 0],
      ["b", 1, 0],
      ["c", 2, 0],
    ],
  );
  const segments = edgeSegments(dag(), cells);
  assert.deepEqual(
    segments.map((segment) => [segment.id, segment.column, segment.span]),
    [
      ["a>b", 1, 1],
      ["b>c", 2, 1],
    ],
  );
  assert.equal(segments[0]?.label, "A to B");
});

test("reducer handles selection, validation and trace actions", () => {
  let state = initialPlaybookAutomationState(dag());
  state = reducePlaybookAutomation(state, { type: "select-node", id: "b" });
  assert.equal(selectedNode(state)?.label, "B");
  state = reducePlaybookAutomation(state, {
    type: "set-validation",
    report: {
      dag_id: "pb-1",
      ok: true,
      order: ["a", "b", "c"],
      layers: [["a"], ["b"], ["c"]],
      depth: {},
      critical_path: [],
      cycles: [],
      missing: [],
      duplicates: [],
      issues: [],
    },
  });
  assert.equal(state.validation?.ok, true);
  state = reducePlaybookAutomation(state, {
    type: "set-trace",
    trace: [
      { node_id: "a", status: "succeeded", detail: "ok", duration_ms: 10 },
      { node_id: "b", status: "failed", detail: "no", duration_ms: 20 },
      { node_id: "c", status: "skipped", detail: "blocked", duration_ms: 0 },
    ],
  });
  const summary = traceSummary(state.trace);
  assert.equal(summary.total, 3);
  assert.equal(summary.failed, 1);
  assert.equal(summary.durationMs, 30);
  assert.equal(summary.maxDurationMs, 20);
  assert.deepEqual(
    traceRows(state.trace).map((row) => row.percent),
    [50, 100, 0],
  );
});

test("reducer adds, updates and removes nodes", () => {
  let state = initialPlaybookAutomationState(dag());
  state = reducePlaybookAutomation(state, {
    type: "add-node",
    node: {
      id: "d",
      label: "D",
      kind: "notify",
      depends_on: ["c"],
      params: {},
    },
  });
  assert.equal(state.dag.nodes.length, 4);
  assert.equal(state.selectedNodeId, "d");
  state = reducePlaybookAutomation(state, {
    type: "add-node",
    node: {
      id: "d",
      label: "D2",
      kind: "notify",
      depends_on: ["c"],
      params: {},
    },
  });
  assert.equal(state.dag.nodes.length, 4);
  assert.equal(selectedNode(state)?.label, "D2");
  state = reducePlaybookAutomation(state, { type: "remove-node", id: "b" });
  assert.equal(state.dag.nodes.length, 3);
  assert.equal(state.dag.edges.length, 0);
  assert.equal(selectedNode(state)?.label, "D2");
});

test("reducer toggles dependencies without mutating input", () => {
  const original = initialPlaybookAutomationState(dag());
  let state = reducePlaybookAutomation(original, {
    type: "toggle-dependency",
    from: "c",
    to: "a",
  });
  assert.deepEqual(state.dag.nodes[0]?.depends_on, ["c"]);
  assert.deepEqual(original.dag.nodes[0]?.depends_on, []);
  state = reducePlaybookAutomation(state, {
    type: "toggle-dependency",
    from: "c",
    to: "a",
  });
  assert.deepEqual(state.dag.nodes[0]?.depends_on, []);
  assert.equal(
    reducePlaybookAutomation(state, {
      type: "toggle-dependency",
      from: "a",
      to: "a",
    }),
    state,
  );
});

test("reducer filters runs and pages schedules", () => {
  let state = initialPlaybookAutomationState(dag());
  state = reducePlaybookAutomation(state, {
    type: "set-runs",
    runs: [run("succeeded"), run("failed", "run-2")],
  });
  state = reducePlaybookAutomation(state, {
    type: "set-filter",
    status: "failed",
  });
  assert.deepEqual(
    visibleRuns(state).map((item) => item.id),
    ["run-2"],
  );
  assert.equal(state.page, 1);
  state = reducePlaybookAutomation(state, { type: "set-page", page: 0 });
  assert.equal(state.page, 1);
  state = reducePlaybookAutomation(state, { type: "set-page", page: 4 });
  assert.equal(state.page, 4);
  state = reducePlaybookAutomation(state, {
    type: "update-schedule",
    schedule: schedule(),
  });
  assert.equal(state.schedules.length, 1);
  state = reducePlaybookAutomation(state, {
    type: "update-schedule",
    schedule: { ...schedule(), minute: 45 },
  });
  assert.equal(state.schedules.length, 1);
  assert.equal(state.schedules[0]?.minute, 45);
  state = reducePlaybookAutomation(state, { type: "set-busy", busy: true });
  assert.equal(canDryRun(state), false);
  state = reducePlaybookAutomation(state, {
    type: "set-error",
    error: "blocked",
  });
  assert.equal(state.error, "blocked");
  state = reducePlaybookAutomation(state, { type: "reset" });
  assert.equal(state.error, "");
  assert.equal(state.busy, false);
  assert.equal(state.schedules.length, 0);
});

test("labels and tones are stable across the UI", () => {
  assert.equal(scheduleLabel(schedule()), "Daily at 07:30");
  assert.equal(
    scheduleLabel({
      ...schedule(),
      frequency: "interval",
      interval_minutes: 15,
    }),
    "Every 15 minutes",
  );
  assert.equal(
    scheduleLabel({ ...schedule(), frequency: "weekly", day_of_week: [0, 2] }),
    "Weekly on 0, 2 at 07:30",
  );
  assert.equal(
    scheduleLabel({ ...schedule(), frequency: "monthly", day_of_month: 31 }),
    "Monthly on day 31 at 07:30",
  );
  assert.equal(statusTone("succeeded"), "good");
  assert.equal(statusTone("failed"), "bad");
  assert.equal(statusTone("running"), "info");
  assert.equal(statusTone("cancelled"), "warn");
  assert.equal(statusTone("pending"), "neutral");
});

test("canvas summary describes the current graph", () => {
  let state = initialPlaybookAutomationState(dag());
  state = reducePlaybookAutomation(state, {
    type: "set-trace",
    trace: [
      { node_id: "a", status: "succeeded", detail: "ok", duration_ms: 4 },
    ],
  });
  const summary = canvasSummary(state);
  assert.equal(summary.nodes, 3);
  assert.equal(summary.edges, 2);
  assert.equal(summary.steps, 1);
  assert.equal(summary.order, "a -> b -> c");
});

test("client decodes success envelopes and encodes queries", async () => {
  const seen: string[] = [];
  let pageOptions: { page?: number; pageSize?: number } = {};
  const client = new PlaybookAutomationClient({
    get: async (
      url: string,
      options: { page?: number; pageSize?: number } = {},
    ) => {
      seen.push(url);
      pageOptions = options;
      return {
        data: { items: [dag()], total: 1 },
        meta: { request_id: "r", version: "v4", page: 2, page_size: 1 },
      };
    },
    post: async () => dag(),
  } as never);
  const result = await client.listRuns({
    playbookId: "pb-1",
    status: "running",
    page: 2,
    pageSize: 1,
  });
  assert.equal(result.data.total, 1);
  assert.equal(result.meta.version, "v4");
  assert.match(seen[0] ?? "", /playbook_id=pb-1/);
  assert.match(seen[0] ?? "", /status=running/);
  assert.equal(pageOptions.page, 2);
  assert.equal(pageOptions.pageSize, 1);
});

test("client throws structured errors and posts dry runs", async () => {
  let posted: unknown;
  const client = new PlaybookAutomationClient({
    get: async () => {
      throw new V4ApiError("forbidden", "no automate", ["cap"]);
    },
    post: async (_url: string, body?: unknown) => {
      posted = body;
      return {
        dag_id: "pb-1",
        status: "succeeded",
        trace: [],
        digest: "d",
        waves: 3,
      };
    },
  } as never);
  await assert.rejects(
    () => client.describe(),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "forbidden",
  );
  const result = await client.dryRun(dag(), ["b"]);
  assert.equal(result.status, "succeeded");
  assert.deepEqual(posted, { dag: dag(), fail_nodes: ["b"] });
});
