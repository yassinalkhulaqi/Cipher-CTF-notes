import assert from "node:assert/strict";
import test from "node:test";

import { V4ApiError, V4Client } from "../src/features/v4-kernel/client";
import {
  CAPTURE_SOURCES,
  InboxClient,
  TRIAGE_STATES,
  inboxClient,
} from "../src/features/capture-inbox/client";
import type {
  CaptureItemV4,
  CaptureMutationData,
  InboxListData,
} from "../src/features/capture-inbox/client";
import {
  capturePreview,
  initialInboxState,
  isLegalTransition,
  legalTargets,
  normalizeTag,
  reduceInbox,
  selectedItem,
  sourceCounts,
  stateCounts,
  visibleItems,
} from "../src/features/capture-inbox/state";

function makeItem(overrides: Partial<CaptureItemV4> = {}): CaptureItemV4 {
  return {
    id: "11111111-2222-3333-4444-555555555555",
    raw: "flag{alpha}",
    source: "flag",
    state: "untriaged",
    tags: ["ctf"],
    confidence: 0.94,
    created_at: "2026-01-02T03:04:05.000Z",
    content_hash: "a".repeat(64),
    ...overrides,
  };
}

test("initial inbox state has deterministic defaults", () => {
  const state = initialInboxState();
  assert.equal(state.draft, "");
  assert.equal(state.source, "manual");
  assert.equal(state.filter, "all");
  assert.equal(state.sourceFilter, "all");
  assert.equal(state.items.length, 0);
  assert.equal(state.total, 0);
  assert.equal(state.loading, false);
  assert.equal(inboxClient instanceof InboxClient, true);
});

test("composer actions update draft, source, and tags", () => {
  let state = initialInboxState();
  state = reduceInbox(state, { type: "draft", value: "hello" });
  assert.equal(state.draft, "hello");
  state = reduceInbox(state, { type: "source", value: "clipboard" });
  assert.equal(state.source, "clipboard");
  state = reduceInbox(state, { type: "toggle-tag", value: " CTF " });
  assert.deepEqual(state.tags, ["ctf"]);
  state = reduceInbox(state, { type: "toggle-tag", value: "#todo" });
  assert.deepEqual(state.tags, ["ctf", "todo"]);
  state = reduceInbox(state, { type: "toggle-tag", value: "ctf" });
  assert.deepEqual(state.tags, ["todo"]);
  state = reduceInbox(state, { type: "reset-composer" });
  assert.equal(state.draft, "");
  assert.deepEqual(state.tags, []);
});

test("source and state arrays are stable and complete", () => {
  assert.deepEqual(
    [...CAPTURE_SOURCES],
    ["manual", "link", "snippet", "flag", "clipboard"],
  );
  assert.deepEqual(
    [...TRIAGE_STATES],
    ["untriaged", "accepted", "rejected", "archived"],
  );
});

test("loaded, captured, and triaged actions maintain the item list", () => {
  let state = initialInboxState();
  state = reduceInbox(state, { type: "loading" });
  assert.equal(state.loading, true);
  state = reduceInbox(state, {
    type: "loaded",
    items: [makeItem()],
    total: 1,
    page: 2,
    nextCursor: "cursor-1",
    requestId: "req-1",
  });
  assert.equal(state.loading, false);
  assert.equal(state.page, 2);
  assert.equal(state.nextCursor, "cursor-1");
  assert.equal(state.requestId, "req-1");
  state = reduceInbox(state, { type: "submitting" });
  assert.equal(state.submitting, true);
  state = reduceInbox(state, {
    type: "captured",
    item: makeItem({ id: "second" }),
    created: true,
    duplicate: false,
  });
  assert.equal(state.items.length, 2);
  assert.equal(state.total, 2);
  assert.equal(state.notice, "Capture saved");
  state = reduceInbox(state, {
    type: "captured",
    item: makeItem({ id: "second" }),
    created: false,
    duplicate: true,
  });
  assert.equal(state.items.length, 2);
  assert.equal(state.total, 2);
  assert.equal(state.notice, "Duplicate already in inbox");
  state = reduceInbox(state, {
    type: "triaged",
    item: makeItem({ id: "second", state: "accepted" }),
  });
  assert.equal(state.items[0].state, "accepted");
  assert.equal(state.notice, "Marked accepted");
});

