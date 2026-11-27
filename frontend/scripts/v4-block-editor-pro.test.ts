import assert from "node:assert/strict";
import test from "node:test";

import {
  BlockEditorClient,
  V4ApiError,
} from "../src/features/block-editor-pro/client";
import {
  BLOCK_LABELS,
  INLINE_MARKS,
  SLASH_BLOCK_KINDS,
  applyInlineMark,
  blockLabel,
  checksum,
  countWords,
  createBlock,
  createInitialState,
  diffDeltas,
  editorReducer,
  emptyDocument,
  findMatches,
} from "../src/features/block-editor-pro/state";
import type { ProDocument } from "../src/features/block-editor-pro/state";
import { V4Client } from "../src/features/v4-kernel/client";

function sample(): ProDocument {
  return {
    id: "doc1",
    title: "Editor notes",
    blocks: [
      createBlock("a", "paragraph", "alpha bravo"),
      createBlock("b", "heading", "Section"),
      createBlock("c", "code", "print(1)"),
    ],
  };
}

function okEnvelope<T>(data: T) {
  return {
    data,
    meta: {
      request_id: "req-1",
      version: "v4",
      page: 1,
      page_size: 25,
    },
  };
}

interface FakeResponse {
  status: number;
  body: unknown;
}

function fakeFetch(responses: FakeResponse[]) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  let index = 0;
  const impl = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    calls.push({ url: String(input), init });
    const response = responses[Math.min(index, responses.length - 1)];
    index += 1;
    return {
      status: response.status,
      json: async () => response.body,
    } as Response;
  };
  return { impl, calls };
}

test("block catalogs expose every editor affordance", () => {
  assert.equal(SLASH_BLOCK_KINDS.length, 7);
  assert.equal(INLINE_MARKS.length, 4);
  assert.equal(BLOCK_LABELS.table, "Table");
  assert.equal(blockLabel(createBlock("h", "heading")), "H2");
  assert.equal(blockLabel(createBlock("l", "list")), "list · bullet");
  assert.equal(blockLabel(createBlock("t", "table")), "Table");
  assert.equal(createBlock("c", "code").language, "text");
  assert.deepEqual(emptyDocument("fresh").blocks, []);
});

test("initial state is clean and deterministic", () => {
  const state = createInitialState(sample(), 4);
  assert.equal(state.document.id, "doc1");
  assert.equal(state.selectedId, "a");
  assert.equal(state.revision, 4);
  assert.equal(state.dirty, false);
  assert.equal(state.status, "idle");
  assert.deepEqual(state.deltas, []);
});

test("reducer selects, updates, and titles documents", () => {
  let state = createInitialState(sample());
  state = editorReducer(state, { type: "select", id: "b" });
  assert.equal(state.selectedId, "b");
  state = editorReducer(state, {
    type: "update-block",
    id: "b",
    patch: { text: "Changed heading" },
  });
  assert.equal(state.document.blocks[1].text, "Changed heading");
  assert.equal(state.dirty, true);
  state = editorReducer(state, { type: "set-title", title: "Renamed" });
  assert.equal(state.document.title, "Renamed");
  state = editorReducer(state, {
    type: "load",
    document: sample(),
    revision: 9,
  });
  assert.equal(state.revision, 9);
  assert.equal(state.dirty, false);
});

test("reducer inserts, deletes, and moves blocks", () => {
  let state = createInitialState(sample());
  state = editorReducer(state, {
    type: "insert",
    block: createBlock("x", "quote", "new"),
    index: 1,
  });
  assert.equal(state.document.blocks[1].id, "x");
  state = editorReducer(state, { type: "move", id: "x", target: 0 });
  assert.equal(state.document.blocks[0].id, "x");
  state = editorReducer(state, { type: "delete", id: "x" });
  assert.equal(state.document.blocks.length, 3);
  state = editorReducer(state, { type: "move", id: "absent", target: 0 });
  assert.equal(state.document.blocks.length, 3);
});

