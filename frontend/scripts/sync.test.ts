import assert from "node:assert/strict";
import test from "node:test";
import { V2Client } from "../src/lib/apiClient";
import {
  MERGE_STRATEGIES,
  SYNC_FORMATS,
  SyncClient,
  activeWizardIndex,
  advanceWizard,
  aggregateProgress,
  applyBulkResolution,
  applyConflictResolution,
  backupRequest,
  buildWizardSteps,
  canUseFormatForBackup,
  canUseFormatForExport,
  canUseFormatForImport,
  changeTone,
  clampPercent,
  compact,
  conflictTone,
  defaultSelection,
  describePath,
  dryRunChanges,
  dryRunConflicts,
  dryRunHeadline,
  exportRequest,
  filterActionableChanges,
  filterByQuery,
  formatBytes,
  formatCount,
  formatDateTime,
  formatPercent,
  groupChangesByAction,
  importPlanFromSelection,
  importRequest,
  inferFormat,
  initialSyncState,
  latestProgress,
  mergeStrategyHelp,
  normalizePath,
  noticeForError,
  profileToSelection,
  progressLabel,
  recommendResolution,
  resolutionLabel,
  resolutionMap,
  restoreRequest,
  selectActionableChangeCount,
  selectIsReadyToRun,
  selectLatestProgress,
  selectUnresolvedCount,
  sessionIsComplete,
  shortChecksum,
  stableSortByPath,
  summarizeChanges,
  summarizeConflicts,
  summarizeMerge,
  syncReducer,
  titleForFormat,
  toErrorMessage,
  unresolvedConflicts,
  validateBackupSelection,
  validateExportSelection,
  validateImportSelection,
  validateRestoreSelection,
  wizardPercent,
} from "../src/features/sync";

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ ok: true, data }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function bodyOf(init: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init.body ?? "{}")) as Record<string, unknown>;
}

function routeOf(url: string): string {
  return url.slice(url.lastIndexOf("/") + 1);
}

test("format helpers normalize percentages, bytes, counts, and labels", () => {
  assert.equal(clampPercent(-1), 0);
  assert.equal(clampPercent(101), 100);
  assert.equal(clampPercent(33.333), 33.33);
  assert.equal(formatPercent(10), "10%");
  assert.equal(formatPercent(10.5), "10.5%");
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(2048), "2 KB");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatCount(Number.NaN), "0");
  assert.equal(shortChecksum("abcdef1234567890"), "abcdef12…7890");
  assert.equal(shortChecksum("short"), "short");
  assert.equal(titleForFormat("sqlite"), "SQLite backup");
  assert.equal(titleForFormat("markdown"), "Markdown export");
  assert.equal(changeTone("create"), "success");
  assert.equal(changeTone("delete"), "danger");
  assert.equal(conflictTone("delete_vs_edit"), "danger");
  assert.equal(conflictTone("metadata"), "neutral");
  assert.equal(resolutionLabel("keep_local"), "Keep local");
  assert.equal(describePath(""), "No path selected");
  assert.equal(describePath("/a/b/c.json"), "…/b/c.json");
  assert.equal(formatDateTime(""), "—");
  assert.equal(toErrorMessage("boom"), "boom");
  assert.equal(toErrorMessage(new Error("oops")), "oops");
});

test("helpers infer formats, validate selections, and build wizard flows", () => {
  assert.deepEqual(SYNC_FORMATS, ["json", "markdown", "html", "sqlite"]);
  assert.deepEqual(MERGE_STRATEGIES, [
    "merge",
    "prefer_local",
    "prefer_remote",
    "skip",
  ]);
  assert.equal(inferFormat("backup.db"), "sqlite");
  assert.equal(inferFormat("report.html"), "html");
  assert.equal(inferFormat("notes/"), "markdown");
  assert.equal(inferFormat("snapshot.json"), "json");
  assert.equal(normalizePath("C:\\tmp\\a.json"), "C:/tmp/a.json");
  assert.equal(canUseFormatForImport("json"), true);
  assert.equal(canUseFormatForImport("sqlite"), false);
  assert.equal(canUseFormatForExport("html"), true);
  assert.equal(canUseFormatForBackup("sqlite"), true);
  assert.equal(canUseFormatForBackup("html"), false);
  assert.deepEqual(
    validateBackupSelection({
      ...defaultSelection(),
      destinationPath: "",
      format: "sqlite",
    }),
    ["Destination path is required"],
  );
  assert.deepEqual(
    validateRestoreSelection({ ...defaultSelection(), sourcePath: "" }),
    ["Source path is required"],
  );
  assert.deepEqual(
    validateExportSelection({
      ...defaultSelection(),
      destinationPath: "",
      format: "sqlite",
    }),
    [
      "Destination path is required",
      "Exports support json, markdown, or html formats",
    ],
  );
  assert.deepEqual(
    validateImportSelection({
      ...defaultSelection(),
      sourcePath: "in.json",
      format: "sqlite",
      strategy: "merge",
    }),
    ["Imports support json or markdown formats"],
  );
  const steps = buildWizardSteps("import");
  assert.equal(steps.length, 4);
  assert.equal(activeWizardIndex(steps), 0);
  const advanced = advanceWizard(steps, 0, "complete");
  assert.equal(advanced[0].status, "complete");
  assert.equal(advanced[1].status, "active");
  assert.equal(wizardPercent(advanced), 25);
});

