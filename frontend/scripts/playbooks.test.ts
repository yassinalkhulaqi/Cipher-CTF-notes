import assert from "node:assert/strict";
import test from "node:test";
import { PlaybooksClient } from "../src/features/playbooks/client";
import {
  ancestorsOf,
  checklistProgress,
  coerceVariableInput,
  compareVersions,
  dependencyDepth,
  descendantsOf,
  filterPlaybooks,
  filterSnippets,
  formatMinutes,
  formatValue,
  graphLayers,
  groupByCategory,
  groupRecommendations,
  hasAnyTag,
  initialInputs,
  maskSecrets,
  missingVariables,
  nextAdvice,
  normalizeQuery,
  playbookStats,
  planVariables,
  planWarnings,
  plannedCommand,
  previewTemplate,
  progressPercent,
  readySteps,
  referencedVariables,
  snippetFamilies,
  sortPlaybooks,
  splitTags,
  stepById,
  summarizePlaybook,
  summarizeRun,
  tagKey,
  templateCategories,
  unique,
  unknownVariables,
  validatePlaybookDraft,
  validateStepDraft,
  validateVariableDraft,
  valuesFromInputs,
} from "../src/features/playbooks/helpers";
import type {
  ChecklistItem,
  Condition,
  Playbook,
  PlaybookStep,
  PlannedStep,
  Recommendation,
  RunPlan,
  RunState,
  SnippetRecord,
  TemplateRecord,
  VariableDefinition,
} from "../src/features/playbooks/types";

function checklist(id: string, label = id): ChecklistItem {
  return { id, label, detail: "", required: true, condition: null, tags: [] };
}

function condition(): Condition {
  return { field: "target", operator: "exists", value: "" };
}

function step(id: string, overrides: Partial<PlaybookStep> = {}): PlaybookStep {
  return {
    id,
    title: `Step ${id}`,
    kind: "action",
    summary: "",
    command_template: `echo {{ target }} ${id}`,
    snippet_key: "",
    checklist: [checklist(`${id}-check`)],
    depends_on: [],
    when: [],
    variables: ["target"],
    optional: false,
    estimated_minutes: 5,
    tags: [],
    note: "",
    ...overrides,
  };
}

function variable(
  key: string,
  overrides: Partial<VariableDefinition> = {},
): VariableDefinition {
  return {
    key,
    label: key,
    kind: "text",
    required: false,
    default: "",
    choices: [],
    description: "",
    secret: false,
    pattern: "",
    minimum: null,
    maximum: null,
    ...overrides,
  };
}

function playbook(key: string, overrides: Partial<Playbook> = {}): Playbook {
  return {
    id: 1,
    key,
    title: `Playbook ${key}`,
    description: "Description",
    status: "draft",
    category: "recon",
    tags: ["network", "recon"],
    version: "1.0.0",
    steps: [step("a")],
    variables: [variable("target", { required: true })],
    owner: "tester",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    references: [],
    ...overrides,
  };
}