test("reducer find and replace across title, text, and items", () => {
  const document = sample();
  document.blocks[0].items = ["alpha item", "other"];
  let state = createInitialState(document);
  state = editorReducer(state, { type: "set-find", open: true });
  state = editorReducer(state, { type: "find", value: "alpha" });
  state = editorReducer(state, { type: "replace", value: "omega" });
  assert.equal(state.findOpen, true);
  assert.equal(state.find, "alpha");
  state = editorReducer(state, { type: "replace-all" });
  assert.equal(state.document.blocks[0].text, "omega bravo");
  assert.equal(state.document.blocks[0].items[0], "omega item");
  const unchanged = editorReducer(state, { type: "replace-all" });
  assert.deepEqual(unchanged.document.blocks, state.document.blocks);
});

test("reducer tracks ui toggles and save lifecycle", () => {
  let state = createInitialState(sample());
  state = editorReducer(state, { type: "toggle-focus" });
  assert.equal(state.focusMode, true);
  assert.equal(state.findOpen, false);
  state = editorReducer(state, { type: "set-diff", open: true });
  assert.equal(state.diffOpen, true);
  state = editorReducer(state, { type: "saving" });
  assert.equal(state.status, "saving");
  state = editorReducer(state, { type: "saved", revision: 7 });
  assert.equal(state.status, "saved");
  assert.equal(state.revision, 7);
  assert.equal(state.dirty, false);
  state = editorReducer(state, { type: "error", message: "offline" });
  assert.equal(state.error, "offline");
  state = editorReducer(state, { type: "mark-dirty" });
  assert.equal(state.dirty, true);
});

test("reducer records snapshots and deltas", () => {
  let state = createInitialState(sample());
  const snapshot = {
    id: "s1",
    revision: 2,
    reason: "manual",
    checksum: "abc",
    created_at: "2026-01-01T00:00:00Z",
  };
  state = editorReducer(state, { type: "snapshots", snapshots: [snapshot] });
  assert.deepEqual(state.snapshots, [snapshot]);
  const delta = {
    id: "a",
    kind: "replace" as const,
    text: "alpha",
    leftIndex: 0,
    rightIndex: 0,
  };
  state = editorReducer(state, { type: "diff", deltas: [delta] });
  assert.deepEqual(state.deltas, [delta]);
});

test("selectors find matches, count words, and checksum content", () => {
  const document = sample();
  assert.deepEqual(findMatches(document, "BRAVO"), ["a"]);
  assert.deepEqual(findMatches(document, ""), []);
  assert.deepEqual(findMatches(document, "missing"), []);
  assert.equal(countWords(document), 6);
  assert.equal(checksum(document), checksum(sample()));
  assert.notEqual(
    checksum(document),
    checksum({ ...document, title: "Other" }),
  );
});

test("diff deltas classify adds, removes, replaces, and moves", () => {
  const before = sample();
  const after = sample();
  after.blocks.splice(1, 1);
  after.blocks[0] = { ...after.blocks[0], text: "alpha changed" };
  after.blocks.push(createBlock("new", "quote", "added"));
  const deltas = diffDeltas(before, after);
  assert.equal(deltas.find((item) => item.id === "b")?.kind, "remove");
  assert.equal(deltas.find((item) => item.id === "a")?.kind, "replace");
  assert.equal(deltas.find((item) => item.id === "new")?.kind, "add");
  assert.deepEqual(diffDeltas(before, sample()), []);
});

test("inline marks wrap the selection without mutating blocks", () => {
  const block = createBlock("a", "paragraph", "hello world");
  assert.equal(applyInlineMark(block, "bold", "world").text, "hello **world**");
  assert.equal(applyInlineMark(block, "italic", "hello").text, "*hello* world");
  assert.equal(applyInlineMark(block, "code", "world").text, "hello `world`");
  assert.equal(
    applyInlineMark(block, "link", "world", "https://x.test").text,
    "hello [world](https://x.test)",
  );
  assert.deepEqual(applyInlineMark(block, "link", "world"), block);
  assert.deepEqual(applyInlineMark(block, "bold", "absent"), block);
});