test("change and conflict helpers summarize, filter, and resolve items", () => {
  const changes = [
    {
      key: "a",
      action: "create",
      entity_type: "note",
      title: "A",
      path: "a",
      checksum: "",
      updated_at: "",
      local: null,
      remote: null,
    },
    {
      key: "b",
      action: "update",
      entity_type: "note",
      title: "B",
      path: "b",
      checksum: "",
      updated_at: "",
      local: null,
      remote: null,
    },
    {
      key: "c",
      action: "delete",
      entity_type: "note",
      title: "C",
      path: "c",
      checksum: "",
      updated_at: "",
      local: null,
      remote: null,
    },
    {
      key: "d",
      action: "unchanged",
      entity_type: "note",
      title: "D",
      path: "d",
      checksum: "",
      updated_at: "",
      local: null,
      remote: null,
    },
  ] as const;
  const actionable = filterActionableChanges([...changes]);
  assert.equal(actionable.length, 3);
  assert.deepEqual(groupChangesByAction([...changes]).create[0].key, "a");
  assert.deepEqual(summarizeChanges([...changes]), {
    total: 4,
    create: 1,
    update: 1,
    delete: 1,
    unchanged: 1,
  });
  const conflicts = [
    {
      key: "x",
      kind: "content",
      path: "x.md",
      title: "X",
      local_checksum: "1",
      remote_checksum: "2",
      local_updated_at: "2026-01-01T00:00:00Z",
      remote_updated_at: "2026-01-02T00:00:00Z",
      resolution: "unresolved",
      details: {},
      suggested: "keep_remote",
    },
    {
      key: "y",
      kind: "metadata",
      path: "y.md",
      title: "Y",
      local_checksum: "3",
      remote_checksum: "4",
      local_updated_at: "2026-01-03T00:00:00Z",
      remote_updated_at: "2026-01-02T00:00:00Z",
      resolution: "unresolved",
      details: {},
      suggested: "",
    },
  ];
  assert.equal(unresolvedConflicts(conflicts).length, 2);
  assert.equal(recommendResolution(conflicts[0]), "keep_remote");
  assert.equal(recommendResolution(conflicts[1]), "keep_local");
  const resolved = applyConflictResolution(conflicts, "x", "keep_local");
  assert.equal(resolved[0].resolution, "keep_local");
  const bulk = applyBulkResolution(conflicts, "skip");
  assert.equal(
    bulk.every((item) => item.resolution === "skip"),
    true,
  );
  assert.deepEqual(
    resolutionMap(applyConflictResolution(conflicts, "x", "merged")),
    { x: "merged" },
  );
  assert.deepEqual(
    summarizeConflicts(applyConflictResolution(conflicts, "x", "merged")),
    {
      total: 2,
      unresolved: 1,
      keep_local: 0,
      keep_remote: 0,
      merged: 1,
      skip: 0,
    },
  );
  assert.equal(
    sessionIsComplete({ conflicts: resolved, resolved: false } as never),
    false,
  );
});

