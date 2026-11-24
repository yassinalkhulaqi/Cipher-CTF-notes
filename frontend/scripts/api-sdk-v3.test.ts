import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiExplorerClient,
  createApiExplorerClient,
} from "../src/features/api-explorer/client";
import {
  MAX_HISTORY,
  capabilitySummary,
  deniedCapabilities,
  exampleManifestText,
  exampleManifestValue,
  filterEntries,
  formatDuration,
  fingerprintOf,
  guardWrite,
  isWriteRoute,
  issueSummary,
  previewResponse,
  pushEntry,
  requestBody,
  responseTone,
  safeParseJson,
  validateManifest,
} from "../src/features/api-explorer/pure";
import type {
  ConsoleEntry,
  ExplorerRequest,
  ExplorerResponse,
} from "../src/features/api-explorer/types";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(patch: Partial<ExplorerRequest> = {}): ExplorerRequest {
  return {
    namespace: "system",
    action: "info",
    bodyText: '{"echo":"hello"}',
    capability: "",
    etag: "",
    idempotencyKey: "",
    allowWrite: false,
    ...patch,
  };
}

function entry(sequence: number, errorCode = ""): ConsoleEntry {
  return {
    id: `e-${sequence}`,
    sequence,
    route: `/api/v3/system/info`,
    status: errorCode ? 400 : 200,
    requestId: `req_${sequence}`,
    etag: "",
    errorCode,
    durationMs: sequence * 2,
    timestamp: sequence,
    cached: false,
    capability: "",
    bodyKeys: ["echo"],
    responsePreview: "{}",
  };
}

function okResponse(): ExplorerResponse {
  return {
    ok: true,
    status: 200,
    requestId: "req_1",
    etag: '"tag"',
    data: { value: 7 },
    errorCode: "",
    errorMessage: "",
    warnings: [],
  };
}

test("safeParseJson parses data and reports errors", () => {
  assert.equal(safeParseJson('{"a":1}').ok, true);
  assert.deepEqual(safeParseJson("[1,2]").value, [1, 2]);
  assert.equal(safeParseJson("").ok, false);
  assert.equal(safeParseJson("{bad").ok, false);
});

test("example manifest validates and has a stable fingerprint", () => {
  const value = exampleManifestValue();
  const first = validateManifest(value);
  const second = validateManifest(JSON.parse(JSON.stringify(value)));
  assert.equal(first.valid, true);
  assert.deepEqual(first.issues, []);
  assert.equal(first.fingerprint, second.fingerprint);
  assert.match(first.fingerprint, /^"[0-9a-f]+"$/);
  assert.equal(first.normalized?.requires[0], "extensions");
  assert.equal(
    issueSummary(first),
    "Manifest is a valid data-only declaration.",
  );
  assert.equal(fingerprintOf({ b: 1, a: 2 }), fingerprintOf({ a: 2, b: 1 }));
});

test("manifest editor rejects executable and malformed declarations", () => {
  const withCode = exampleManifestValue() as Record<string, unknown>;
  withCode.metadata = { code: "eval('1')" };
  const report = validateManifest(withCode);
  assert.equal(report.valid, false);
  assert.ok(report.issues.some((item) => item.code === "forbidden_key"));

  const missing = validateManifest({ schema: "redscribe-extension/1" });
  assert.equal(missing.valid, false);
  assert.ok(missing.issues.some((item) => item.path === "id"));
  assert.ok(missing.issues.some((item) => item.path === "version"));

  const badBinding = exampleManifestValue();
  badBinding.contributions[0] = {
    kind: "shortcut",
    id: "shortcut-1",
    title: "Bad",
    binding: "eval()",
  };
  assert.equal(validateManifest(badBinding).valid, false);
  assert.equal(validateManifest([]).valid, false);
  assert.deepEqual(validateManifest([]).issues[0].code, "invalid_type");
});

test("example manifest text round-trips", () => {
  const parsed = safeParseJson(exampleManifestText());
  assert.equal(parsed.ok, true);
  assert.equal(validateManifest(parsed.value).valid, true);
});

test("write routes require an explicit opt-in", () => {
  assert.equal(isWriteRoute("extensions", "install"), true);
  assert.equal(isWriteRoute("extensions", "list"), false);
  assert.match(
    guardWrite(request({ namespace: "extensions", action: "install" })),
    /explicit write opt-in/,
  );
  assert.equal(
    guardWrite(
      request({ namespace: "extensions", action: "install", allowWrite: true }),
    ),
    "",
  );
});

test("requestBody validates JSON objects", () => {
  assert.deepEqual(requestBody(request()).value, { echo: "hello" });
  assert.equal(requestBody(request({ bodyText: "[]" })).ok, false);
  assert.equal(requestBody(request({ bodyText: "{bad" })).ok, false);
});

