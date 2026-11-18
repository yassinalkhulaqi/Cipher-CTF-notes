import assert from "node:assert/strict";
import test from "node:test";
import { V2Client } from "../src/lib/apiClient";
import { ReportingClient } from "../src/features/reporting/client";
import {
  compact,
  displayName,
  evidenceLabel,
  formatBytes,
  formatConfidence,
  formatCount,
  formatKey,
  manifestLines,
  previewRows,
  riskClass,
  severityBar,
  severityClass,
  severityLabel,
  severityRank,
  summarizeSeverity,
  truncate,
} from "../src/features/reporting/format";
import {
  REPORT_FORMATS,
  builderReducer,
  configFromState,
  initialBuilderState,
  previewSignature,
  splitList,
} from "../src/features/reporting/state";
import type { SeveritySummary } from "../src/features/reporting/types";

interface FetchCall {
  url: string;
  body: Record<string, unknown>;
}

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

function fakeClient(
  handler: (route: string, body: Record<string, unknown>) => unknown,
): { client: ReportingClient; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const body = bodyOf(init);
    calls.push({ url, body });
    return envelope(handler(routeOf(url), body));
  }) as typeof globalThis.fetch;
  return {
    client: new ReportingClient(
      new V2Client({ fetch, requestId: () => "req_reporting" }),
    ),
    calls,
  };
}

const summary: SeveritySummary = {
  info: 1,
  low: 2,
  medium: 3,
  high: 4,
  critical: 5,
  counts: { info: 1, low: 2, medium: 3, high: 4, critical: 5 },
  total: 15,
  highest: "critical",
  weighted: 45,
  risk_level: "critical",
  bar: "#12345",
  percentages: {
    info: 6.7,
    low: 13.3,
    medium: 20,
    high: 26.7,
    critical: 33.3,
  },
};

test("initial state exposes complete builder defaults", () => {
  const state = initialBuilderState({ title: "Custom" });
  assert.equal(state.title, "Custom");
  assert.equal(state.template, "engagement");
  assert.equal(state.format, "html");
  assert.equal(state.includeEvidence, true);
  assert.equal(state.redactSensitive, true);
  assert.equal(state.preview, null);
  assert.equal(state.error, "");
  assert.deepEqual(REPORT_FORMATS, ["markdown", "html", "json", "print"]);
});

test("configFromState maps camelCase fields to API payload", () => {
  const state = initialBuilderState({
    minimumSeverity: "high",
    pageSize: "letter",
    print_profile_placeholder: undefined,
  } as never);
  const payload = configFromState({ ...state, profile: "landscape" });
  assert.equal(payload.title, "Engagement Report");
  assert.equal(payload.minimum_severity, "high");
  assert.equal(payload.page_size, "letter");
  assert.equal(payload.print_profile, "landscape");
  assert.equal(payload.generated_at, "");
  assert.equal(payload.include_evidence, true);
});

test("reducer handles fields, toggles, lists, formats, and resets", () => {
  let state = initialBuilderState();
  state = builderReducer(state, {
    type: "field",
    field: "title",
    value: "New",
  });
  assert.equal(state.title, "New");
  state = builderReducer(state, {
    type: "toggle",
    field: "includeEvidence",
    value: false,
  });
  assert.equal(state.includeEvidence, false);
  state = builderReducer(state, {
    type: "list",
    field: "tags",
    value: ["web", "active"],
  });
  assert.deepEqual(state.tags, ["web", "active"]);
  state = builderReducer(state, { type: "format", value: "json" });
  assert.equal(state.format, "json");
  state = builderReducer(state, { type: "error", value: "boom" });
  assert.equal(state.error, "boom");
  assert.equal(state.busy, false);
  state = builderReducer(state, { type: "reset" });
  assert.equal(state.title, "Engagement Report");
  assert.equal(state.format, "html");
});

test("reducer stores previews, validation, render output, and redactions", () => {
  let state = initialBuilderState();
  const preview = {
    title: "Report",
    template: "engagement",
    finding_count: 1,
    severity: summary,
    sections: [],
    warnings: [],
    evidence: {},
  };
  state = builderReducer(state, { type: "preview", value: preview });
  assert.equal(state.preview?.finding_count, 1);
  state = builderReducer(state, {
    type: "validation",
    value: { valid: true, errors: 0, warnings: 0, issues: [] },
  });
  assert.equal(state.validation?.valid, true);
  state = builderReducer(state, {
    type: "rendered",
    value: {
      format: "markdown",
      content: "# Report",
      filename: "report.md",
      mime: "text/markdown",
      manifest: { digest: "abc" },
    },
  });
  assert.equal(state.rendered?.filename, "report.md");
  state = builderReducer(state, {
    type: "redaction",
    value: {
      text: "[REDACTED]",
      applied: [],
      counts: {},
      preview: [],
      rules: [],
    },
  });
  assert.equal(state.redaction?.text, "[REDACTED]");
});

