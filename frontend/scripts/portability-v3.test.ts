import assert from "node:assert/strict";
import test from "node:test";

import {
  PortabilityClient,
  bundleCreateRequest,
  compact,
  createPortabilityClient,
  previewRequest,
  resolveRequest,
  transferChunkRequest,
  transferStartRequest,
} from "../src/features/portability/client";
import {
  REASON_CODES,
  RESOLUTIONS,
  WIZARD_LABELS,
  actionTone,
  advanceWizard,
  applyResolution,
  buildWizardSteps,
  canCancel,
  canResume,
  changesByAction,
  clamp,
  conflictCounts,
  currentStep,
  defaultPlan,
  diffRows,
  failedChecks,
  filterConflicts,
  formatBytes,
  formatTimestamp,
  groupConflicts,
  overlappingFields,
  passphraseScore,
  progressLabel,
  progressPercent,
  receiptVerdict,
  reasonHelp,
  reasonLabel,
  reasonTone,
  renderValue,
  resolutionLabel,
  resolutionTone,
  shortDigest,
  stableSortConflicts,
  strengthLabel,
  strengthTone,
  suggestResolution,
  summarizeDryRun,
  toErrorMessage,
  truncate,
  unresolvedCount,
  validatePlan,
  vectorRelationLabel,
  vectorSummary,
  vectorTone,
  wizardPercent,
} from "../src/features/portability/pure";
import {
  initialPortabilityState,
  portabilityReducer,
  selectNotice,
  selectProgress,
  selectReadyToRun,
  selectReceipt,
  selectStep,
  selectUnresolved,
} from "../src/features/portability/state";
import type {
  BundlePlan,
  ConflictView,
  DiffRow,
  DryRunView,
  ProgressView,
  ReceiptView,
  VectorView,
} from "../src/features/portability/types";

function plan(overrides: Partial<BundlePlan> = {}): BundlePlan {
  return {
    ...defaultPlan(),
    label: "Test bundle",
    passphrase: "Str0ng!Passphrase",
    ...overrides,
  };
}

function diff(
  field: string,
  base: unknown,
  local: unknown,
  remote: unknown,
): DiffRow {
  return {
    field,
    base,
    local,
    remote,
    localChanged: local !== base,
    remoteChanged: remote !== base,
    overlap: local !== base && remote !== base,
  };
}

function conflict(overrides: Partial<ConflictView> = {}): ConflictView {
  return {
    ref: "note:1",
    family: "note",
    reason: "field_both_edited",
    reasonDescription: "Both devices edited the same field.",
    severity: "error",
    message: "note:1: both devices edited the same field",
    fields: [diff("title", "Base", "Local", "Remote")],
    suggestion: "unresolved",
    resolution: "unresolved",
    detail: "",
    ...overrides,
  };
}

function dryRun(overrides: Partial<DryRunView> = {}): DryRunView {
  return {
    operation: "import",
    valid: true,
    headline: "2 entities ready to import",
    changes: [
      {
        ref: "note:1",
        action: "update",
        family: "note",
        title: "Note",
        fields: ["title"],
      },
      {
        ref: "note:2",
        action: "create",
        family: "note",
        title: "New",
        fields: [],
      },
      {
        ref: "note:3",
        action: "unchanged",
        family: "note",
        title: "Same",
        fields: [],
      },
    ],
    conflicts: [],
    warnings: [],
    counts: { entities: 3 },
    ...overrides,
  };
}

function progress(overrides: Partial<ProgressView> = {}): ProgressView {
  return {
    transferId: "xfer_1",
    bundleId: "bundle_1",
    phase: "active",
    percent: 50,
    receivedChunks: 2,
    totalChunks: 4,
    missingChunks: [2, 3],
    canCancel: true,
    canResume: true,
    ...overrides,
  };
}

