import assert from "node:assert/strict";
import test from "node:test";

import { ApiClientError, V3Client } from "../src/v3/apiClient";
import {
  clearRegistries,
  listCommands,
  listFeatures,
  searchCommands,
} from "../src/v3/registry";
import { AutomationClient } from "../src/features/automation/client";
import {
  compileDag,
  connectSteps,
  dependencyGraph,
  detectCycles,
  edgesFor,
  layoutDag,
  nextReady,
  parallelLayers,
  topologicalOrder,
} from "../src/features/automation/dag";
import {
  DEFAULT_RULE,
  expand,
  humanize,
  nextOccurrence,
  validateRule,
} from "../src/features/automation/recurrence";
import { registerAutomation } from "../src/features/automation/register";
import {
  actionForKey,
  createRunner,
  currentStep,
  runnerProgress,
  runnerReducer,
} from "../src/features/automation/runner";
import {
  asTrace,
  diffRuns,
  diffTraces,
  timeline,
  traceSummary,
  traceVerdict,
} from "../src/features/automation/trace";
import type {
  DryRunTrace,
  MutationResult,
  Playbook,
  RunRecord,
  StepDef,
} from "../src/features/automation/types";
import {
  collectPlaceholders,
  interpolate,
  resolveInputs,
  safeValues,
  validateVariableValues,
  variableIssuesByKey,
} from "../src/features/automation/variables";

function envelope<T>(data: T): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: { request_id: "req_test", api_version: "3.0" },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function steps(): StepDef[] {
  return [
    {
      id: "a",
      title: "Capture",
      kind: "create_note",
      inputs: { title: "Note" },
    },
    {
      id: "b",
      title: "Find",
      kind: "create_finding",
      depends_on: ["a"],
      inputs: { title: "Finding" },
    },
    {
      id: "c",
      title: "Attach",
      kind: "attach_evidence",
      depends_on: ["b"],
      inputs: { evidence_ref: "evidence:e1", target_ref: "finding:f1" },
    },
    {
      id: "d",
      title: "Emit",
      kind: "emit_event",
      depends_on: ["c"],
      inputs: { event_kind: "automation.done" },
    },
  ];
}

function playbook(): Playbook {
  return {
    id: "pb",
    title: "Playbook",
    variables: [
      { key: "target", kind: "entity_ref", required: true },
      { key: "count", kind: "number", default: 2, minimum: 1, maximum: 5 },
    ],
    steps: steps(),
  };
}

function trace(): DryRunTrace {
  const result: MutationResult = {
    intent: {
      step_id: "a",
      kind: "create_note",
      target: "note:auto_a_note",
      payload: { title: "Note" },
      key: "key-a",
      inverse: { action: "delete" },
    },
    ref: "note:auto_a_note",
    applied: false,
  };
  return {
    playbook_ref: "playbook:pb",
    mode: "dry_run",
    entries: [
      {
        index: 0,
        step_id: "a",
        status: "planned",
        kind: "create_note",
        message: "Planned (no write)",
        result,
        chain: "chain-a",
      },
      {
        index: 1,
        step_id: "b",
        status: "skipped",
        kind: "create_finding",
        message: "Skipped",
        chain: "chain-b",
      },
    ],
    variables: { target: "target:t1" },
    digest: "chain-b",
    writes: 0,
    input_fingerprint: "fp-1",
    state_digest: "state-1",
  };
}

test("dependency graph normalizes and detects cycles", () => {
  const graph = dependencyGraph([
    { id: "a", title: "A", kind: "create_note", depends_on: ["a", "b", "b"] },
    { id: "b", title: "B", kind: "create_note" },
  ]);
  assert.deepEqual(graph, { a: ["b"], b: [] });
  assert.deepEqual(detectCycles(graph), []);
  const cyclic: Record<string, string[]> = {
    a: ["b"],
    b: ["c"],
    c: ["a"],
    d: [],
  };
  const found = detectCycles(cyclic);
  assert.equal(found.length, 1);
  assert.equal(found[0]?.[0], found[0]?.at(-1));
  assert.throws(() => topologicalOrder(cyclic), /cycle/);
});