test("splitList and previewSignature handle normalization", () => {
  assert.deepEqual(splitList("a, b\nc,, d"), ["a", "b", "c", "d"]);
  const left = initialBuilderState();
  const right = initialBuilderState();
  assert.equal(previewSignature(left), previewSignature(right));
  assert.notEqual(
    previewSignature(left),
    previewSignature(
      builderReducer(left, { type: "field", field: "title", value: "X" }),
    ),
  );
});

test("severity helpers rank, label, and classify values", () => {
  assert.ok(severityRank("critical") > severityRank("high"));
  assert.equal(severityRank("unknown"), -1);
  assert.equal(severityLabel("high"), "High");
  assert.equal(severityLabel("odd"), "odd");
  assert.equal(severityClass("critical"), "severity-critical");
  assert.equal(severityClass("odd"), "severity-info");
  assert.equal(riskClass(" CRITICAL "), "risk-critical");
  assert.equal(riskClass("other"), "risk-info");
});

test("formatting helpers produce readable values", () => {
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatCount(Number.NaN), "0");
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(2048), "2 KB");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatConfidence(0.456), "46%");
  assert.equal(formatConfidence(2), "100%");
  assert.equal(truncate("abcdef", 4), "abc…");
  assert.equal(compact(" a \n b\t c "), "a b c");
  assert.equal(formatKey("  Hello, World! "), "hello-world");
  assert.equal(displayName("print_profile"), "Print Profile");
});

test("severity summaries and preview rows are presentation ready", () => {
  assert.equal(
    summarizeSeverity(summary),
    "1 info · 2 low · 3 medium · 4 high · 5 critical",
  );
  assert.equal(summarizeSeverity(null), "No preview");
  const bar = severityBar(summary);
  assert.equal(bar.length, 5);
  assert.equal(bar[4].name, "critical");
  assert.equal(bar[4].percent, 33.3);
  const preview = {
    title: "Report",
    template: "engagement",
    finding_count: 2,
    severity: summary,
    sections: [
      { identifier: "b", title: "Beta", level: 2, finding_count: 1 },
      { identifier: "a", title: "Alpha", level: 1, finding_count: 2 },
    ],
    warnings: [],
    evidence: {},
  };
  assert.deepEqual(
    previewRows(preview).map((row) => row.identifier),
    ["a", "b"],
  );
  assert.deepEqual(previewRows(null), []);
});

test("manifest and evidence labels are humanized", () => {
  assert.equal(evidenceLabel("findings_with_evidence"), "With evidence");
  assert.equal(evidenceLabel("custom_key"), "custom key");
  const lines = manifestLines({
    source_digest: "abc",
    nested: { ignored: true },
    template_digest: "def",
  });
  assert.deepEqual(lines, ["source digest: abc", "template digest: def"]);
});

test("client fetches metadata from reporting namespace routes", async () => {
  const { client, calls } = fakeClient((route) => {
    if (route === "reporting.health") {
      return {
        ok: true,
        namespace: "reporting",
        formats: ["html"],
        templates: ["ctf"],
        profiles: [],
      };
    }
    if (route === "reporting.templates") {
      return { templates: [{ key: "ctf", name: "CTF" }] };
    }
    if (route === "reporting.template") {
      return { key: "ctf", name: "CTF", sections: [] };
    }
    if (route === "reporting.profiles") {
      return { profiles: [{ name: "standard" }] };
    }
    if (route === "reporting.config_schema") {
      return { version: "1.0.0", fields: [], formats: { formats: ["html"] } };
    }
    if (route === "reporting.sections") {
      return { sections: [], stats: {}, outline: [] };
    }
    return { generated_at: "now", notes: [] };
  });

  const health = await client.health();
  assert.equal(health.namespace, "reporting");
  assert.equal((await client.templates())[0].key, "ctf");
  assert.equal((await client.template("ctf")).key, "ctf");
  assert.equal((await client.profiles())[0].name, "standard");
  assert.equal((await client.configSchema()).version, "1.0.0");
  assert.deepEqual((await client.sections("ctf")).outline, []);
  assert.equal((await client.source({ tag: "web" })).generated_at, "now");
  assert.deepEqual(
    calls.map((call) => routeOf(call.url)),
    [
      "reporting.health",
      "reporting.templates",
      "reporting.template",
      "reporting.profiles",
      "reporting.config_schema",
      "reporting.sections",
      "reporting.source",
    ],
  );
});