function receipt(overrides: Partial<ReceiptView> = {}): ReceiptView {
  return {
    receiptId: "receipt_1",
    bundleId: "bundle_1",
    device: "alpha",
    verifiedAt: 1_700_000_000,
    status: "verified",
    ok: true,
    digest: "a".repeat(64),
    checks: [
      {
        name: "manifest",
        passed: true,
        detail: "manifest v3.1",
        code: "MANIFEST_OK",
      },
      { name: "tag", passed: true, detail: "HMAC verified", code: "MAC_OK" },
    ],
    ...overrides,
  };
}

function vector(): VectorView {
  return {
    local: { alpha: 2 },
    remote: { beta: 1 },
    relation: "concurrent",
    relationLabel: "Independent edits",
    merged: { alpha: 2, beta: 1 },
    distance: 2,
    concurrent: true,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope<T>(data: T): { data: T; meta: Record<string, unknown> } {
  return { data, meta: { request_id: "req_test", api_version: "3.0" } };
}

test("wizard steps start at source with six ordered stages", () => {
  const steps = buildWizardSteps();
  assert.equal(steps.length, 6);
  assert.equal(steps[0].id, "source");
  assert.equal(steps[0].status, "active");
  assert.equal(steps[1].status, "pending");
  assert.deepEqual(
    steps.map((step) => step.id),
    WIZARD_LABELS.map((step) => step.id),
  );
});

test("advance wizard completes prior steps and activates the target", () => {
  const steps = advanceWizard(buildWizardSteps(), 2);
  assert.deepEqual(
    steps.map((step) => step.status),
    ["complete", "complete", "active", "pending", "pending", "pending"],
  );
  assert.equal(wizardPercent(steps), 33);
  assert.equal(currentStep(steps)?.id, "dry-run");
});

test("advance wizard ignores out-of-range indexes and marks errors", () => {
  const original = buildWizardSteps();
  assert.equal(advanceWizard(original, -1), original);
  assert.equal(advanceWizard(original, 99), original);
  const errored = advanceWizard(original, 1, "error");
  assert.equal(errored[1].status, "error");
});

test("default plan enables dry runs and four entity families", () => {
  const value = defaultPlan();
  assert.equal(value.deviceId, "local");
  assert.equal(value.dryRun, true);
  assert.equal(value.includeLinks, true);
  assert.equal(value.scope.length, 4);
});

test("validate plan reports missing label, scope, and weak key", () => {
  const problems = validatePlan({
    ...defaultPlan(),
    label: "",
    passphrase: "a",
    scope: [],
  });
  assert.equal(problems.length, 3);
  assert.ok(problems[0].includes("label"));
  assert.ok(problems[1].includes("passphrase"));
  assert.ok(problems[2].includes("family"));
});

test("validate plan accepts a complete plan", () => {
  assert.deepEqual(validatePlan(plan()), []);
});

test("passphrase score mirrors the deterministic strength policy", () => {
  assert.equal(passphraseScore(""), 0);
  assert.equal(passphraseScore("aaaaaaaaaaaa"), 1);
  assert.ok(passphraseScore("Abcdefgh1234") >= 2);
  assert.equal(passphraseScore("Str0ng!Passphrase#2026"), 4);
  assert.equal(strengthLabel(0), "Empty");
  assert.equal(strengthLabel(4), "Excellent");
  assert.equal(strengthTone(0), "bad");
  assert.equal(strengthTone(4), "good");
});

test("numeric formatting helpers handle edge cases", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(1024), "1.0 KB");
  assert.equal(formatBytes(1024 * 1024), "1.0 MB");
  assert.equal(formatBytes(-1), "—");
  assert.equal(clamp(120, 0, 100), 100);
  assert.equal(clamp(-5, 0, 100), 0);
  assert.equal(truncate("  many   spaces  here ", 10), "many spac…");
  assert.equal(shortDigest("abcdefghijklmnopqrstuvwxyz", 8), "abcdefgh…");
  assert.equal(shortDigest("short", 8), "short");
  assert.equal(formatTimestamp(0), "unknown");
  assert.equal(formatTimestamp(1_700_000_000).endsWith("UTC"), true);
});

