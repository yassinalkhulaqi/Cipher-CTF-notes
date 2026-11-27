import assert from "node:assert/strict";
import test from "node:test";

import {
  FIELD_LABELS,
  OPERATOR_LABELS,
  QUERY_FIELDS,
  QUERY_OPERATORS,
  QueryLanguageClient,
  V4ApiError,
  buildSearchPath,
} from "../src/features/query-language/client";
import type {
  QueryField,
  SavedQueryView,
  SearchResponse,
} from "../src/features/query-language/client";
import {
  appendClause,
  buildFacetSelections,
  highlightExpression,
  initialQueryState,
  queryReducer,
  resultLabel,
  selectedFacetCount,
  toggleFacetValues,
} from "../src/features/query-language/state";
import { V4Client } from "../src/features/v4-kernel/client";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function searchResponse(total = 2): SearchResponse {
  return {
    expression: "title:contains(sql)",
    normalized: "title:contains(sql)",
    token_count: 1,
    hits: {
      items: [{ id: "n1", title: "SQL playbook", tags: ["web"] }],
      total,
      page: 1,
      page_size: 10,
      next_cursor: "",
      etag: '"etag"',
    },
    facets: [
      {
        field: "tag",
        label: "Tag",
        values: [{ value: "web", count: 1, selected: false }],
      },
    ],
    clusters: [{ key: "web", count: 1, sample_ids: ["n1"] }],
    cluster_summary: { clusters: 1, results: total },
    warnings: [],
    cursor_applied: false,
  };
}

const savedQuery: SavedQueryView = {
  id: "11111111-2222-3333-4444-555555555555",
  name: "sql hunt",
  expression: "title:contains(sql)",
  created_at: "2026-01-01T00:00:00.000Z",
};

function fakeClient(
  handler: (url: string, init: RequestInit) => Response | Promise<Response>,
): QueryLanguageClient {
  const fetchImpl = (async (input: RequestInfo | URL, init: RequestInit = {}) =>
    handler(String(input), init)) as typeof globalThis.fetch;
  return new QueryLanguageClient(new V4Client("/api/v4", fetchImpl));
}

test("field and operator vocabularies are complete and labelled", () => {
  assert.equal(QUERY_FIELDS.length, 8);
  assert.equal(QUERY_OPERATORS.length, 7);
  for (const field of QUERY_FIELDS) assert.ok(FIELD_LABELS[field]);
  for (const operator of QUERY_OPERATORS) assert.ok(OPERATOR_LABELS[operator]);
  assert.equal(FIELD_LABELS.tag, "Tag");
  assert.equal(OPERATOR_LABELS.contains, "contains");
});

test("buildSearchPath encodes all structured parameters", () => {
  const path = buildSearchPath({
    expression: "title:contains(sql)",
    page: 2,
    pageSize: 25,
    facets: ["tag", "status"],
    clusterField: "kind",
    rank: true,
    cursor: "v1.abc",
    selectedFacets: { tag: ["web", "ctf"] },
  });
  assert.ok(path.startsWith("/query?"));
  const params = new URLSearchParams(path.split("?")[1]);
  assert.equal(params.get("expression"), "title:contains(sql)");
  assert.equal(params.get("page"), "2");
  assert.equal(params.get("page_size"), "25");
  assert.equal(params.get("facets"), "tag,status");
  assert.equal(params.get("cluster_field"), "kind");
  assert.equal(params.get("rank"), "true");
  assert.equal(params.get("cursor"), "v1.abc");
  assert.deepEqual(JSON.parse(params.get("facet_selections") ?? "{}"), {
    tag: ["web", "ctf"],
  });
});

test("buildSearchPath omits empty selections and defaults", () => {
  assert.equal(
    buildSearchPath({ expression: "" }),
    "/query?action=search&expression=",
  );
  const path = buildSearchPath({ expression: "x", selectedFacets: {} });
  assert.ok(!path.includes("facet_selections"));
});