test("client posts deterministic bodies for build, render, and export", async () => {
  const { client, calls } = fakeClient((route) => {
    if (route === "reporting.build") return { finding_count: 1 };
    if (route === "reporting.render") {
      return {
        format: "markdown",
        content: "# Report",
        filename: "report.md",
        mime: "text/markdown",
        manifest: {},
      };
    }
    if (route === "reporting.export") {
      return {
        directory: "/tmp/report",
        formats: ["html"],
        outputs: {},
        manifest: {},
      };
    }
    return {};
  });
  const config = { title: "Report", tags: ["web"] };

  await client.build(config, "2026-01-01T00:00:00Z");
  assert.deepEqual(calls[0].body, {
    title: "Report",
    tags: ["web"],
    generated_at: "2026-01-01T00:00:00Z",
  });

  const rendered = await client.render(config, "markdown", "compact");
  assert.equal(rendered.filename, "report.md");
  assert.equal(calls[1].body.format, "markdown");
  assert.equal(calls[1].body.profile, "compact");

  const exported = await client.exportReport(
    config,
    "markdown",
    "/tmp/report",
    "compact",
    "fixed",
  );
  assert.equal(exported.directory, "/tmp/report");
  assert.equal(calls[2].body.directory, "/tmp/report");
  assert.equal(calls[2].body.generated_at, "fixed");
});

test("client covers validation, analytics, and redaction routes", async () => {
  const { client, calls } = fakeClient((route) => {
    if (route === "reporting.validate") {
      return { valid: true, errors: 0, warnings: 0, issues: [] };
    }
    if (route === "reporting.severity") return summary;
    if (route === "reporting.inclusion") return { source_notes: 2 };
    if (route === "reporting.manifest") return { digest: "abc" };
    if (route === "reporting.redact") {
      return {
        text: "[REDACTED]",
        applied: ["flag"],
        counts: { flag: 1 },
        preview: [],
        rules: [],
      };
    }
    if (route === "reporting.redaction_rules") {
      return { rules: [{ name: "flag", pattern: "flag" }] };
    }
    return {};
  });

  assert.equal((await client.validate({ title: "R" })).valid, true);
  assert.equal((await client.severity({ title: "R" })).total, 15);
  assert.equal((await client.inclusion({ title: "R" })).source_notes, 2);
  assert.equal((await client.manifest({ title: "R" })).digest, "abc");
  assert.equal(
    (await client.redact("flag{x}", { context: 4 })).text,
    "[REDACTED]",
  );
  assert.equal((await client.redactionRules(true))[0].name, "flag");
  assert.equal(calls[4].body.context, 4);
  assert.equal(calls[5].body.include_hosts, true);
});

test("client posts section reorder and move payloads", async () => {
  const { client, calls } = fakeClient(() => ({
    sections: [
      { identifier: "b", title: "Beta" },
      { identifier: "a", title: "Alpha" },
    ],
    stats: {},
    outline: [],
  }));
  const sections = [
    { identifier: "a", title: "Alpha" },
    { identifier: "b", title: "Beta" },
  ] as never;

  assert.equal(
    (await client.reorder(sections, "", ["b", "a"])).sections.length,
    2,
  );
  assert.equal(calls[0].body.parent_id, "");
  assert.deepEqual(calls[0].body.order, ["b", "a"]);

  await client.move(sections, "a", "", 1);
  assert.equal(calls[1].body.identifier, "a");
  assert.equal(calls[1].body.index, 1);
});

test("client route map covers every reporting namespace handler", () => {
  const client = new ReportingClient(
    new V2Client({
      fetch: (async () => envelope({})) as typeof globalThis.fetch,
    }),
  );
  const routes = Object.values(client.routes);
  assert.equal(routes.length, 20);
  assert.ok(routes.every((route) => route.startsWith("reporting.")));
  assert.ok(routes.includes("reporting.export"));
  assert.ok(routes.includes("reporting.redaction_rules"));
});
