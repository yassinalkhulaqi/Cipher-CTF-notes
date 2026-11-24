import assert from "node:assert/strict";
import test from "node:test";

import { V3Client } from "../src/v3/apiClient";
import { ReportDesignerClient } from "../src/features/report-designer/client";
import {
  FORMAT_LABELS,
  ZOOM_LEVELS,
  clampZoom,
  countFindings,
  countSectionFindings,
  designSignature,
  formatBytes,
  formatCount,
  kindLabel,
  pageLabel,
  paginationStats,
  parseList,
  redactionSummary,
  severityClass,
  severityLabel,
  severityRank,
  tocLine,
  truncate,
  visibleSectionCount,
  zoomLabel,
  zoomScale,
  zoomStep,
} from "../src/features/report-designer/format";
import {
  DESIGN_FORMATS,
  designerReducer,
  designerSignature,
  initialDesignerState,
  sectionsToLayout,
  specFromState,
} from "../src/features/report-designer/state";
import type {
  PaginationPlan,
  RedactionPreview,
} from "../src/features/report-designer/types";

function envelope(data: unknown): Response {
  return new Response(
    JSON.stringify({ data, meta: { request_id: "r", api_version: "3.0" } }),
    {
      status: 200,
      headers: { "Content-Type": "application/json" },
    },
  );
}

function fakeClient(
  handler: (action: string, body: Record<string, unknown>) => unknown,
) {
  const calls: Array<{ action: string; body: Record<string, unknown> }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    const url = String(input);
    const action = url.slice(url.lastIndexOf("/") + 1);
    const body = JSON.parse(String(init.body ?? "{}")) as Record<
      string,
      unknown
    >;
    calls.push({ action, body });
    return envelope(handler(action, body));
  }) as typeof globalThis.fetch;
  return {
    calls,
    client: new ReportDesignerClient(
      new V3Client({ fetch: fetchImpl, requestId: () => "req_rd" }),
    ),
  };
}

const plan: PaginationPlan = {
  document_key: "doc",
  theme: "client",
  total_pages: 3,
  lines_per_page: 10,
  pages: [
    {
      index: 1,
      anchor: "page-1",
      items: [],
      used_lines: 4,
      capacity: 10,
      forced_break: true,
    },
    {
      index: 2,
      anchor: "page-2",
      items: [],
      used_lines: 8,
      capacity: 10,
      forced_break: false,
    },
    {
      index: 3,
      anchor: "page-3",
      items: [],
      used_lines: 6,
      capacity: 10,
      forced_break: false,
    },
  ],
  anchors: { "sec-a": 2 },
  finding_pages: { "f-1": 2 },
};

const preview: RedactionPreview = {
  text: "[EMAIL]",
  spans: [
    {
      rule: "email",
      start: 7,
      end: 24,
      matched: "admin@example.com",
      replacement: "[EMAIL]",
      before: "Contact ",
      after: " today",
      section_key: "intro",
      field: "body",
    },
  ],
  applied: ["email"],
  counts: { email: 1 },
  total_matches: 1,
  is_complete: true,
};

test("zoom helpers snap to presets", () => {
  assert.deepEqual([...ZOOM_LEVELS], [50, 75, 100, 125, 150]);
  assert.equal(clampZoom(113), 125);
  assert.equal(clampZoom(112), 100);
  assert.equal(clampZoom(Number.NaN), 100);
  assert.equal(zoomStep(100, 1), 125);
  assert.equal(zoomStep(100, -1), 75);
  assert.equal(zoomStep(150, 1), 150);
  assert.equal(zoomStep(50, -1), 50);
  assert.equal(zoomLabel(125), "125%");
  assert.equal(zoomScale(150), 1.5);
});

test("severity helpers", () => {
  assert.equal(severityRank("critical"), 4);
  assert.equal(severityRank("info"), 0);
  assert.equal(severityLabel("info"), "Informational");
  assert.equal(severityClass("high"), "rd-sev-high");
});

test("text and page helpers", () => {
  assert.equal(pageLabel(2, 5), "Page 2 of 5");
  assert.equal(pageLabel(0, 5), "Page —");
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(formatBytes(-1), "0 B");
  assert.equal(kindLabel("executive_summary"), "Executive Summary");
  assert.equal(truncate("abcdef", 4), "abc…");
  assert.equal(truncate("abc", 4), "abc");
  assert.deepEqual(parseList("a, b\na,, c"), ["a", "b", "c"]);
  assert.equal(
    tocLine(
      { title: "Overview", anchor: "sec-a", page: 2, level: 2, kind: "text" },
      5,
    ),
    "  Overview — Page 2 of 5",
  );
});

test("tree and statistics helpers", () => {
  assert.equal(visibleSectionCount([]), 0);
  assert.equal(countFindings([{}, {}] as never), 2);
  assert.equal(
    countSectionFindings([
      {
        findings: [{}],
        children: [{ findings: [{}, {}], children: [] }],
      },
    ] as never),
    3,
  );
  assert.deepEqual(paginationStats(plan), { pages: 3, items: 0, fills: 0.6 });
  assert.equal(redactionSummary(preview), "1 match · email");
  assert.equal(FORMAT_LABELS.print, "Print CSS");
  assert.deepEqual(DESIGN_FORMATS, ["html", "markdown", "json", "print"]);
});

test("design signature is order independent", () => {
  assert.equal(
    designSignature({ b: 1, a: [2, 3] }),
    designSignature({ a: [2, 3], b: 1 }),
  );
  assert.notEqual(designSignature({ a: 1 }), designSignature({ a: 2 }));
});