test("reason catalog exposes stable codes, labels, and tones", () => {
  assert.equal(REASON_CODES.length, 10);
  assert.ok(REASON_CODES.includes("delete_modify"));
  assert.equal(reasonLabel("field_both_edited"), "Same field edited twice");
  assert.equal(reasonLabel("custom_code"), "custom code");
  assert.ok(reasonHelp("delete_modify").includes("deleted"));
  assert.equal(reasonTone("concurrent_add"), "bad");
  assert.equal(reasonTone("schema_mismatch"), "warn");
  assert.equal(reasonTone("field_both_edited"), "info");
});

test("resolution labels and tones cover every choice", () => {
  assert.deepEqual(RESOLUTIONS, [
    "unresolved",
    "keep_local",
    "keep_remote",
    "merge_fields",
    "skip",
  ]);
  assert.equal(resolutionLabel("keep_local"), "Keep local");
  assert.equal(resolutionLabel("unknown"), "unknown");
  assert.equal(resolutionTone("unresolved"), "warn");
  assert.equal(resolutionTone("keep_remote"), "good");
  assert.equal(resolutionTone("skip"), "neutral");
});

test("vector view helpers explain causal relations", () => {
  const value = vector();
  assert.equal(
    vectorRelationLabel("concurrent"),
    "Independent edits on both sides",
  );
  assert.equal(vectorRelationLabel("left_ahead"), "Local history is ahead");
  assert.equal(vectorRelationLabel("custom"), "custom");
  assert.equal(vectorTone("concurrent"), "warn");
  assert.equal(vectorTone("equal"), "good");
  assert.equal(vectorTone("right_ahead"), "info");
  assert.ok(vectorSummary(value).includes("distance 2"));
  assert.equal(vectorSummary(null), "No vectors compared yet");
});

test("render value covers scalars, arrays, objects, and empties", () => {
  assert.equal(renderValue(null), "—");
  assert.equal(renderValue(undefined), "—");
  assert.equal(renderValue(7), "7");
  assert.equal(renderValue(["a", 2]), "a, 2");
  assert.equal(renderValue([]), "—");
  assert.equal(renderValue({ a: 1 }), '{"a":1}');
});

test("diff rows and overlapping fields come from conflict data", () => {
  const value = conflict({
    fields: [
      diff("title", "Base", "Local", "Remote"),
      diff("summary", "Same", "Same", "Changed"),
    ],
  });
  assert.deepEqual(
    diffRows(value).map((row) => row.field),
    ["title", "summary"],
  );
  assert.deepEqual(overlappingFields(value), ["title"]);
  assert.deepEqual(diffRows(null), []);
  assert.deepEqual(overlappingFields(null), []);
});

test("filter conflicts by query, reason, and resolution", () => {
  const items = [
    conflict({ ref: "note:1" }),
    conflict({ ref: "note:2", reason: "content_divergence" }),
    conflict({ ref: "finding:3", resolution: "keep_local" }),
  ];
  assert.equal(filterConflicts(items).length, 3);
  assert.equal(
    filterConflicts(items, { reason: "content_divergence" }).length,
    1,
  );
  assert.equal(filterConflicts(items, { unresolvedOnly: true }).length, 2);
  assert.equal(filterConflicts(items, { query: "finding" }).length, 1);
  assert.equal(filterConflicts(items, { query: "zzzz-not-present" }).length, 0);
});

test("group conflicts by reason code", () => {
  const groups = groupConflicts([
    conflict({ ref: "note:1", reason: "content_divergence" }),
    conflict({ ref: "note:2", reason: "field_both_edited" }),
    conflict({ ref: "note:3", reason: "content_divergence" }),
  ]);
  assert.equal(groups.length, 2);
  assert.equal(groups[0][0], "content_divergence");
  assert.equal(groups[0][1].length, 2);
  assert.deepEqual(conflictCounts(groups[0][1]), { content_divergence: 2 });
});

