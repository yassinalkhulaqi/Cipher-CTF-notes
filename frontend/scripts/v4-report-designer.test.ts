import assert from "node:assert/strict";
import test from "node:test";

import { ReportDesignerClient } from "../src/features/report-designer/v4/client";
import type { ReportLayoutV4 } from "../src/features/report-designer/v4/client";
import {
  lineRows,
  sectionRowLabel,
  themeOptions,
} from "../src/features/report-designer/v4/PageDesigner";
import {
  SECTION_KINDS,
  ZOOM_MODES,
  canMoveSection,
  describeState,
  initialDesignerState,
  pageDimensions,
  pageSummary,
  reduceDesigner,
  sectionTitle,
  selectedSection,
  statusTone,
  visiblePage,
  zoomScale,
} from "../src/features/report-designer/v4/state";
import { V4ApiError, V4Client } from "../src/features/v4-kernel/client";
import type { V4Envelope, V4Error } from "../src/features/v4-kernel/types-v4";

function sampleLayout(): ReportLayoutV4 {
  return {
    id: "fixture.layout",
    title: "Fixture report",
    subtitle: "Draft",
    theme: "classic",
    page_size: "a4",
    orientation: "portrait",
    sections: [
      { kind: "cover", title: "Cover", entries: [], page_break_before: true },
      {
        kind: "findings",
        title: "Findings",
        entries: [],
        page_break_before: true,
      },
    ],
    created_at: "",
  };
}

test("initial designer state is deterministic and isolated", () => {
  const first = initialDesignerState();
  const second = initialDesignerState();
  assert.deepEqual(first, second);
  assert.equal(first.layout.title, "Untitled report");
  assert.equal(first.layout.theme, "classic");
  assert.equal(first.layout.page_size, "a4");
  assert.equal(first.zoom, "fit");
  assert.equal(first.format, "html");
  assert.equal(first.previewPage, 1);
  const withLayout = initialDesignerState({ title: "Custom", sections: [] });
  withLayout.layout.sections.push({
    kind: "appendix",
    title: "Appendix",
    entries: [],
    page_break_before: false,
  });
  assert.equal(initialDesignerState().layout.sections.length, 0);
});

test("metadata actions update geometry and description without mutation", () => {
  const start = initialDesignerState();
  const titled = reduceDesigner(start, {
    type: "set-title",
    title: "Engagement",
  });
  assert.equal(titled.layout.title, "Engagement");
  assert.equal(start.layout.title, "Untitled report");
  let state = reduceDesigner(titled, {
    type: "set-subtitle",
    subtitle: "Final",
  });
  state = reduceDesigner(state, { type: "select-theme", theme: "ink" });
  state = reduceDesigner(state, { type: "set-page-size", pageSize: "letter" });
  state = reduceDesigner(state, {
    type: "set-orientation",
    orientation: "landscape",
  });
  state = reduceDesigner(state, { type: "set-zoom", zoom: "125" });
  state = reduceDesigner(state, { type: "set-format", format: "markdown" });
  state = reduceDesigner(state, {
    type: "set-status",
    status: "ready",
    message: "Rendered",
  });
  assert.equal(state.layout.subtitle, "Final");
  assert.equal(state.layout.theme, "ink");
  assert.equal(state.layout.page_size, "letter");
  assert.equal(state.layout.orientation, "landscape");
  assert.equal(state.zoom, "125");
  assert.equal(state.format, "markdown");
  assert.equal(state.status, "ready");
  assert.match(
    describeState(state),
    /Engagement · 0 sections · 0 pages · markdown · 125/,
  );
});

test("section actions add, select, toggle, move, and remove", () => {
  let state = initialDesignerState();
  state = reduceDesigner(state, { type: "add-section", kind: "findings" });
  state = reduceDesigner(state, { type: "add-section", kind: "evidence" });
  assert.equal(state.layout.sections.length, 2);
  assert.equal(state.selectedSection, 1);
  assert.equal(state.layout.sections[0].title, "Findings");
  assert.equal(canMoveSection(state, 1, 1), false);
  assert.equal(canMoveSection(state, 1, -1), true);
  state = reduceDesigner(state, { type: "toggle-break", index: 1 });
  assert.equal(state.layout.sections[1].page_break_before, false);
  state = reduceDesigner(state, {
    type: "move-section",
    index: 1,
    direction: -1,
  });
  assert.equal(state.layout.sections[0].kind, "evidence");
  assert.equal(state.selectedSection, 0);
  state = reduceDesigner(state, { type: "select-section", index: 99 });
  assert.equal(state.selectedSection, 1);
  state = reduceDesigner(state, { type: "remove-section", index: 0 });
  assert.equal(state.layout.sections.length, 1);
  const unchanged = reduceDesigner(state, {
    type: "remove-section",
    index: 50,
  });
  assert.equal(unchanged, state);
  assert.equal(
    reduceDesigner(state, { type: "reset" }).layout.title,
    "Untitled report",
  );
});