test("client decodes a search envelope and sends request headers", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const client = fakeClient((url, init) => {
    calls.push({ url, init });
    return json({
      data: searchResponse(),
      meta: {
        request_id: "req-1",
        version: "v4",
        page: 1,
        page_size: 10,
        etag: 'W/"abc"',
      },
    });
  });
  const envelope = await client.search({
    expression: "title:contains(sql)",
    pageSize: 10,
  });
  assert.equal(envelope.data.token_count, 1);
  assert.equal(envelope.meta.request_id, "req-1");
  assert.ok(calls[0].url.startsWith("/api/v4/query?action=search"));
  const headers = calls[0].init.headers as Record<string, string>;
  assert.equal(headers.Accept, "application/json");
  assert.ok(headers["X-Request-ID"]);
});

test("client raises V4ApiError for error envelopes", async () => {
  const client = fakeClient(() =>
    json(
      {
        error: {
          code: "invalid_input",
          message: "bad expression",
          details: ["position=0"],
        },
      },
      400,
    ),
  );
  await assert.rejects(
    () => client.search({ expression: "bogus:x" }),
    (error: unknown) => {
      assert.ok(error instanceof V4ApiError);
      assert.equal(error.code, "invalid_input");
      assert.equal(error.message, "bad expression");
      assert.deepEqual(error.details, ["position=0"]);
      return true;
    },
  );
});

test("client saved-query methods send expected actions", async () => {
  const actions: string[] = [];
  const client = fakeClient((url, init) => {
    if (String(init.method ?? "GET") === "GET") {
      actions.push("list");
      return json({
        data: [savedQuery],
        meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
      });
    }
    const body = JSON.parse(String(init.body ?? "{}")) as { action: string };
    actions.push(body.action);
    if (body.action === "export") {
      return json({
        data: { json: "{}", count: 1 },
        meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
      });
    }
    return json({
      data: body.action === "delete" ? { deleted: savedQuery } : savedQuery,
      meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
    });
  });
  const listed = await client.listSaved(1, 5);
  assert.equal(listed.data[0].name, "sql hunt");
  assert.deepEqual(
    await client.save("sql hunt", "title:contains(sql)"),
    savedQuery,
  );
  assert.deepEqual(await client.rename(savedQuery.id, "renamed"), savedQuery);
  await client.remove(savedQuery.id);
  assert.equal((await client.exportSaved()).count, 1);
  assert.deepEqual(actions, ["list", "save", "rename", "delete", "export"]);
});

test("initial state is deterministic and copy-safe", () => {
  const saved = [savedQuery];
  const state = initialQueryState(saved);
  assert.equal(state.expression, "");
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 10);
  assert.equal(state.loading, false);
  assert.deepEqual(state.savedQueries, saved);
  state.savedQueries.pop();
  assert.equal(saved.length, 1);
});

test("reducer handles expression, submit, loading, and errors", () => {
  let state = initialQueryState();
  state = queryReducer(state, { type: "expression", value: " title:x " });
  assert.equal(state.expression, " title:x ");
  state = queryReducer(state, { type: "submit" });
  assert.equal(state.submittedExpression, "title:x");
  state = queryReducer(state, { type: "loading", value: true });
  assert.equal(state.loading, true);
  state = queryReducer(state, { type: "error", message: "boom" });
  assert.equal(state.error, "boom");
  assert.equal(state.loading, false);
});

test("reducer stores results and resets loading", () => {
  let state = queryReducer(initialQueryState(), {
    type: "loading",
    value: true,
  });
  state = queryReducer(state, { type: "results", response: searchResponse(9) });
  assert.equal(state.total, 9);
  assert.equal(state.results.length, 1);
  assert.equal(state.facets[0].label, "Tag");
  assert.equal(state.clusters[0].key, "web");
  assert.equal(state.pageSize, 10);
  assert.equal(state.loading, false);
});