test("console history is bounded and filterable", () => {
  let entries: ConsoleEntry[] = [];
  for (let index = 0; index < MAX_HISTORY + 5; index += 1) {
    entries = pushEntry(entries, entry(index));
  }
  assert.equal(entries.length, MAX_HISTORY);
  assert.equal(entries[0].sequence, 5);
  const withError = pushEntry(entries, entry(999, "forbidden"));
  assert.equal(filterEntries(withError, "", true).length, 1);
  assert.equal(filterEntries(withError, "req_999").length, 1);
  assert.equal(filterEntries(withError, "nothing-matches").length, 0);
  assert.equal(formatDuration(-5), "0 ms");
});

test("capability and response presentation helpers", () => {
  const map = { extensions: true, findings: false, graph: false };
  assert.deepEqual(deniedCapabilities(map), ["findings", "graph"]);
  assert.equal(
    capabilitySummary([
      { name: "a", granted: true, reason: "", required_for: "", source: "" },
      { name: "b", granted: false, reason: "", required_for: "", source: "" },
    ]),
    "1/2 capabilities available",
  );
  assert.equal(responseTone(null), "idle");
  assert.equal(responseTone(okResponse()), "success");
  assert.equal(
    responseTone({ ...okResponse(), errorCode: "forbidden", ok: false }),
    "error",
  );
  assert.equal(responseTone({ ...okResponse(), status: 304 }), "cached");
  assert.match(previewResponse(okResponse()), /"value": 7/);
});

test("client sends capability, idempotency, and ETag headers", async () => {
  const seen: RequestInit[] = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    assert.equal(String(input), "/api/v3/system/info");
    seen.push(init);
    return json({
      data: { value: 7 },
      meta: { request_id: "req_test", api_version: "3.0", etag: '"tag"' },
    });
  }) as typeof globalThis.fetch;
  const client = new ApiExplorerClient({
    fetch: fetchImpl,
    requestId: () => "req_test",
  });
  const result = await client.call(
    request({
      capability: "extensions",
      idempotencyKey: "key-1",
      etag: '"old"',
    }),
  );
  assert.equal(result.ok, true);
  assert.equal(result.data && (result.data as { value: number }).value, 7);
  const headers = seen[0].headers as Record<string, string>;
  assert.equal(headers["X-Capability"], "extensions");
  assert.equal(headers["Idempotency-Key"], "key-1");
  assert.equal(headers["If-None-Match"], '"old"');
  assert.equal(headers["X-Request-ID"], "req_test");
});

test("client blocks write routes without opt-in", async () => {
  let calls = 0;
  const fetchImpl = (async () => {
    calls += 1;
    return json({ data: {}, meta: { request_id: "r" } });
  }) as typeof globalThis.fetch;
  const client = createApiExplorerClient({ fetch: fetchImpl });
  const blocked = await client.call(
    request({ namespace: "extensions", action: "install" }),
  );
  assert.equal(blocked.ok, false);
  assert.equal(blocked.errorCode, "read_only_violation");
  assert.equal(calls, 0);
});

test("client surfaces typed V3 errors", async () => {
  const fetchImpl = (async () =>
    json(
      {
        error: {
          code: "forbidden",
          message: "Capability is unavailable",
          field: "capability",
          retryable: false,
          context: {},
        },
        meta: { request_id: "req_err", api_version: "3.0" },
      },
      403,
    )) as typeof globalThis.fetch;
  const client = new ApiExplorerClient({ fetch: fetchImpl });
  const result = await client.call(request({ capability: "findings" }));
  assert.equal(result.ok, false);
  assert.equal(result.status, 403);
  assert.equal(result.errorCode, "forbidden");
  assert.equal(result.requestId, "req_err");
});

test("client maps route manifests and validation reports", async () => {
  const fetchImpl = (async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/system/manifest")) {
      return json({
        data: {
          version: "3.0",
          namespaces: ["system"],
          routes: [
            { path: "/api/v3/system/info", methods: ["POST"], public: true },
          ],
        },
        meta: { request_id: "r1" },
      });
    }
    return json({
      data: { valid: true, issues: [], fingerprint: '"abc"', normalized: null },
      meta: { request_id: "r2" },
    });
  }) as typeof globalThis.fetch;
  const client = new ApiExplorerClient({ fetch: fetchImpl });
  const routes = await client.routes();
  assert.equal(routes.length, 1);
  assert.equal(routes[0].path, "/api/v3/system/info");
  const report = await client.validate(exampleManifestValue());
  assert.equal(report.valid, true);
  assert.equal(report.fingerprint, '"abc"');
});

test("client reads paginated results", async () => {
  const fetchImpl = (async () =>
    json({
      data: { items: [1, 2], next_cursor: "cursor-2" },
      meta: {
        request_id: "r3",
        page: {
          page: 1,
          page_size: 2,
          total: 5,
          has_next: true,
          has_previous: false,
        },
      },
    })) as typeof globalThis.fetch;
  const client = new ApiExplorerClient({ fetch: fetchImpl });
  const page = await client.page(
    request({ namespace: "extensions", action: "list" }),
    2,
  );
  assert.deepEqual(page.items, [1, 2]);
  assert.equal(page.total, 5);
  assert.equal(page.hasNext, true);
  assert.equal(page.cursor, "cursor-2");
});