test("unresolved count and resolution application are immutable", () => {
  const items = [conflict({ ref: "note:1" }), conflict({ ref: "note:2" })];
  assert.equal(unresolvedCount(items), 2);
  const updated = applyResolution(items, "note:1", "keep_local");
  assert.equal(unresolvedCount(updated), 1);
  assert.equal(updated[0].resolution, "keep_local");
  assert.equal(items[0].resolution, "unresolved");
  assert.equal(applyResolution(items, "missing", "skip").length, 2);
});

test("suggest resolution honors strategy and conflict suggestion", () => {
  const value = conflict({ suggestion: "keep_remote" });
  assert.equal(suggestResolution(value, "keep_local"), "keep_local");
  assert.equal(suggestResolution(value, "keep_remote"), "keep_remote");
  assert.equal(suggestResolution(value, "skip"), "skip");
  assert.equal(suggestResolution(value, "merge_fields"), "merge_fields");
  assert.equal(suggestResolution(value, "manual"), "keep_remote");
  assert.equal(suggestResolution(conflict(), "manual"), "unresolved");
});

test("stable sort conflicts orders by reference first", () => {
  const sorted = stableSortConflicts([
    conflict({ ref: "note:9" }),
    conflict({ ref: "finding:1" }),
    conflict({ ref: "note:1" }),
  ]);
  assert.deepEqual(
    sorted.map((item) => item.ref),
    ["finding:1", "note:1", "note:9"],
  );
});

test("change actions have display tones", () => {
  assert.equal(actionTone("create"), "good");
  assert.equal(actionTone("delete"), "bad");
  assert.equal(actionTone("update"), "info");
  assert.equal(actionTone("unchanged"), "neutral");
});

test("dry-run summaries and change counts", () => {
  const report = dryRun();
  assert.ok(summarizeDryRun(report).includes("2 entities ready"));
  assert.deepEqual(changesByAction(report), {
    update: 1,
    create: 1,
    unchanged: 1,
  });
  const blocked = dryRun({ valid: false, conflicts: [conflict()] });
  assert.ok(summarizeDryRun(blocked).includes("conflicts to resolve"));
  assert.equal(summarizeDryRun(null).includes("dry preview"), true);
  assert.deepEqual(changesByAction(null), {});
});

test("progress helpers clamp, label, and gate controls", () => {
  assert.equal(progressPercent(1, 4), 25);
  assert.equal(progressPercent(4, 0), 100);
  assert.equal(progressPercent(200, 100), 100);
  const active = progress();
  assert.ok(progressLabel(active).includes("50%"));
  assert.equal(progressLabel(null), "No transfer in progress");
  assert.equal(
    progressLabel(progress({ phase: "complete" })),
    "Transfer complete and verified",
  );
  assert.equal(
    progressLabel(progress({ phase: "cancelled" })),
    "Transfer cancelled",
  );
  assert.equal(
    progressLabel(progress({ phase: "failed" })),
    "Transfer failed — resume to retry",
  );
  assert.equal(
    progressLabel(progress({ phase: "paused", percent: 25 })),
    "Paused at 25%",
  );
  assert.equal(canCancel(active), true);
  assert.equal(canCancel(progress({ phase: "complete" })), false);
  assert.equal(canCancel(null), false);
  assert.equal(canResume(progress({ phase: "paused" })), true);
  assert.equal(canResume(progress({ phase: "cancelled" })), false);
});

test("receipt verdicts and failed checks", () => {
  const verified = receipt();
  assert.ok(receiptVerdict(verified).includes("Verified on"));
  assert.equal(receiptVerdict(null), "Not verified yet");
  assert.deepEqual(failedChecks(verified), []);
  const broken = receipt({
    ok: false,
    checks: [
      { name: "tag", passed: false, detail: "bad", code: "MAC_MISMATCH" },
    ],
  });
  assert.equal(failedChecks(broken).length, 1);
  assert.ok(receiptVerdict(broken).includes("Verification failed"));
});