function snippet(
  key: string,
  overrides: Partial<SnippetRecord> = {},
): SnippetRecord {
  return {
    id: 1,
    key,
    title: key,
    command: `run {{ target }} ${key}`,
    description: "Snippet description",
    tags: ["network"],
    library: "builtin",
    variables: ["target"],
    usage_count: 4,
    version: "1.0.0",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function template(
  key: string,
  overrides: Partial<TemplateRecord> = {},
): TemplateRecord {
  return {
    id: 1,
    key,
    name: key,
    content: "# {{ title }}\n\nTarget: {{ target }}",
    description: "Template description",
    tags: ["report"],
    category: "reports",
    variables: [variable("title"), variable("target")],
    version: "1.0.0",
    changelog: [],
    default_title: "Untitled",
    ...overrides,
  };
}

function planned(
  id: string,
  overrides: Partial<PlannedStep> = {},
): PlannedStep {
  return {
    id,
    title: `Planned ${id}`,
    kind: "action",
    command: `echo {{ target }} ${id}`,
    checklist: [checklist(`${id}-check`)],
    depends_on: [],
    skipped: false,
    variables: ["target"],
    warnings: [],
    ...overrides,
  };
}

function plan(overrides: Partial<RunPlan> = {}): RunPlan {
  return {
    playbook_key: "demo",
    version: "1.0.0",
    values: { target: "example.com" },
    steps: [planned("a"), planned("b", { depends_on: ["a"] })],
    issues: [],
    estimated_minutes: 10,
    critical_path: ["a", "b"],
    generated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function run(overrides: Partial<RunState> = {}): RunState {
  return {
    id: 7,
    playbook_key: "demo",
    version: "1.0.0",
    status: "running",
    values: { target: "example.com" },
    step_status: { a: "done", b: "ready" },
    checklist: { "a-check": "done", "b-check": "pending" },
    notes: { "a-check": "observed" },
    events: [],
    current_step: "b",
    started_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:01:00Z",
    finished_at: "",
    context: {},
    ...overrides,
  };
}

test("normalizeQuery, splitTags, tagKey, unique, and hasAnyTag clean inputs", () => {
  assert.equal(normalizeQuery("  Recon   Network "), "recon network");
  assert.deepEqual(splitTags(" Recon, network recon ##web "), [
    "recon",
    "network",
    "web",
  ]);
  assert.equal(tagKey("#Network"), "network");
  assert.deepEqual(unique(["a", "b", "a", "c"]), ["a", "b", "c"]);
  assert.equal(hasAnyTag(["recon", "web"], ["#RECON"]), true);
  assert.equal(hasAnyTag(["recon"], ["web"]), false);
  assert.equal(hasAnyTag(["recon"], []), true);
});

test("compareVersions orders semantic versions", () => {
  assert.equal(compareVersions("1.0.0", "1.0.1"), -1);
  assert.equal(compareVersions("2.0.0", "1.9.9"), 1);
  assert.equal(compareVersions("1.2.0", "1.2"), 0);
  assert.equal(compareVersions("1.10.0", "1.9.9"), 1);
});

test("filterPlaybooks supports query, tags, status, and category", () => {
  const books = [
    playbook("alpha", {
      tags: ["network"],
      category: "recon",
      status: "active",
    }),
    playbook("beta", {
      tags: ["web"],
      category: "exploit",
      status: "draft",
      steps: [step("scan", { summary: "port scan" })],
    }),
  ];
  assert.deepEqual(
    filterPlaybooks(books, { query: "port scan" }).map((item) => item.key),
    ["beta"],
  );
  assert.deepEqual(
    filterPlaybooks(books, { tags: ["network"] }).map((item) => item.key),
    ["alpha"],
  );
  assert.deepEqual(
    filterPlaybooks(books, { status: "draft" }).map((item) => item.key),
    ["beta"],
  );
  assert.deepEqual(
    filterPlaybooks(books, { category: "RECON" }).map((item) => item.key),
    ["alpha"],
  );
  assert.equal(filterPlaybooks(books, { query: "missing" }).length, 0);
});

test("sortPlaybooks and groupByCategory organize the library", () => {
  const books = [
    playbook("zeta", { title: "Zulu", status: "archived", version: "1.2.0" }),
    playbook("alpha", { title: "Alpha", status: "active", version: "2.0.0" }),
    playbook("middle", {
      title: "Middle",
      status: "draft",
      category: "exploit",
    }),
  ];
  assert.deepEqual(
    sortPlaybooks(books, "title").map((item) => item.key),
    ["alpha", "middle", "zeta"],
  );
  assert.deepEqual(
    sortPlaybooks(books, "title", "desc").map((item) => item.key),
    ["zeta", "middle", "alpha"],
  );
  assert.equal(sortPlaybooks(books, "status")[0]?.key, "alpha");
  assert.equal(sortPlaybooks(books, "version")[0]?.key, "middle");
  const groups = groupByCategory(books);
  assert.deepEqual(Array.from(groups.keys()), ["exploit", "recon"]);
  assert.equal(groups.get("recon")?.length, 2);
});

test("playbookStats and summarizePlaybook count nested content", () => {
  const books = [
    playbook("alpha", {
      status: "active",
      steps: [
        step("a", { checklist: [checklist("a1"), checklist("a2")] }),
        step("b"),
      ],
      variables: [variable("target"), variable("ports", { kind: "list" })],
      tags: ["network"],
    }),
    playbook("beta", { status: "draft", tags: ["web"] }),
  ];
  const stats = playbookStats(books);
  assert.equal(stats.playbooks, 2);
  assert.equal(stats.active, 1);
  assert.equal(stats.steps, 3);
  assert.equal(stats.checklists, 4);
  assert.equal(stats.variables, 2);
  assert.equal(stats.tags, 2);
  const summary = summarizePlaybook(books[0] as Playbook);
  assert.equal(summary.step_count, 2);
  assert.equal(summary.checklist_count, 3);
  assert.equal("steps" in summary, false);
});

test("dependencyDepth, graphLayers, ancestors, descendants, and readySteps walk the DAG", () => {
  const graph = playbook("graph", {
    steps: [
      step("a"),
      step("b", { depends_on: ["a"] }),
      step("c", { depends_on: ["a"] }),
      step("d", { depends_on: ["b", "c"] }),
    ],
  });
  const depths = dependencyDepth(graph);
  assert.equal(depths.get("a"), 0);
  assert.equal(depths.get("b"), 1);
  assert.equal(depths.get("d"), 2);
  assert.deepEqual(graphLayers(graph), [["a"], ["b", "c"], ["d"]]);
  assert.deepEqual(ancestorsOf(graph, "d"), ["a", "b", "c"]);
  assert.deepEqual(descendantsOf(graph, "a"), ["b", "c", "d"]);
  assert.deepEqual(descendantsOf(graph, "d"), []);
  assert.deepEqual(
    readySteps(graph, new Set()).map((item) => item.id),
    ["a"],
  );
  assert.deepEqual(
    readySteps(graph, new Set(["a"])).map((item) => item.id),
    ["b", "c"],
  );
  assert.equal(stepById(graph, "c")?.title, "Step c");
  assert.equal(stepById(graph, "missing"), undefined);
});

test("dependencyDepth stops on cycles and still returns stable layers", () => {
  const graph = playbook("cycle", {
    steps: [step("a", { depends_on: ["b"] }), step("b", { depends_on: ["a"] })],
  });
  const depths = dependencyDepth(graph);
  assert.equal(depths.size, 2);
  assert.equal(graphLayers(graph).flat().length, 2);
});

test("formatValue, coerceVariableInput, initialInputs, and valuesFromInputs handle types", () => {
  assert.equal(formatValue(null), "-");
  assert.equal(formatValue(true), "true");
  assert.equal(formatValue(["a", 2]), "a, 2");
  assert.equal(
    coerceVariableInput(variable("n", { kind: "number" }), "42"),
    42,
  );
  assert.equal(
    coerceVariableInput(variable("n", { kind: "number" }), "x"),
    null,
  );
  assert.equal(
    coerceVariableInput(variable("b", { kind: "boolean" }), "YES"),
    true,
  );
  assert.equal(
    coerceVariableInput(variable("b", { kind: "boolean" }), "maybe"),
    null,
  );
  assert.deepEqual(
    coerceVariableInput(variable("l", { kind: "list" }), "a, b,c"),
    ["a", "b", "c"],
  );
  assert.equal(coerceVariableInput(variable("t"), "  text "), "text");

  const vars = [
    variable("target", { required: true, default: "" }),
    variable("ports", { kind: "list", default: ["80"] }),
  ];
  assert.deepEqual(initialInputs(vars, "host.local"), {
    target: "host.local",
    ports: "80",
  });
  assert.deepEqual(
    valuesFromInputs(vars, { target: "host.local", ports: "80,443" }),
    {
      target: "host.local",
      ports: ["80", "443"],
    },
  );
});

test("missingVariables, referencedVariables, unknownVariables, and maskSecrets protect values", () => {
  const vars = [
    variable("target", { required: true }),
    variable("token", { kind: "secret", required: true }),
    variable("optional"),
  ];
  assert.deepEqual(missingVariables(vars, { target: "" }), [vars[0], vars[1]]);
  assert.deepEqual(
    referencedVariables("{{ target }} {{ domain | lower }} {{target}}"),
    ["target", "domain"],
  );
  const graph = playbook("vars", {
    steps: [
      step("a", {
        command_template: "{{ target }} {{ mystery }} {{ domain }}",
      }),
    ],
  });
  assert.deepEqual(unknownVariables(graph, { target: "x" }), ["mystery"]);
  assert.deepEqual(maskSecrets(vars, { target: "x", token: "s3cr3t" }), {
    target: "x",
    token: "••••••",
  });
});

test("formatMinutes, progressPercent, summarizeRun, and checklistProgress report status", () => {
  assert.equal(formatMinutes(45), "45m");
  assert.equal(formatMinutes(120), "2h");
  assert.equal(formatMinutes(125), "2h 5m");
  assert.equal(progressPercent(1, 4), 25);
  assert.equal(progressPercent(1, 0), 100);
  const current = run();
  const summary = summarizeRun(current, plan());
  assert.equal(summary.settled, 1);
  assert.equal(summary.total, 2);
  assert.equal(summary.percent, 50);
  const checklist = checklistProgress(current, plan());
  assert.equal(checklist.total, 2);
  assert.equal(checklist.done, 1);
  assert.equal(checklist.required_total, 2);
  assert.equal(checklist.required_done, 1);
  assert.equal(checklist.percent, 50);
  assert.equal(checklist.items[0]?.note, "observed");
});

test("nextAdvice returns the first ready step and respects blockers", () => {
  const currentPlan = plan({
    steps: [
      planned("a"),
      planned("b", { depends_on: ["a"] }),
      planned("c", { depends_on: ["d"] }),
    ],
  });
  const advice = nextAdvice(
    currentPlan,
    run({ step_status: { a: "done" }, current_step: "b" }),
  );
  assert.equal(advice?.step_id, "b");
  assert.deepEqual(advice?.blocked_by, []);
  assert.equal(nextAdvice(null, run()), null);
  assert.equal(nextAdvice(currentPlan, null), null);
  const blocked = nextAdvice(
    currentPlan,
    run({ step_status: { a: "skipped" }, current_step: "b" }),
  );
  assert.equal(blocked?.step_id, "b");
});

test("snippet filtering, families, and template preview work without a backend", () => {
  const snippets = [
    snippet("nmap-basic", { tags: ["network"], command: "nmap {{ target }}" }),
    snippet("smbclient-shares", {
      tags: ["shares"],
      command: "smbclient -L {{ host }}",
    }),
  ];
  assert.deepEqual(
    filterSnippets(snippets, "nmap").map((item) => item.key),
    ["nmap-basic"],
  );
  assert.deepEqual(
    filterSnippets(snippets, "", ["shares"]).map((item) => item.key),
    ["smbclient-shares"],
  );
  assert.deepEqual(filterSnippets(snippets, "", [], "builtin").length, 2);
  assert.deepEqual(Array.from(snippetFamilies(snippets).entries()), [
    ["nmap", 1],
    ["smbclient", 1],
  ]);
  const rendered = previewTemplate(template("report"), {
    title: "Engagement",
    target: "host.local",
  });
  assert.equal(rendered.content, "# Engagement\n\nTarget: host.local");
  assert.deepEqual(rendered.unresolved, []);
  assert.deepEqual(
    templateCategories([
      template("report"),
      template("note", { category: "notes" }),
    ]),
    ["notes", "reports"],
  );
});

test("validation helpers find draft problems", () => {
  assert.deepEqual(
    validateStepDraft(
      step("a", {
        title: "",
        snippet_key: "",
        command_template: "",
        depends_on: ["a"],
      }),
    )
      .map((issue) => issue.code)
      .sort(),
    ["empty-command", "missing-title", "self-dependency"],
  );
  assert.deepEqual(
    validateVariableDraft(
      variable("", { label: "", kind: "choice", choices: [], pattern: "[" }),
    )
      .map((issue) => issue.code)
      .sort(),
    ["invalid-pattern", "missing-choices", "missing-key", "missing-label"],
  );
  const graph = playbook("bad", {
    key: "",
    title: "",
    version: "v1",
    steps: [step("a"), step("a", { depends_on: ["ghost"] })],
  });
  const codes = validatePlaybookDraft(graph).map((issue) => issue.code);
  assert.ok(codes.includes("duplicate-step"));
  assert.ok(codes.includes("unknown-parent"));
  assert.ok(codes.includes("invalid-version"));
  assert.equal(validatePlaybookDraft(playbook("ok")).length, 0);
});

test("plan helpers extract commands, variables, and warnings", () => {
  const currentPlan = plan({
    steps: [
      planned("a", {
        warnings: [{ code: "warn", message: "check", severity: "warning" }],
      }),
      planned("b", { variables: ["ports", "target"] }),
    ],
  });
  assert.equal(
    plannedCommand(planned("a"), { target: "host.local" }),
    "echo host.local a",
  );
  assert.deepEqual(planVariables(currentPlan), ["ports", "target"]);
  assert.equal(planWarnings(currentPlan).length, 1);
});

test("groupRecommendations sorts each kind by score", () => {
  const rows: Recommendation[] = [
    {
      kind: "snippet",
      key: "nmap",
      score: 1,
      reason: "r",
      title: "Nmap",
      meta: {},
    },
    {
      kind: "playbook",
      key: "recon",
      score: 2,
      reason: "r",
      title: "Recon",
      meta: {},
    },
    {
      kind: "snippet",
      key: "smb",
      score: 3,
      reason: "r",
      title: "SMB",
      meta: {},
    },
  ];
  const groups = groupRecommendations(rows);
  assert.deepEqual(
    groups.get("snippet")?.map((item) => item.key),
    ["smb", "nmap"],
  );
  assert.equal(groups.get("playbook")?.length, 1);
  assert.equal(groups.has("template"), false);
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface FetchCall {
  url: string;
  body: Record<string, unknown>;
}

function fakeClient(): { client: PlaybooksClient; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({
      url,
      body: JSON.parse(String(init.body ?? "{}")) as Record<string, unknown>,
    });
    return json({ ok: true, data: { route: url.split("/").pop(), ok: true } });
  }) as typeof globalThis.fetch;
  return {
    client: new PlaybooksClient({ fetch, requestId: () => "req_test" }),
    calls,
  };
}

test("PlaybooksClient posts v2 envelopes for catalog and mutation routes", async () => {
  const { client, calls } = fakeClient();
  await client.listPlaybooks({ query: "nmap", tags: ["recon"], limit: 20 });
  await client.getPlaybook("recon-basic");
  await client.createPlaybook({
    key: "custom",
    title: "Custom",
    description: "d",
    status: "draft",
    category: "recon",
    tags: [],
    version: "1.0.0",
    steps: [],
    variables: [],
    owner: "",
    created_at: "",
    updated_at: "",
    references: [],
  });
  await client.updatePlaybook("custom", { title: "Renamed" });
  await client.clonePlaybook("custom");
  await client.deletePlaybook("custom");
  await client.reset();

  assert.deepEqual(
    calls.map((call) => call.url.split("/").pop()),
    [
      "playbooks.list",
      "playbooks.get",
      "playbooks.create",
      "playbooks.update",
      "playbooks.clone",
      "playbooks.delete",
      "playbooks.reset",
    ],
  );
  assert.deepEqual(calls[0]?.body, {
    query: "nmap",
    tags: ["recon"],
    limit: 20,
  });
  assert.deepEqual(calls[1]?.body, { key: "recon-basic" });
  assert.deepEqual(calls[3]?.body, { key: "custom", title: "Renamed" });
});

test("PlaybooksClient maps steps, variables, snippets, and templates to route names", async () => {
  const { client, calls } = fakeClient();
  await client.addStep("demo", { id: "a", title: "A" });
  await client.updateStep("demo", "a", { title: "B" });
  await client.moveStep("demo", "a", 2);
  await client.linkSteps("demo", "b", "a");
  await client.unlinkSteps("demo", "b", "a");
  await client.setStepChecklist("demo", "a", [checklist("x")]);
  await client.addVariable("demo", { key: "target" });
  await client.removeVariable("demo", "target");
  await client.resolveVariables("demo", { target: "x" }, "x", true);
  await client.useSnippet("nmap-basic", { target: "x" });
  await client.composeSnippets(["nmap-basic", "smbclient-shares"]);
  await client.renderTemplate("report", { title: "T" }, "x", false);

  assert.deepEqual(
    calls.map((call) => call.url.split("/").pop()),
    [
      "steps.add",
      "steps.update",
      "steps.move",
      "steps.link",
      "steps.unlink",
      "steps.checklist",
      "variables.add",
      "variables.remove",
      "variables.resolve",
      "snippets.use",
      "snippets.compose",
      "templates.render",
    ],
  );
  assert.deepEqual(calls[2]?.body, { key: "demo", step_id: "a", position: 2 });
  assert.deepEqual(calls[11]?.body, {
    key: "report",
    values: { title: "T" },
    target: "x",
    strict: false,
  });
});

test("PlaybooksClient maps run lifecycle routes and keeps payload keys stable", async () => {
  const { client, calls } = fakeClient();
  await client.planRun("demo", { target: "x" });
  await client.previewRun("demo", { target: "x" });
  await client.startRun("demo", { target: "x" });
  await client.listRuns("demo", { limit: 5 });
  await client.getRun(9);
  await client.nextStep(9);
  await client.advanceRun(9, "a", "skipped", "not needed", "output");
  await client.runProgress(9);
  await client.runChecklist(9);
  await client.setRunChecklist(9, "a-check", "done", "verified");
  await client.cancelRun(9, "scope change");

  assert.deepEqual(
    calls.map((call) => call.url.split("/").pop()),
    [
      "runs.plan",
      "runs.preview",
      "runs.start",
      "runs.list",
      "runs.get",
      "runs.next",
      "runs.advance",
      "runs.progress",
      "runs.checklist",
      "runs.set_checklist",
      "runs.cancel",
    ],
  );
  assert.deepEqual(calls[6]?.body, {
    id: 9,
    step_id: "a",
    status: "skipped",
    message: "not needed",
    output: "output",
    variables: {},
  });
  assert.deepEqual(calls[9]?.body, {
    id: 9,
    item_id: "a-check",
    state: "done",
    note: "verified",
  });
  assert.deepEqual(calls[10]?.body, { id: 9, reason: "scope change" });
});

test("PlaybooksClient wraps envelope errors and supports an injected V2Client", async () => {
  const fetch = (async () =>
    json(
      { ok: false, error: { code: "not_found", message: "Missing playbook" } },
      404,
    )) as typeof globalThis.fetch;
  const client = new PlaybooksClient({ fetch });
  await assert.rejects(client.getPlaybook("missing"), (error: unknown) => {
    assert.equal((error as { code?: string }).code, "not_found");
    assert.equal((error as { status?: number }).status, 404);
    return true;
  });
  const { client: second } = fakeClient();
  assert.equal(second.client.basePath, "/api/v2");
});