test("selection, request, and dry-run helpers map UI state to API payloads", () => {
  const selection = {
    ...defaultSelection(),
    sourcePath: "in.json",
    destinationPath: "out.db",
    format: "sqlite" as const,
    strategy: "prefer_remote" as const,
    dryRun: true,
    verifyChecksums: true,
    includeSettings: true,
    includeDeleted: false,
  };
  assert.deepEqual(compact({ a: 1, b: "", c: null, d: undefined }), { a: 1 });
  assert.deepEqual(backupRequest(selection), {
    destination: "out.db",
    format: "sqlite",
    include_deleted: false,
    include_settings: true,
    include_manifest: true,
    include_snippets: true,
    include_history: false,
    dry_run: true,
  });
  assert.deepEqual(restoreRequest({ ...selection, sourcePath: "in.db" }), {
    source: "in.db",
    mode: "replace",
    verify_checksums: true,
    dry_run: true,
    allow_incompatible: false,
  });
  assert.deepEqual(
    exportRequest({
      ...selection,
      format: "html",
      destinationPath: "out.html",
    }),
    {
      destination: "out.html",
      format: "html",
      include_deleted: false,
      include_settings: true,
      dry_run: true,
    },
  );
  assert.deepEqual(
    importRequest({ ...selection, format: "markdown", sourcePath: "notes" }),
    {
      source: "notes",
      format: "markdown",
      strategy: "prefer_remote",
      verify_checksums: true,
      dry_run: true,
    },
  );
  assert.deepEqual(
    importPlanFromSelection({
      ...selection,
      format: "markdown",
      sourcePath: "notes",
    }),
    {
      source: "notes",
      format: "markdown",
      strategy: "prefer_remote",
      verify_checksums: true,
      dry_run: true,
      parent_id: null,
    },
  );
  assert.equal(
    mergeStrategyHelp("merge"),
    "Combine non-conflicting changes and require decisions for conflicts.",
  );
  assert.equal(
    profileToSelection(
      {
        name: "quick-json",
        format: "json",
        include_deleted: false,
        include_settings: true,
        include_history: false,
        verify_checksums: true,
        strategy: "skip",
        description: "",
      },
      selection,
    ).strategy,
    "skip",
  );
  const report = {
    operation: "import",
    valid: true,
    summary: {},
    changes: [{ key: "a", action: "create" }],
    conflicts: [{ key: "b", resolution: "unresolved" }],
    warnings: [],
  } as never;
  assert.equal(dryRunChanges(report).length, 1);
  assert.equal(dryRunConflicts(report).length, 1);
  assert.equal(dryRunHeadline(report as never), "1 changes, 1 conflicts");
  assert.equal(
    summarizeMerge({ counts: { applied: 1, skipped: 2, conflicts: 3 } }),
    "1 applied, 2 skipped, 3 conflicts",
  );
});

test("progress and collection helpers support stable UI rendering", () => {
  const reports = [
    {
      operation: "sync",
      stage: "plan",
      current: 1,
      total: 4,
      message: "start",
      percent: 25,
      done: true,
    },
    {
      operation: "sync",
      stage: "write",
      current: 2,
      total: 4,
      message: "write",
      percent: 50,
      done: false,
    },
  ];
  assert.deepEqual(latestProgress(reports)?.stage, "write");
  assert.equal(aggregateProgress(reports), 50);
  assert.equal(progressLabel(latestProgress(reports)), "write 50% — write");
  const items = [
    { key: "b", path: "b.md", title: "Beta" },
    { key: "a", path: "a.md", title: "Alpha" },
  ];
  assert.deepEqual(
    stableSortByPath(items).map((item) => item.key),
    ["a", "b"],
  );
  assert.deepEqual(
    filterByQuery(items, "alpha").map((item) => item.key),
    ["a"],
  );
});

test("state reducer tracks wizard, dry-run, conflicts, progress, and readiness", () => {
  let state = initialSyncState("import");
  assert.equal(state.wizard[0].status, "active");
  state = syncReducer(state, {
    type: "selection",
    value: { sourcePath: "in.json" },
  });
  assert.equal(state.selection.sourcePath, "in.json");
  state = syncReducer(state, { type: "wizard", index: 0, status: "complete" });
  assert.equal(state.wizard[1].status, "active");
  state = syncReducer(state, {
    type: "dry-run",
    value: {
      operation: "import",
      valid: true,
      summary: {},
      changes: [
        {
          key: "a",
          action: "create",
          entity_type: "note",
          title: "A",
          path: "a",
          checksum: "",
          updated_at: "",
        },
      ],
      conflicts: [],
      warnings: [],
    } as never,
  });
  assert.equal(selectActionableChangeCount(state), 1);
  assert.equal(selectUnresolvedCount(state), 0);
  assert.equal(selectIsReadyToRun(state), true);
  state = syncReducer(state, {
    type: "progress-push",
    value: {
      operation: "sync",
      stage: "load",
      current: 1,
      total: 2,
      message: "loading",
      percent: 50,
      done: false,
    },
  });
  assert.equal(selectLatestProgress(state)?.stage, "load");
  state = syncReducer(state, { type: "busy", value: true });
  assert.equal(selectIsReadyToRun(state), false);
  state = syncReducer(state, {
    type: "log",
    value: { operation: "import", status: "completed", summary: "done" },
  });
  assert.equal(state.logs.length, 1);
  assert.equal(noticeForError("x").tone, "danger");
});