test("notice and error helpers", () => {
  assert.deepEqual(toErrorMessage(new Error("boom")), "boom");
  assert.deepEqual(toErrorMessage("plain"), "plain");
  assert.equal(toErrorMessage({}), "Unexpected portability error");
});

test("initial portability state is empty and idle", () => {
  const state = initialPortabilityState();
  assert.equal(state.stepIndex, 0);
  assert.equal(state.dryRun, null);
  assert.equal(state.conflicts.length, 0);
  assert.equal(state.busy, false);
  assert.equal(selectUnresolved(state), 0);
  assert.equal(selectReadyToRun(state), false);
  assert.equal(selectReceipt(state), null);
  assert.equal(selectProgress(state), null);
  assert.equal(selectNotice(state), null);
  assert.equal(selectStep(state)?.id, "source");
});

test("reducer updates plan, step, and busy state", () => {
  let state = initialPortabilityState();
  state = portabilityReducer(state, {
    type: "plan",
    value: { label: "Handoff" },
  });
  assert.equal(state.plan.label, "Handoff");
  state = portabilityReducer(state, {
    type: "step",
    index: 2,
    status: "active",
  });
  assert.equal(state.stepIndex, 2);
  assert.equal(selectStep(state)?.id, "dry-run");
  state = portabilityReducer(state, { type: "busy", value: true });
  assert.equal(state.busy, true);
});

test("reducer stores dry run, conflicts, vector, progress, and receipt", () => {
  let state = initialPortabilityState();
  const report = dryRun({ conflicts: [conflict()] });
  state = portabilityReducer(state, { type: "dry-run", value: report });
  assert.equal(state.dryRun?.operation, "import");
  assert.equal(state.conflicts.length, 1);
  state = portabilityReducer(state, { type: "vector", value: vector() });
  assert.equal(state.vector?.concurrent, true);
  state = portabilityReducer(state, { type: "progress", value: progress() });
  assert.equal(selectProgress(state)?.percent, 50);
  state = portabilityReducer(state, { type: "receipt", value: receipt() });
  assert.equal(selectReceipt(state)?.ok, true);
  state = portabilityReducer(state, {
    type: "audit",
    value: [{ sequence: 1, kind: "x" }],
  });
  assert.equal(state.audit.length, 1);
  state = portabilityReducer(state, {
    type: "notice",
    value: { tone: "good", title: "Done", message: "ok" },
  });
  assert.equal(selectNotice(state)?.title, "Done");
});

test("reducer resolves conflicts and gates readiness", () => {
  let state = initialPortabilityState();
  state = portabilityReducer(state, {
    type: "dry-run",
    value: dryRun({ conflicts: [conflict()] }),
  });
  assert.equal(selectReadyToRun(state), false);
  state = portabilityReducer(state, {
    type: "resolve",
    ref: "note:1",
    resolution: "keep_local",
  });
  assert.equal(selectUnresolved(state), 0);
  assert.equal(selectReadyToRun(state), true);
  state = portabilityReducer(state, { type: "busy", value: true });
  assert.equal(selectReadyToRun(state), false);
});

test("reducer resets to a fresh state", () => {
  let state = initialPortabilityState();
  state = portabilityReducer(state, {
    type: "plan",
    value: { label: "Changed" },
  });
  state = portabilityReducer(state, { type: "reset" });
  assert.equal(state.plan.label, "");
  assert.equal(state.conflicts.length, 0);
});

test("request builders omit empty values", () => {
  assert.deepEqual(compact({ a: 1, b: "", c: null, d: undefined, e: 0 }), {
    a: 1,
    e: 0,
  });
  const value = plan();
  const request = bundleCreateRequest(value, [{ id: 1 }], []);
  assert.equal(request.device_id, "local");
  assert.equal(request.passphrase, value.passphrase);
  assert.deepEqual(request.entities, [{ id: 1 }]);
  assert.deepEqual(request.links, []);
  assert.equal(request.families?.length, 4);
});