test("reducer reorders and toggles sections", () => {
  let state = initialDesignerState();
  const before = state.sections.map((section) => section.key);
  state = designerReducer(state, {
    type: "moveSection",
    key: before[2],
    delta: -1,
  });
  assert.deepEqual(
    state.sections.map((section) => section.key),
    [before[0], before[2], before[1]],
  );
  assert.deepEqual(
    state.sections.map((section) => section.order),
    [0, 1, 2],
  );
  state = designerReducer(state, { type: "dropSection", from: 0, to: 2 });
  assert.equal(state.sections[2].key, before[0]);
  state = designerReducer(state, {
    type: "toggleVisible",
    key: state.sections[0].key,
  });
  assert.equal(state.sections[0].visible, false);
  state = designerReducer(state, {
    type: "toggleToc",
    key: state.sections[0].key,
  });
  assert.equal(state.sections[0].includeToc, false);
  state = designerReducer(state, {
    type: "togglePageBreak",
    key: state.sections[0].key,
  });
  assert.equal(state.sections[0].pageBreakBefore, true);
  state = designerReducer(state, { type: "addSection", kind: "appendix" });
  assert.equal(state.sections.length, 4);
  state = designerReducer(state, {
    type: "removeSection",
    key: state.selectedSection,
  });
  assert.equal(state.sections.length, 3);
  assert.deepEqual(
    state.sections.map((section) => section.order),
    [0, 1, 2],
  );
});

test("reducer manages findings, redactions, formats and preview", () => {
  let state = initialDesignerState();
  const ref = state.findings[0].ref;
  state = designerReducer(state, { type: "toggleFinding", ref });
  assert.deepEqual(state.excluded, [ref]);
  const spec = specFromState(state);
  assert.equal(spec.rules[0].action, "exclude");
  assert.equal(spec.rules[0].identifier, ref);
  state = designerReducer(state, { type: "toggleFinding", ref });
  assert.deepEqual(state.excluded, []);

  state = designerReducer(state, {
    type: "updateRedaction",
    index: 0,
    patch: { enabled: false },
  });
  assert.equal(state.redactions[0].enabled, false);
  state = designerReducer(state, { type: "removeRedaction", index: 0 });
  assert.equal(state.redactions.length, 1);
  state = designerReducer(state, { type: "addRedaction" });
  assert.equal(state.redactions.length, 2);

  state = designerReducer(state, { type: "toggleFormat", format: "json" });
  assert.equal(state.formats.includes("json"), false);
  state = designerReducer(state, { type: "toggleFormat", format: "json" });
  assert.equal(state.formats.includes("json"), true);
  state = designerReducer(state, {
    type: "setOption",
    name: "toc",
    value: false,
  });
  assert.equal(state.options.toc, false);
  state = designerReducer(state, { type: "zoom", value: 150 });
  assert.equal(state.zoom, 150);
  state = designerReducer(state, { type: "activeFormat", value: "markdown" });
  assert.equal(state.activeFormat, "markdown");
  state = designerReducer(state, { type: "togglePrintPreview" });
  assert.equal(state.printPreview, true);
  state = designerReducer(state, { type: "toggleRedactions" });
  assert.equal(state.showRedactions, false);
  state = designerReducer(state, { type: "status", value: "loading" });
  assert.equal(state.status, "loading");
  state = designerReducer(state, { type: "error", value: "boom" });
  assert.equal(state.error, "boom");
  state = designerReducer(state, {
    type: "field",
    field: "title",
    value: "New title",
  });
  assert.equal(state.title, "New title");
  state = designerReducer(state, { type: "theme", value: "technical" });
  assert.equal(state.theme, "technical");
  assert.equal(designerSignature(state).length > 0, true);
});

test("specFromState serializes layout sections", () => {
  const state = initialDesignerState();
  const spec = specFromState(state);
  assert.equal(spec.title, state.title);
  assert.equal(spec.sections.length, state.sections.length);
  assert.equal(spec.formats.length, 4);
  const layout = sectionsToLayout(state.sections);
  assert.equal(layout[0].anchor, "sec-executive-summary");
  assert.equal(layout[0].visible, true);
  assert.equal(layout[0].include_toc, true);
  assert.equal(layout[0].metadata && Object.keys(layout[0].metadata).length, 0);
});

test("client dispatches reports routes and sends the spec", async () => {
  const { client, calls } = fakeClient((action) => {
    if (action === "health")
      return { status: "ok", formats: ["html"], themes: 4 };
    if (action === "themes")
      return { default: "client", themes: [], summaries: [] };
    return { ok: true, action };
  });
  const health = await client.health();
  assert.equal(health.status, "ok");
  const themes = await client.themes();
  assert.equal(themes.default, "client");
  const spec = specFromState(initialDesignerState());
  await client.design(spec);
  await client.preview(spec);
  await client.paginate(spec);
  await client.manifest(spec);
  await client.redact(spec);
  await client.validate(spec);
  await client.render(spec, "html");
  await client.formats();
  assert.deepEqual(
    calls.map((call) => call.action),
    [
      "health",
      "themes",
      "design",
      "preview",
      "paginate",
      "manifest",
      "redact",
      "validate",
      "render",
      "formats",
    ],
  );
  const renderCall = calls.find((call) => call.action === "render");
  assert.equal(renderCall?.body.format, "html");
  assert.equal(client.routes.design, "reports.design");
});