test("sync client maps routes and payloads for major operations", async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const body = bodyOf(init);
    calls.push({ url, body });
    const route = routeOf(url);
    const responses: Record<string, unknown> = {
      "sync.health": {
        ok: true,
        namespace: "sync",
        records: 1,
        formats: ["json"],
        strategies: ["merge"],
        vault: "v",
        schema_version: 4,
      },
      "sync.backup.create": { path: "a.db", dry_run: false },
      "sync.restore.apply": { restored_path: "a.db", dry_run: false },
      "sync.export.run": { path: "a.json", dry_run: false },
      "sync.import.plan": {
        dry_run: true,
        local_records: 0,
        remote_records: 0,
        merge: { applied: [], skipped: [], conflicts: [] },
        plan: {},
      },
      "sync.import.run": {
        dry_run: false,
        local_records: 0,
        remote_records: 0,
        merge: { applied: [], skipped: [], conflicts: [] },
        plan: {},
      },
      "sync.dry_run": {
        operation: "backup",
        valid: true,
        summary: {},
        warnings: [],
      },
      "sync.conflicts.detect": {
        changes: [],
        conflicts: [],
        summary: { changes: 0, conflicts: 0, resolutions: {} },
      },
      "sync.merge.preview": {
        strategy: "merge",
        applied: [],
        skipped: [],
        conflicts: [],
        dry_run: true,
      },
      "sync.checksums.verify": { ok: true },
      "sync.vectors.compare": {
        local: { a: 1 },
        remote: { a: 2 },
        relation: "remote",
        merged: { a: 2 },
      },
      "sync.migration.check": { compatibility: { compatible: true } },
      "sync.portability.profiles": { profiles: [], matrix: {} },
      "sync.progress.report": {
        reports: [],
        summary: { stages: 0, done: false, percent: 0 },
      },
    };
    return envelope(responses[route] ?? {});
  }) as typeof globalThis.fetch;

  const client = new SyncClient(
    new V2Client({ fetch: fetcher, requestId: () => "req_sync" }),
  );
  const selection = {
    ...defaultSelection(),
    sourcePath: "in.json",
    destinationPath: "out.db",
    format: "sqlite" as const,
  };
  await client.health();
  await client.backup(selection);
  await client.restore(selection);
  await client.exportData({
    ...selection,
    destinationPath: "out.json",
    format: "json",
  });
  await client.importPlan({ ...selection, format: "json" });
  await client.importData({ ...selection, format: "json" });
  await client.dryRun("backup", { destination: "out.db" });
  await client.detectConflicts({ source: "in.json" });
  await client.mergePreview({ source: "in.json" });
  await client.verifyChecksums({ path: "out.db" });
  await client.compareVectors({ a: 1 }, { a: 2 });
  await client.migrationCheck({ manifest_version: "1.0", schema_version: 4 });
  await client.portabilityProfiles();
  await client.progressReport([{ stage: "x", message: "y" }]);

  const routes = calls.map((call) => routeOf(call.url));
  assert.ok(routes.includes("sync.health"));
  assert.ok(routes.includes("sync.backup.create"));
  assert.ok(routes.includes("sync.restore.apply"));
  assert.ok(routes.includes("sync.export.run"));
  assert.ok(routes.includes("sync.import.plan"));
  assert.ok(routes.includes("sync.import.run"));
  assert.ok(routes.includes("sync.dry_run"));
  assert.ok(routes.includes("sync.conflicts.detect"));
  assert.ok(routes.includes("sync.merge.preview"));
  assert.ok(routes.includes("sync.checksums.verify"));
  assert.ok(routes.includes("sync.vectors.compare"));
  assert.ok(routes.includes("sync.migration.check"));
  assert.ok(routes.includes("sync.portability.profiles"));
  assert.ok(routes.includes("sync.progress.report"));
  assert.equal(calls[0].body && typeof calls[0].body, "object");
});