test("preview, resolution, and transfer request builders", () => {
  assert.deepEqual(previewRequest("bundle_1", "pw", [1], [2], ["note"]), {
    bundle_id: "bundle_1",
    passphrase: "pw",
    base: [1],
    local: [2],
    families: ["note"],
  });
  assert.deepEqual(resolveRequest("preview_1", { "note:1": "keep_local" }), {
    preview_id: "preview_1",
    decisions: { "note:1": "keep_local" },
    actor: "local",
    device: "local",
  });
  assert.deepEqual(transferChunkRequest("xfer_1", 2, "YWJj"), {
    transfer_id: "xfer_1",
    index: 2,
    chunk: "YWJj",
  });
  assert.deepEqual(transferStartRequest("bundle_1", 1024), {
    bundle_id: "bundle_1",
    chunk_size: 1024,
  });
});

test("client calls the sync namespace with v3 envelopes", async () => {
  const calls: Array<{ url: string; body: unknown }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    calls.push({ url: String(input), body: JSON.parse(String(init.body)) });
    return json(envelope({ ok: true }));
  }) as typeof globalThis.fetch;
  const client = createPortabilityClient(fetchImpl);
  const result = await client.health();
  assert.deepEqual(result, { ok: true });
  assert.equal(calls[0].url, "/api/v3/sync/health");
});

test("client compares vectors and inspects bundles", async () => {
  const fetchImpl = (async () =>
    json(envelope(vector()))) as typeof globalThis.fetch;
  const client = new PortabilityClient(
    new (await import("../src/v3/apiClient")).V3Client({ fetch: fetchImpl }),
  );
  const compared = await client.compareVectors({ alpha: 2 }, { beta: 1 });
  assert.equal(compared.relation, "concurrent");
  const inspected = await client.inspectBundle("bundle_1");
  assert.equal(inspected.relation, "concurrent");
});

test("client verifies bundles and resolves conflicts", async () => {
  const receiptView = receipt();
  const fetchImpl = (async () =>
    json(
      envelope({
        receipt: receiptView,
        verification: { ok: true },
        merge: { conflicts: [] },
        ledger_intact: true,
      }),
    )) as typeof globalThis.fetch;
  const client = createPortabilityClient(fetchImpl);
  const verified = await client.verifyBundle("bundle_1", "Str0ng!Passphrase");
  assert.equal(verified.receipt.ok, true);
  const resolved = await client.resolveConflicts("preview_1", {
    "note:1": "keep_local",
  });
  assert.equal(resolved.ledger_intact, true);
});

test("client transfer methods round-trip progress views", async () => {
  const fetchImpl = (async () =>
    json(envelope(progress()))) as typeof globalThis.fetch;
  const client = createPortabilityClient(fetchImpl);
  const started = await client.beginTransfer("bundle_1", 128);
  assert.equal(started.transferId, "xfer_1");
  assert.equal((await client.pushChunk("xfer_1", 0, "YWJj")).percent, 50);
  assert.equal((await client.pauseTransfer("xfer_1")).phase, "active");
  assert.equal((await client.resumeTransfer("xfer_1")).phase, "active");
  assert.equal((await client.cancelTransfer("xfer_1")).phase, "active");
});

test("client raises typed errors from v3 error envelopes", async () => {
  const fetchImpl = (async () =>
    json(
      {
        error: {
          code: "forbidden",
          message: "Portability disabled",
          field: "",
          retryable: false,
          context: {},
        },
        meta: { request_id: "req_1", api_version: "3.0" },
      },
      403,
    )) as typeof globalThis.fetch;
  const client = createPortabilityClient(fetchImpl);
  await assert.rejects(
    () => client.health(),
    (error: unknown) => {
      assert.equal((error as { code: string }).code, "forbidden");
      return true;
    },
  );
});