test("topological order and layers are stable", () => {
  const graph = dependencyGraph(steps());
  assert.deepEqual(topologicalOrder(graph), ["a", "b", "c", "d"]);
  assert.deepEqual(parallelLayers(graph), [["a"], ["b"], ["c"], ["d"]]);
  const independent = dependencyGraph([
    { id: "a", title: "A", kind: "create_note" },
    { id: "b", title: "B", kind: "create_note" },
    { id: "c", title: "C", kind: "create_note", depends_on: ["a", "b"] },
  ]);
  assert.deepEqual(parallelLayers(independent), [["a", "b"], ["c"]]);
  assert.deepEqual(nextReady(["a", "b", "c"], independent, ["a"]), ["b"]);
});

test("compileDag reports duplicates, missing dependencies and cycles", () => {
  const valid = compileDag(steps());
  assert.equal(valid.ok, true);
  assert.deepEqual(valid.order, ["a", "b", "c", "d"]);
  assert.deepEqual(valid.critical_path, ["a", "b", "c", "d"]);
  assert.equal(valid.depth["d"], 4);
  assert.equal(valid.issues.length, 0);

  const broken = compileDag([
    { id: "a", title: "A", kind: "create_note", depends_on: ["b"] },
    { id: "b", title: "B", kind: "create_note", depends_on: ["a"] },
    { id: "a", title: "A2", kind: "create_note", depends_on: ["ghost"] },
  ]);
  assert.equal(broken.ok, false);
  assert.deepEqual(broken.duplicates, ["a"]);
  assert.deepEqual(broken.missing, ["ghost"]);
  assert.ok(broken.cycles.length > 0);
  assert.ok(broken.issues.some((item) => item.code === "cycle_detected"));
});

test("connectSteps rejects cycles without mutating input", () => {
  const original = steps();
  const accepted = connectSteps(original, "a", "d");
  assert.equal(accepted.accepted, true);
  assert.deepEqual(original[3]?.depends_on, ["c"]);
  assert.deepEqual(accepted.steps[3]?.depends_on, ["c", "a"]);

  const rejected = connectSteps(original, "a", "a");
  assert.equal(rejected.accepted, false);
  assert.equal(rejected.problem?.code, "self_dependency");
  const loop = connectSteps(original, "d", "a");
  assert.equal(loop.accepted, false);
  assert.equal(loop.problem?.code, "cycle_detected");
  const unknown = connectSteps(original, "ghost", "a");
  assert.equal(unknown.problem?.code, "unknown_step");
});

test("layout and edges are deterministic for the DAG editor", () => {
  const layout = layoutDag(steps());
  assert.equal(layout.length, 4);
  assert.deepEqual(
    layout.map((node) => node.column),
    [0, 1, 2, 3],
  );
  assert.deepEqual(
    layout.map((node) => node.row),
    [0, 0, 0, 0],
  );
  assert.deepEqual(edgesFor(steps()), [
    { from: "a", to: "b" },
    { from: "b", to: "c" },
    { from: "c", to: "d" },
  ]);
});

test("variable validation coerces typed inputs and reports issues", () => {
  const definitions = playbook().variables;
  const ok = validateVariableValues(definitions, {
    target: "target:t1",
    count: "4",
  });
  assert.equal(ok.ok, true);
  assert.equal(ok.values["count"], 4);
  const problems = validateVariableValues(definitions, {
    target: "bad",
    count: 99,
  });
  assert.equal(problems.ok, false);
  const codes = problems.issues.map((item) => item.code);
  assert.ok(codes.includes("invalid_ref"));
  assert.ok(codes.includes("out_of_range"));
  const byKey = variableIssuesByKey(problems.issues);
  assert.ok(byKey["target"]);
  assert.equal(
    validateVariableValues(definitions, {}).issues[0]?.code,
    "missing_variable",
  );
});