test("filters, query, and selection navigation", () => {
  let state = initialInboxState({
    items: [
      makeItem({ id: "a", state: "untriaged" }),
      makeItem({
        id: "b",
        state: "accepted",
        source: "link",
        raw: "https://example.test",
      }),
      makeItem({ id: "c", state: "rejected", tags: ["web"] }),
    ],
  });
  assert.equal(visibleItems(state).length, 3);
  state = reduceInbox(state, { type: "filter", value: "accepted" });
  assert.deepEqual(
    visibleItems(state).map((item) => item.id),
    ["b"],
  );
  state = reduceInbox(state, { type: "filter", value: "all" });
  state = reduceInbox(state, { type: "source-filter", value: "link" });
  assert.deepEqual(
    visibleItems(state).map((item) => item.id),
    ["b"],
  );
  state = reduceInbox(state, { type: "source-filter", value: "all" });
  state = reduceInbox(state, { type: "query", value: "WEB" });
  assert.deepEqual(
    visibleItems(state).map((item) => item.id),
    ["c"],
  );
  state = reduceInbox(state, { type: "query", value: "" });
  state = reduceInbox(state, { type: "move", delta: 1 });
  assert.equal(selectedItem(state)?.id, "a");
  state = reduceInbox(state, { type: "move", delta: 1 });
  assert.equal(selectedItem(state)?.id, "b");
  state = reduceInbox(state, { type: "move", delta: -1 });
  assert.equal(selectedItem(state)?.id, "a");
  state = reduceInbox(state, { type: "select", id: "c" });
  assert.equal(selectedItem(state)?.id, "c");
});

test("counts and transition helpers", () => {
  const state = initialInboxState({
    items: [
      makeItem({ id: "a", state: "untriaged", source: "flag" }),
      makeItem({ id: "b", state: "accepted", source: "link" }),
    ],
  });
  assert.deepEqual(stateCounts(state), {
    all: 2,
    untriaged: 1,
    accepted: 1,
    rejected: 0,
    archived: 0,
  });
  assert.deepEqual(sourceCounts(state), {
    all: 2,
    manual: 0,
    link: 1,
    snippet: 0,
    flag: 1,
    clipboard: 0,
  });
  assert.equal(isLegalTransition("accepted", "rejected"), false);
  assert.equal(isLegalTransition("accepted", "archived"), true);
  assert.deepEqual([...legalTargets("rejected")], ["archived"]);
  assert.equal(normalizeTag("## Deep Work"), "deep-work");
  assert.equal(capturePreview("a\nb  c", 4), "a b…");
});

test("failed and reset actions restore state", () => {
  const original = initialInboxState();
  let state = reduceInbox(original, { type: "failed", message: "boom" });
  assert.equal(state.error, "boom");
  state = reduceInbox(state, { type: "notice", message: "ok" });
  assert.equal(state.error, "");
  assert.equal(state.notice, "ok");
  state = reduceInbox(state, { type: "reset", state: original });
  assert.deepEqual(state, original);
});

function fakeFetch(payload: unknown, status = 200): typeof fetch {
  return (async () =>
    ({
      ok: status < 400,
      status,
      json: async () => payload,
    }) as Response) as typeof fetch;
}

function listPayload(): InboxListData {
  return {
    items: [makeItem()],
    total: 1,
    page: 1,
    page_size: 50,
    next_cursor: "",
    etag: 'W/"etag"',
    filters: { state: "untriaged", source: "", tag: "", query: "" },
  };
}

test("client encodes filters and decodes a list envelope", async () => {
  let requested = "";
  const client = new InboxClient(
    new V4Client("/api/v4", (async (url: string) => {
      requested = String(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: listPayload(),
          meta: {
            request_id: "r1",
            version: "v4",
            page: 1,
            page_size: 50,
            etag: 'W/"etag"',
          },
        }),
      } as Response;
    }) as typeof fetch),
  );
  const page = await client.list({
    state: "untriaged",
    source: "flag",
    page: 1,
  });
  assert.equal(page.data.items[0].id, makeItem().id);
  assert.equal(page.meta.request_id, "r1");
  assert.match(requested, /state=untriaged/);
  assert.match(requested, /source=flag/);
  assert.match(requested, /page=1/);
});

test("client validates local input before issuing requests", async () => {
  let calls = 0;
  const client = new InboxClient(
    new V4Client("/api/v4", (async () => {
      calls += 1;
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    }) as typeof fetch),
  );
  await assert.rejects(
    () => client.capture("  "),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "invalid_input",
  );
  await assert.rejects(
    () => client.triage("", "accepted"),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "invalid_input",
  );
  assert.equal(calls, 0);
});

test("client decodes capture and triage mutations", async () => {
  const mutation: CaptureMutationData = {
    capture: makeItem({ state: "accepted" }),
    created: true,
    duplicate: false,
    from_state: "untriaged",
    to_state: "accepted",
  };
  const client = new InboxClient(
    new V4Client("/api/v4", fakeFetch({ data: mutation, meta: {} })),
  );
  const capture = await client.capture("flag{alpha}", "flag", ["ctf"]);
  assert.equal(capture.capture.state, "accepted");
  const triaged = await client.triage("id-1", "accepted");
  assert.equal(triaged.to_state, "accepted");
  const byAction = await client.triageByAction("id-1", "archive");
  assert.equal(byAction.capture.id, makeItem().id);
});

test("client surfaces structured API errors", async () => {
  const client = new InboxClient(
    new V4Client(
      "/api/v4",
      fakeFetch(
        {
          error: {
            code: "conflict",
            message: "illegal transition",
            details: ["archived"],
          },
        },
        409,
      ),
    ),
  );
  await assert.rejects(
    () => client.triage("id-1", "rejected"),
    (error: unknown) =>
      error instanceof V4ApiError &&
      error.code === "conflict" &&
      error.details[0] === "archived",
  );
});