test("pages clamp the preview window and summarize sections", () => {
  let state = initialDesignerState();
  assert.equal(visiblePage(state), undefined);
  state = reduceDesigner(state, {
    type: "set-pages",
    pages: [
      {
        number: 1,
        section: "cover",
        lines: ["Cover", "Client"],
        title: "Cover",
      },
      {
        number: 2,
        section: "findings",
        lines: ["Findings"],
        title: "Findings",
      },
    ],
  });
  assert.equal(state.previewPage, 1);
  assert.equal(visiblePage(state)?.title, "Cover");
  state = reduceDesigner(state, { type: "set-page", page: 99 });
  assert.equal(state.previewPage, 2);
  state = reduceDesigner(state, { type: "set-page", page: -4 });
  assert.equal(state.previewPage, 1);
  const summary = pageSummary(state.pages);
  assert.equal(summary.total, 2);
  assert.equal(summary.lines, 3);
  assert.equal(summary.firstSection, "Cover");
  assert.equal(summary.byKind.cover, 1);
  assert.equal(summary.byKind.findings, 1);
  assert.equal(summary.byKind.appendix, 0);
});

test("apply layout replaces sections and resets the preview", () => {
  let state = initialDesignerState();
  state = reduceDesigner(state, { type: "set-page", page: 9 });
  state = reduceDesigner(state, {
    type: "apply-layout",
    layout: sampleLayout(),
  });
  assert.equal(state.layout.id, "fixture.layout");
  assert.equal(state.layout.sections.length, 2);
  assert.equal(state.selectedSection, 0);
  assert.equal(state.previewPage, 1);
  assert.equal(state.status, "ready");
  assert.match(state.message, /Fixture report/);
  assert.equal(selectedSection(state)?.kind, "cover");
  assert.equal(state.layout.title, "Fixture report");
});

test("geometry helpers use page size, orientation, and zoom", () => {
  assert.deepEqual(ZOOM_MODES, ["fit", "75", "100", "125"]);
  assert.equal(zoomScale("100"), 1);
  assert.equal(zoomScale("125"), 1.25);
  const portrait = pageDimensions(sampleLayout(), "100");
  assert.equal(portrait.width, 794);
  assert.equal(portrait.height, 1123);
  assert.match(portrait.label, /A4 portrait · 100%/);
  const landscape = pageDimensions(
    { ...sampleLayout(), orientation: "landscape", page_size: "a5" },
    "fit",
  );
  assert.ok(landscape.width > landscape.height);
  assert.equal(landscape.scale, 0.62);
  assert.equal(SECTION_KINDS.length, 5);
  assert.equal(sectionTitle("toc"), "Table of contents");
  assert.equal(statusTone("error"), "danger");
  assert.equal(statusTone("idle"), "muted");
});

test("component helpers format labels and preview lines", () => {
  const section = {
    kind: "findings" as const,
    title: "Findings",
    entries: [],
    page_break_before: true,
  };
  assert.equal(sectionRowLabel(section, 0), "1. Findings · 0 entries");
  assert.deepEqual(lineRows(undefined), []);
  assert.deepEqual(
    lineRows({ number: 3, section: "cover", lines: ["A", ""], title: "Cover" }),
    [
      { key: "3-0", text: "A" },
      { key: "3-1", text: "\u00a0" },
    ],
  );
  assert.deepEqual(themeOptions([]), [
    "classic",
    "modern",
    "compact",
    "ink",
    "client",
  ]);
  assert.deepEqual(
    themeOptions([
      { name: "custom", parent: "", lineage: [], description: "" },
    ]),
    ["custom"],
  );
});

test("client decodes envelopes and forwards action query parameters", async () => {
  let capturedUrl = "";
  const payload = {
    data: {
      items: [{ name: "classic" }],
      total: 1,
      page: 2,
      page_size: 1,
      next_cursor: "",
      etag: "e",
    },
    meta: { request_id: "r1", version: "v4", page: 2, page_size: 1 },
  } satisfies V4Envelope<unknown>;
  const fetchImpl = (async (input: RequestInfo | URL) => {
    capturedUrl = String(input);
    return { status: 200, json: async () => payload } as Response;
  }) as typeof fetch;
  const client = new ReportDesignerClient(new V4Client("/api/v4", fetchImpl));
  const result = await client.themes(2, 1);
  assert.equal(result.data.items.length, 1);
  assert.equal(result.meta.request_id, "r1");
  assert.match(capturedUrl, /\/api\/v4\/reports\?action=themes/);
  assert.match(capturedUrl, /page=2/);
  assert.match(capturedUrl, /page_size=1/);
});

test("client renders layouts with POST envelopes and throws structured errors", async () => {
  const calls: Array<{
    url: string;
    method: string;
    body: string | undefined;
  }> = [];
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: String(init?.method),
      body: init?.body as string,
    });
    if (String(input).includes("action=layout")) {
      const error: V4Error = {
        error: {
          code: "not_found",
          message: "unknown layout",
          details: ["id"],
        },
      };
      return { status: 404, json: async () => error } as Response;
    }
    return {
      status: 200,
      json: async () =>
        ({
          data: { layout_id: "x", format: "html" },
          meta: {},
        }) as V4Envelope<unknown>,
    } as Response;
  }) as typeof fetch;
  const client = new ReportDesignerClient(new V4Client("/api/v4", fetchImpl));
  await client.render("x", "html", "ui");
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].url, "/api/v4/reports");
  assert.deepEqual(JSON.parse(calls[0].body ?? "{}"), {
    action: "render",
    layout_id: "x",
    format: "html",
    trigger: "ui",
  });
  await assert.rejects(
    () => client.layout("missing"),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "not_found",
  );
});