test("interpolation preserves types and supports step outputs", () => {
  const context = {
    vars: { count: 7, nested: { key: "v" } },
    steps: { a: { ref: "note:a" } },
  };
  assert.equal(interpolate("{{ count }}", context), 7);
  assert.equal(interpolate("n={{ count }}", context), "n=7");
  assert.equal(interpolate("{{ vars.nested.key }}", context), "v");
  assert.equal(interpolate("{{ steps.a.ref }}", context), "note:a");
  assert.throws(() => interpolate("{{ missing }}", context), /Unresolved/);
  assert.equal(interpolate("{{ missing }}", context, false), "");
  assert.deepEqual(collectPlaceholders("{{ a }} {{ b }} {{ a }}"), ["a", "b"]);
  assert.deepEqual(
    resolveInputs(
      { title: "{{ steps.a.ref }}", items: ["{{ count }}", 2] },
      context,
    ),
    { title: "note:a", items: [7, 2] },
  );
});

test("secret variable values are masked in safe views", () => {
  const resolution = validateVariableValues(
    [
      { key: "token", kind: "text", secret: true },
      { key: "public", kind: "text", default: "ok" },
    ],
    { token: "s3cr3t" },
  );
  assert.equal(resolution.values["token"], "s3cr3t");
  assert.deepEqual(safeValues(resolution), { token: "***", public: "ok" });
  assert.ok(!JSON.stringify(safeValues(resolution)).includes("s3cr3t"));
});

test("trace timeline, summary, verdict and diffs", () => {
  const current = trace();
  const items = timeline(current);
  assert.deepEqual(
    items.map((item) => item.step_id),
    ["a", "b"],
  );
  assert.equal(items[0]?.tone, "info");
  assert.equal(items[1]?.tone, "warn");
  assert.equal(items[0]?.target, "note:auto_a_note");
  assert.equal(traceSummary(current)["mutations"], 1);
  assert.equal(traceSummary(current)["writes"], 0);
  assert.equal(traceVerdict(current), "clean");

  const changed: DryRunTrace = {
    ...current,
    entries: [
      { ...current.entries[0]!, status: "executed", message: "Applied" },
      current.entries[1]!,
    ],
    input_fingerprint: "fp-2",
  };
  assert.equal(traceVerdict(changed), "attention");
  const differences = diffTraces(current, changed);
  assert.ok(differences.some((item) => item.path === "input_fingerprint"));
  assert.ok(
    differences.some((item) => item.path.includes("steps.a[0].status")),
  );
  assert.deepEqual(diffTraces(current, current), []);

  const base: RunRecord = {
    id: "run-1",
    playbook_ref: "playbook:pb",
    status: "completed",
    mode: "live",
    started_at: 1,
    finished_at: 2,
    trace: current.entries,
    variables: {},
    trace_digest: "d1",
    state_digest: "s1",
    rollback_of: "",
    input_fingerprint: "fp-1",
  };
  const rolled = {
    ...base,
    status: "rolled_back" as const,
    trace_digest: "d2",
  };
  assert.deepEqual(diffRuns(base, base), []);
  assert.ok(diffRuns(base, rolled).some((item) => item.path === "status"));
  assert.equal(asTrace(base).digest, "d1");
});

test("recurrence expansion honors interval, weekday, count and month clamp", () => {
  const daily = { ...DEFAULT_RULE, interval: 2, count: 3 };
  const found = expand(daily, 0, 90 * 86_400_000, 10);
  assert.equal(found.length, 3);
  assert.equal(found[1]! - found[0]!, 2 * 86_400_000);
  assert.deepEqual(expand(daily, 0, 0), []);
  assert.equal(nextOccurrence(daily, found[0]!), found[1]);
  assert.deepEqual(
    expand(
      { ...DEFAULT_RULE, frequency: "weekly", by_weekday: [0, 2] },
      2 * 86_400_000,
      30 * 86_400_000,
      6,
    ).map((value) => (new Date(value).getUTCDay() + 6) % 7),
    [0, 2, 0, 2, 0, 2],
  );
  const monthly = expand(
    { ...DEFAULT_RULE, frequency: "monthly", by_month_day: 31 },
    0,
    200 * 86_400_000,
    12,
  );
  assert.ok(
    monthly.every((value) =>
      [28, 30, 31].includes(new Date(value).getUTCDate()),
    ),
  );
  assert.ok(
    humanize({
      ...DEFAULT_RULE,
      frequency: "weekly",
      by_weekday: [0, 2],
    }).includes("Mon"),
  );
  assert.equal(
    validateRule({ ...DEFAULT_RULE, interval: 0 })[0]?.code,
    "invalid_interval",
  );
  assert.equal(validateRule(DEFAULT_RULE).length, 0);
});

