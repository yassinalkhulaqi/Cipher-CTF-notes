import assert from "node:assert/strict";
import test from "node:test";
import {
  ApiClientError,
  V2Client,
  isAbortError,
  requestId,
  withQuery,
} from "../src/lib/apiClient";

function json(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

type FetchCall = { url: string; init: RequestInit };

function fakeFetch(
  handler: (url: string, init: RequestInit) => Promise<Response>,
): { fetch: typeof globalThis.fetch; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init);
  }) as typeof globalThis.fetch;
  return { fetch, calls };
}

function headersOf(call: FetchCall): Record<string, string> {
  return call.init.headers as Record<string, string>;
}

function bodyOf(call: FetchCall): Record<string, unknown> {
  return JSON.parse(String(call.init.body)) as Record<string, unknown>;
}

test("call parses envelopes, posts JSON, and sends request ids", async () => {
  const { fetch, calls } = fakeFetch(async () =>
    json({ ok: true, data: { value: 7 }, request_id: "server-1" }),
  );
  const client = new V2Client({
    fetch,
    requestId: () => "req_test",
  });

  const data = await client.call<{ value: number }>("echo", { value: 7 });
  assert.deepEqual(data, { value: 7 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v2/echo");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(bodyOf(calls[0]), { value: 7 });
  assert.equal(headersOf(calls[0])["X-Request-ID"], "req_test");
  assert.equal(headersOf(calls[0])["Content-Type"], "application/json");
});

test("call supports base paths, query objects, and idempotency keys", async () => {
  const { fetch, calls } = fakeFetch(async () =>
    json({ ok: true, data: null }),
  );
  const client = new V2Client({ basePath: "/api/test/", fetch });

  await client.call(
    "notes/list",
    {},
    {
      query: { page: 2, tag: ["a", "b"], skip: undefined },
      idempotencyKey: "idem-1",
      headers: { "X-Extra": "yes" },
    },
  );

  assert.equal(calls[0].url, "/api/test/notes/list?page=2&tag=a&tag=b");
  assert.equal(headersOf(calls[0])["Idempotency-Key"], "idem-1");
  assert.equal(headersOf(calls[0])["X-Extra"], "yes");
});

test("call wraps HTTP and envelope errors in ApiClientError", async () => {
  const { fetch, calls } = fakeFetch(async () =>
    json(
      {
        ok: false,
        error: { code: "bad_request", message: "Nope" },
        request_id: "server-2",
      },
      400,
    ),
  );
  const client = new V2Client({ fetch });

  await assert.rejects(client.call("broken", {}), (error: unknown) => {
    assert.ok(error instanceof ApiClientError);
    assert.equal(error.status, 400);
    assert.equal(error.code, "bad_request");
    assert.equal(error.requestId, "server-2");
    assert.equal(error.retryable, false);
    return true;
  });
  assert.equal(calls.length, 1);
});

test("a 200 envelope with ok=false is still an error", async () => {
  const { fetch } = fakeFetch(async () =>
    json({ ok: false, error: "Rejected", request_id: "server-3" }),
  );
  const client = new V2Client({ fetch });

  await assert.rejects(
    client.call("reject", {}),
    (error: unknown) =>
      error instanceof ApiClientError &&
      error.status === 200 &&
      error.code === "http_200" &&
      error.message === "Rejected",
  );
});

test("generated request ids are unique and caller overrides are honored", async () => {
  const { fetch, calls } = fakeFetch(async () =>
    json({ ok: true, data: "ok" }),
  );
  const client = new V2Client({ fetch });

  await client.call("first", {});
  await client.call("second", {});
  await client.call("third", {}, { requestId: "req_custom" });

  const first = headersOf(calls[0])["X-Request-ID"];
  const second = headersOf(calls[1])["X-Request-ID"];
  assert.match(first, /^req_/);
  assert.match(second, /^req_/);
  assert.notEqual(first, second);
  assert.equal(headersOf(calls[2])["X-Request-ID"], "req_custom");
});

test("timeouts abort the request and report a timeout error", async () => {
  const { fetch } = fakeFetch(
    (_url, init) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init.signal;
        if (signal?.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      }),
  );
  const client = new V2Client({ fetch, timeout: 15 });

  await assert.rejects(
    client.call("slow", {}),
    (error: unknown) =>
      error instanceof ApiClientError &&
      error.status === 0 &&
      error.code === "timeout" &&
      /timed out/.test(error.message),
  );
});

test("an externally aborted signal is not retried even for reads", async () => {
  const controller = new AbortController();
  controller.abort();
  const { fetch, calls } = fakeFetch(async (_url, init) => {
    if (init.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    return json({ ok: true, data: "unexpected" });
  });
  const client = new V2Client({ fetch });

  await assert.rejects(
    client.call("status", {}, { method: "GET", signal: controller.signal }),
    (error: unknown) =>
      error instanceof ApiClientError &&
      error.code === "aborted" &&
      error.retryable === false,
  );
  assert.equal(calls.length, 1);
});

test("GET-like reads retry once on network failures", async () => {
  let attempts = 0;
  const { fetch, calls } = fakeFetch(async () => {
    attempts += 1;
    if (attempts === 1) throw new TypeError("connection reset");
    return json({ ok: true, data: "recovered" });
  });
  const client = new V2Client({ fetch });

  const result = await client.call<string>("status", {}, { method: "GET" });
  assert.equal(result, "recovered");
  assert.equal(calls.length, 2);
  assert.equal(
    headersOf(calls[0])["X-Request-ID"],
    headersOf(calls[1])["X-Request-ID"],
  );
});

test("writes do not retry unless explicitly requested", async () => {
  let attempts = 0;
  const { fetch, calls } = fakeFetch(async () => {
    attempts += 1;
    if (attempts === 1) throw new TypeError("connection reset");
    return json({ ok: true, data: "unexpected" });
  });
  const client = new V2Client({ fetch });

  await assert.rejects(client.call("write", {}));
  assert.equal(calls.length, 1);

  attempts = 0;
  const retry = fakeFetch(async () => {
    attempts += 1;
    if (attempts === 1) {
      return json({ ok: false, error: "transient" }, 503);
    }
    return json({ ok: true, data: "retried" });
  });
  const retryingClient = new V2Client({ fetch: retry.fetch });
  const result = await retryingClient.call<string>(
    "write",
    {},
    { retry: true },
  );
  assert.equal(result, "retried");
  assert.equal(retry.calls.length, 2);
});

test("paginate follows cursors and forwards limits", async () => {
  const pages = [
    {
      ok: true,
      data: {
        items: [{ id: 1 }, { id: 2 }],
        meta: { next_cursor: "cursor-2", has_more: true },
      },
    },
    {
      ok: true,
      data: {
        items: [{ id: 3 }],
        meta: { next_cursor: null, has_more: false },
      },
    },
  ];
  let index = 0;
  const { fetch, calls } = fakeFetch(async () => {
    const page = pages[index];
    index += 1;
    return json(page);
  });
  const client = new V2Client({ fetch });

  const collected: Array<{ id: number }> = [];
  for await (const item of client.paginate<{ id: number }>(
    "list_items",
    { filter: "all" },
    { limit: 2, maxPages: 10 },
  )) {
    collected.push(item);
  }

  assert.deepEqual(
    collected.map((item) => item.id),
    [1, 2, 3],
  );
  assert.equal(calls.length, 2);
  assert.deepEqual(bodyOf(calls[0]), { filter: "all", limit: 2 });
  assert.deepEqual(bodyOf(calls[1]), {
    filter: "all",
    limit: 2,
    cursor: "cursor-2",
  });
});

test("paginate reads envelope-level cursors from json-only fakes", async () => {
  let index = 0;
  const fetch = (async () => {
    index += 1;
    const body =
      index === 1
        ? {
            ok: true,
            data: [{ id: 1 }],
            meta: { next_cursor: "next-page" },
          }
        : {
            ok: true,
            data: [{ id: 2 }],
            meta: { has_more: false },
          };
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => body,
    } as unknown as Response;
  }) as typeof globalThis.fetch;
  const client = new V2Client({ fetch });

  const ids: number[] = [];
  for await (const item of client.paginate<{ id: number }>("list_items", {})) {
    ids.push(item.id);
  }

  assert.deepEqual(ids, [1, 2]);
  assert.equal(index, 2);
});

test("paginate stops at the safety cap", async () => {
  let page = 0;
  const { fetch, calls } = fakeFetch(async () => {
    page += 1;
    return json({
      ok: true,
      data: {
        items: [{ id: page }],
        meta: { next_cursor: `cursor-${page}`, has_more: true },
      },
    });
  });
  const client = new V2Client({ fetch });

  const ids: number[] = [];
  for await (const item of client.paginate<{ id: number }>(
    "list_items",
    {},
    { maxPages: 3 },
  )) {
    ids.push(item.id);
  }

  assert.deepEqual(ids, [1, 2, 3]);
  assert.equal(calls.length, 3);
});

test("withQuery, isAbortError, and requestId helpers behave safely", () => {
  assert.equal(
    withQuery("/x", {
      a: 1,
      b: undefined,
      c: null,
      d: "",
      e: [1, 2],
    }),
    "/x?a=1&d=&e=1&e=2",
  );
  assert.equal(withQuery("/x?z=1", { a: "b" }), "/x?z=1&a=b");
  assert.equal(withQuery("/x"), "/x");

  assert.equal(isAbortError(new DOMException("Aborted", "AbortError")), true);
  assert.equal(isAbortError({ name: "AbortError" }), true);
  assert.equal(isAbortError(new Error("nope")), false);
  assert.equal(isAbortError(null), false);

  assert.match(requestId(), /^req_/);
  assert.match(requestId("trace"), /^trace_/);
});