test("reducer toggles facets case-insensitively and clears them", () => {
  let state = initialQueryState();
  state = queryReducer(state, {
    type: "toggle-facet",
    field: "tag",
    value: "web",
  });
  assert.deepEqual(state.selectedFacets, { tag: ["web"] });
  assert.equal(selectedFacetCount(state), 1);
  state = queryReducer(state, {
    type: "toggle-facet",
    field: "tag",
    value: "WEB",
  });
  assert.deepEqual(state.selectedFacets, { tag: [] });
  state = queryReducer(state, {
    type: "toggle-facet",
    field: "status",
    value: "open",
  });
  assert.equal(selectedFacetCount(state), 1);
  assert.deepEqual(buildFacetSelections(state), { status: ["open"] });
  state = queryReducer(state, { type: "clear-facets" });
  assert.deepEqual(buildFacetSelections(state), {});
});

test("toggleFacetValues preserves other fields", () => {
  const next = toggleFacetValues(
    { tag: ["web"], status: ["open"] },
    "status",
    "closed",
  );
  assert.deepEqual(next, { tag: ["web"], status: ["open", "closed"] });
});

test("reducer applies saved queries, clauses, and pages", () => {
  let state = initialQueryState([savedQuery]);
  state = queryReducer(state, { type: "apply-saved", query: savedQuery });
  assert.equal(state.expression, "title:contains(sql)");
  assert.equal(state.saveName, "sql hunt");
  assert.equal(state.activeChip, savedQuery.id);
  state = queryReducer(state, {
    type: "apply-clause",
    field: "tag",
    operator: "in",
    value: "web,ctf",
  });
  assert.equal(state.expression, "title:contains(sql) AND tag:in(web,ctf)");
  state = queryReducer(state, { type: "page", value: 0 });
  assert.equal(state.page, 1);
  state = queryReducer(state, { type: "page", value: 4 });
  assert.equal(state.page, 4);
  state = queryReducer(state, { type: "save-name", value: "new name" });
  assert.equal(state.saveName, "new name");
  state = queryReducer(state, { type: "reset" });
  assert.equal(state.expression, "");
  assert.deepEqual(state.savedQueries, [savedQuery]);
});

test("appendClause handles empty expressions and quoted values", () => {
  assert.equal(
    appendClause("", "title", "contains", "sql"),
    "title:contains(sql)",
  );
  assert.equal(appendClause("title:x", "title", "=", ""), "title:x");
  assert.equal(
    appendClause("", "title", "=", "sql injection"),
    'title:"sql injection"',
  );
  assert.equal(
    appendClause("title:x", "author", "starts_with", "ada"),
    "title:x AND author:starts_with(ada)",
  );
});

test("highlightExpression classifies syntax parts", () => {
  const segments = highlightExpression(
    "title:contains(sql) AND tag:in(web,ctf)",
  );
  const kinds = segments.map((segment) => segment.kind);
  assert.ok(kinds.includes("field"));
  assert.ok(kinds.includes("operator"));
  assert.ok(kinds.includes("boolean"));
  assert.ok(kinds.includes("value"));
  assert.equal(
    segments
      .filter((segment) => segment.kind === "boolean")
      .map((item) => item.text)
      .join(""),
    "AND",
  );
  assert.deepEqual(highlightExpression(""), []);
});

test("highlightExpression keeps quoted values intact", () => {
  const segments = highlightExpression('body:"hello world"');
  assert.equal(
    segments.find((segment) => segment.text === '"hello world"')?.kind,
    "value",
  );
});

test("resultLabel falls back to id then placeholder", () => {
  assert.equal(resultLabel({ id: "n1" }), "n1");
  assert.equal(resultLabel({ title: "SQL" }), "SQL");
  assert.equal(resultLabel({}), "Untitled result");
});

test("QUERY_FIELDS list matches the field label keys", () => {
  const fields: QueryField[] = QUERY_FIELDS;
  assert.deepEqual(fields, Object.keys(FIELD_LABELS));
});
