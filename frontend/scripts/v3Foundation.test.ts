import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiClientError,
  V3Client,
  isAbortError,
  nextCursor,
} from "../src/v3/apiClient";
import {
  clearRegistries,
  listCommands,
  listFeatures,
  registerCommand,
  registerFeature,
  registrySnapshot,
  searchCommands,
} from "../src/v3/registry";
import { isEnvelope, unwrap } from "../src/v3/types";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("client decodes v3 envelopes and sends headers", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    calls.push({ url: String(input), init });
    return json({
      data: { value: 7 },
      meta: { request_id: "r1", api_version: "3.0" },
    });
  }) as typeof globalThis.fetch;
  const client = new V3Client({
    fetch: fetchImpl,
    requestId: () => "req_test",
  });
  const envelope = await client.call<{ value: number }>("system", "info");
  assert.deepEqual(envelope.data, { value: 7 });
  assert.equal(calls[0].url, "/api/v3/system/info");
  const headers = calls[0].init.headers as Record<string, string>;
  assert.equal(headers["X-Request-ID"], "req_test");
  assert.equal(calls[0].init.method, "POST");
});

test("client raises typed errors", async () => {
  const fetchImpl = (async () =>
    json(
      {
        error: {
          code: "not_found",
          message: "Unknown finding",
          field: "ref",
          retryable: false,
          context: {},
        },
        meta: { request_id: "r2", api_version: "3.0" },
      },
      404,
    )) as typeof globalThis.fetch;
  const client = new V3Client({ fetch: fetchImpl });
  await assert.rejects(
    () => client.data("findings", "get", { ref: "x" }),
    (error: unknown) => {
      assert.ok(error instanceof ApiClientError);
      assert.equal(error.code, "not_found");
      assert.equal(error.status, 404);
      assert.equal(error.field, "ref");
      return true;
    },
  );
});

test("client list extracts page metadata", async () => {
  const fetchImpl = (async () =>
    json({
      data: [1, 2],
      meta: {
        request_id: "r3",
        api_version: "3.0",
        etag: '"tag"',
        page: {
          page: 1,
          page_size: 2,
          total: 5,
          has_next: true,
          has_previous: false,
        },
      },
    })) as typeof globalThis.fetch;
  const client = new V3Client({ fetch: fetchImpl });
  const result = await client.list<number>("notes", "list");
  assert.deepEqual(result.items, [1, 2]);
  assert.equal(result.page?.total, 5);
  assert.equal(result.etag, '"tag"');
  assert.equal(nextCursor(result.page), "2");
});

test("envelope guards", () => {
  assert.ok(isEnvelope({ data: 1, meta: {} }));
  assert.equal(isEnvelope({ data: 1 }), false);
  assert.equal(unwrap({ data: 4, meta: {} }), 4);
});

test("registries sort and search", () => {
  clearRegistries();
  registerFeature({ id: "b", label: "Beta", route: "/b", order: 20 });
  registerFeature({ id: "a", label: "Alpha", route: "/a", order: 10 });
  assert.deepEqual(
    listFeatures().map((feature) => feature.id),
    ["a", "b"],
  );
  registerCommand({
    id: "palette",
    title: "Open palette",
    group: "Navigation",
    keywords: ["jump", "search"],
    run: () => undefined,
  });
  registerCommand({
    id: "dashboard",
    title: "Open dashboard",
    group: "Navigation",
    keywords: ["home"],
    run: () => undefined,
  });
  assert.equal(searchCommands("jump").length, 1);
  assert.equal(searchCommands("").length, 2);
  assert.deepEqual(registrySnapshot().commands, ["dashboard", "palette"]);
  clearRegistries();
  assert.equal(listCommands().length, 0);
});

test("abort detection", () => {
  const abort = new Error("cancelled");
  abort.name = "AbortError";
  assert.ok(isAbortError(abort));
  assert.equal(isAbortError(new Error("other")), false);
});