test("guided runner walks steps and respects dependencies", () => {
  let state = createRunner(steps());
  assert.deepEqual(state.order, ["a", "b", "c", "d"]);
  assert.equal(currentStep(state)?.id, "a");
  assert.deepEqual(runnerProgress(state), { done: 0, total: 4, percent: 0 });

  state = runnerReducer(state, { type: "next" });
  assert.equal(currentStep(state)?.id, "b");
  state = runnerReducer(state, { type: "previous" });
  assert.equal(currentStep(state)?.id, "a");
  state = runnerReducer(state, { type: "toggle" });
  assert.equal(state.completed.length, 1);
  assert.equal(currentStep(state)?.id, "a");
  state = runnerReducer(state, { type: "last" });
  assert.equal(currentStep(state)?.id, "d");
  const before = state;
  state = runnerReducer(state, { type: "toggle" });
  assert.equal(state, before, "blocked step cannot be completed");
  state = runnerReducer(state, { type: "first" });
  state = runnerReducer(state, { type: "reset" });
  assert.deepEqual(state.completed, []);
  assert.ok(actionForKey("ArrowRight"));
  assert.equal(actionForKey("Home")?.type, "first");
  assert.equal(actionForKey("q"), null);
});

test("automation client sends V3 envelopes to every route", async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    calls.push({
      url: String(input),
      body: JSON.parse(String(init.body ?? "{}")) as Record<string, unknown>,
    });
    return envelope({ ok: true });
  }) as typeof globalThis.fetch;
  const client = new AutomationClient({
    client: new V3Client({ fetch: fetchImpl }),
  });
  const pb = playbook();
  await client.validate(pb, { target: "target:t" });
  await client.compile(pb);
  await client.connect(pb, "d", "a");
  await client.dryRun(pb, { target: "target:t" });
  await client.run(pb, { target: "target:t" });
  await client.runs("playbook:pb");
  await client.runGet("run-1");
  await client.replay("run-1");
  await client.rollback("run-1");
  await client.recurrence(DEFAULT_RULE, 0, 1000);
  await client.diff("run-1", "run-2");
  assert.deepEqual(
    calls.map((call) => call.url),
    [
      "/api/v3/automation/validate",
      "/api/v3/automation/compile",
      "/api/v3/automation/connect",
      "/api/v3/automation/dry_run",
      "/api/v3/automation/run",
      "/api/v3/automation/runs",
      "/api/v3/automation/run_get",
      "/api/v3/automation/replay",
      "/api/v3/automation/rollback",
      "/api/v3/automation/recurrence",
      "/api/v3/automation/diff",
    ],
  );
  assert.deepEqual(calls[2]?.body, { playbook: pb, source: "d", target: "a" });
});

test("automation client surfaces typed V3 errors", async () => {
  const fetchImpl = (async () =>
    new Response(
      JSON.stringify({
        error: {
          code: "invalid_request",
          message: "bad playbook",
          field: "playbook",
          retryable: false,
          context: {},
        },
        meta: { request_id: "r", api_version: "3.0" },
      }),
      { status: 400 },
    )) as typeof globalThis.fetch;
  const client = new AutomationClient({
    client: new V3Client({ fetch: fetchImpl }),
  });
  await assert.rejects(
    () => client.dryRun(playbook(), {}),
    (error: unknown) =>
      error instanceof ApiClientError && error.code === "invalid_request",
  );
});

test("automation registers features and commands additively", () => {
  clearRegistries();
  registerAutomation();
  registerAutomation();
  assert.equal(
    listFeatures().filter((feature) => feature.id === "automation").length,
    1,
  );
  assert.equal(
    listFeatures().find((feature) => feature.id === "automation")?.order,
    60,
  );
  assert.ok(
    listCommands().some((command) => command.id === "automation.focus"),
  );
  assert.equal(
    searchCommands("dry run").some(
      (command) => command.id === "automation.dry-run-hint",
    ),
    true,
  );
  clearRegistries();
});