test("client gets a document with an etag precondition", async () => {
  const { impl, calls } = fakeFetch([
    {
      status: 200,
      body: okEnvelope({
        document: sample(),
        checksum: "abc",
        word_count: 8,
        revision: 1,
        not_modified: false,
      }),
    },
  ]);
  const client = new BlockEditorClient({
    client: new V4Client("/api/v4", impl),
  });
  const result = await client.getDocument("doc1", 'W/"abc"');
  assert.equal(result.data.document.title, "Editor notes");
  assert.equal(result.meta.version, "v4");
  assert.equal(calls[0].url, "/api/v4/blocks?id=doc1");
  assert.equal(calls[0].init?.method, "GET");
  const headers = calls[0].init?.headers as Record<string, string>;
  assert.equal(headers["If-None-Match"], 'W/"abc"');
});

test("client lists, puts, and patches documents", async () => {
  const { impl, calls } = fakeFetch([
    { status: 200, body: okEnvelope({ items: [sample()], total: 1 }) },
    {
      status: 200,
      body: okEnvelope({
        document: sample(),
        revision: 3,
        checksum: "abc",
        created: false,
      }),
    },
    {
      status: 200,
      body: okEnvelope({
        document: sample(),
        revision: 4,
        checksum: "def",
        applied: [],
        summary: {},
      }),
    },
  ]);
  const client = new BlockEditorClient({
    client: new V4Client("/api/v4", impl),
  });
  const listed = await client.listDocuments(2, 10, "alpha");
  assert.equal(listed.total, 1);
  assert.equal(listed.meta.request_id, "req-1");
  assert.equal(calls[0].url, "/api/v4/blocks?page=2&page_size=10&query=alpha");
  const put = await client.putDocument(sample(), "abc");
  assert.equal(put.revision, 3);
  assert.equal(calls[1].init?.method, "PUT");
  assert.deepEqual(JSON.parse(String(calls[1].init?.body)), {
    document: sample(),
    expected_checksum: "abc",
  });
  const patched = await client.patchDocument("doc1", [], "def");
  assert.equal(patched.revision, 4);
  assert.equal(calls[2].init?.method, "PATCH");
});

test("client reads history and manages snapshots", async () => {
  const { impl, calls } = fakeFetch([
    {
      status: 200,
      body: okEnvelope({
        items: [],
        total: 0,
        page: 1,
        page_size: 25,
        next_cursor: "",
        etag: 'W/"a"',
      }),
    },
    {
      status: 200,
      body: okEnvelope({ snapshots: [], count: 0, document_id: "doc1" }),
    },
    {
      status: 200,
      body: okEnvelope({
        snapshots: [{ id: "s1" }],
        count: 1,
        document_id: "doc1",
      }),
    },
    {
      status: 200,
      body: okEnvelope({ document: sample(), revision: 2, checksum: "abc" }),
    },
  ]);
  const client = new BlockEditorClient({
    client: new V4Client("/api/v4", impl),
  });
  const history = await client.history("doc1", 1, 5);
  assert.equal(history.data.total, 0);
  assert.equal(
    calls[0].url,
    "/api/v4/blocks/history?id=doc1&page=1&page_size=5",
  );
  assert.equal((await client.snapshots("doc1")).count, 0);
  assert.equal((await client.createSnapshot("doc1", "manual")).count, 1);
  assert.deepEqual(JSON.parse(String(calls[2].init?.body)), {
    id: "doc1",
    action: "create",
    reason: "manual",
  });
  assert.equal((await client.restoreSnapshot("doc1", "s1")).revision, 2);
  assert.equal(calls[3].init?.method, "PATCH");
});

test("client throws structured V4ApiError on error envelopes", async () => {
  const { impl } = fakeFetch([
    {
      status: 404,
      body: {
        error: { code: "not_found", message: "no document", details: ["doc1"] },
      },
    },
  ]);
  const client = new BlockEditorClient({
    client: new V4Client("/api/v4", impl),
  });
  await assert.rejects(
    () => client.getDocument("doc1"),
    (error: unknown) => {
      assert.ok(error instanceof V4ApiError);
      assert.equal(error.code, "not_found");
      assert.deepEqual(error.details, ["doc1"]);
      return true;
    },
  );
});
