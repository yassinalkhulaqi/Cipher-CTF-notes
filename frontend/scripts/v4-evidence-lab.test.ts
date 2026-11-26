import assert from "node:assert/strict";
import test from "node:test";

import { V4ApiError, V4Client } from "../src/features/v4-kernel/client";
import {
  EvidenceLabClientV4,
  bytesToHex,
  hexToBytes,
} from "../src/features/evidence-lab/v4/client";
import {
  badgeLabel,
  canInspect,
  custodyTimeline,
  evidenceLabReducer,
  formatBytes,
  formatOffset,
  formatTimestamp,
  hashBadge,
  hexRows,
  initialEvidenceLabState,
  shortHash,
  statusText,
  totalSize,
  visibleRecords,
  visibleStrings,
} from "../src/features/evidence-lab/v4/state";
import type {
  CustodyEntryV4,
  EvidenceRecordV4,
  InspectionResultV4,
} from "../src/features/evidence-lab/v4/types";

function record(id: string, name: string): EvidenceRecordV4 {
  return {
    id,
    name,
    size: 64,
    sha256: "a".repeat(64),
    acquired_at: "2024-05-01T12:00:00.000Z",
    tags: ["disk", "triage"],
  };
}

function inspection(matches = true): InspectionResultV4 {
  return {
    evidence_id: "ev-1",
    hex_rows: [
      {
        offset: 0,
        cells: [
          { offset: 0, hex: "41", ascii: "A" },
          { offset: 1, hex: "00", ascii: "." },
        ],
        ascii: "A.",
      },
    ],
    strings: [
      { offset: 0, value: "HELLO", encoding: "ascii" },
      { offset: 8, value: "xy", encoding: "ascii" },
      { offset: 16, value: "wide", encoding: "utf-16le" },
    ],
    verifications: [
      {
        algorithm: "sha256",
        expected: "a".repeat(64),
        actual: matches ? "a".repeat(64) : "b".repeat(64),
        matches,
      },
    ],
    custody: [],
    generated_at: "2024-05-01T12:00:00.000Z",
    notes: ["declared size differs"],
    summary: {
      rows: 1,
      cells: 2,
      strings: 3,
      verifications: 1,
      custody_entries: 0,
      all_verified: matches,
    },
  };
}

function custodyEntries(): CustodyEntryV4[] {
  return [
    {
      actor: "zoe",
      action: "transferred",
      timestamp: "2024-05-01T14:00:00.000Z",
      from_hash: "a".repeat(64),
      to_hash: "b".repeat(64),
    },
    {
      actor: "alice",
      action: "acquired",
      timestamp: "2024-05-01T12:00:00.000Z",
      from_hash: "0".repeat(64),
      to_hash: "a".repeat(64),
    },
  ];
}

test("initial state is deterministic and empty", () => {
  const state = initialEvidenceLabState();
  assert.equal(state.records.length, 0);
  assert.equal(state.selectedId, "");
  assert.equal(state.panel, "hex");
  assert.equal(state.showAscii, true);
  assert.equal(state.minStringLength, 4);
  assert.equal(state.error, null);
  assert.equal(hashBadge(state), "pending");
  assert.equal(canInspect(state), false);
  assert.equal(statusText(state), "0 of 0 items");
});

test("reducer loads records and selects the first one", () => {
  let state = initialEvidenceLabState();
  state = evidenceLabReducer(state, { type: "load-start" });
  assert.equal(state.loading, true);
  assert.equal(state.loadCount, 1);
  state = evidenceLabReducer(state, {
    type: "records-loaded",
    records: [record("ev-1", "disk.img"), record("ev-2", "trace.pcap")],
    etag: "W/abc",
    total: 2,
  });
  assert.equal(state.selectedId, "ev-1");
  assert.equal(state.loading, false);
  assert.equal(state.etag, "W/abc");
  assert.equal(totalSize(state), 128);
  state = evidenceLabReducer(state, { type: "query", value: "pcap" });
  assert.deepEqual(
    visibleRecords(state).map((item) => item.id),
    ["ev-2"],
  );
  state = evidenceLabReducer(state, { type: "select", id: "ev-2" });
  assert.equal(state.inspection, null);
  assert.equal(state.panel, "hex");
});

test("reducer stores inspection and custody data", () => {
  let state = initialEvidenceLabState();
  state = evidenceLabReducer(state, {
    type: "records-loaded",
    records: [record("ev-1", "disk.img")],
    etag: "",
    total: 1,
  });
  state = evidenceLabReducer(state, {
    type: "inspection-loaded",
    result: inspection(),
  });
  state = evidenceLabReducer(state, {
    type: "custody-loaded",
    entries: custodyEntries(),
    valid: true,
  });
  assert.equal(hashBadge(state), "verified");
  assert.equal(badgeLabel(hashBadge(state)), "Hashes verified");
  assert.equal(hexRows(state).length, 1);
  assert.equal(visibleStrings(state).length, 2);
  assert.equal(state.chainValid, true);
  assert.deepEqual(
    custodyTimeline(state).map((entry) => entry.actor),
    ["alice", "zoe"],
  );
  assert.equal(canInspect(state), true);
});

test("hash badge reports mismatches and pending results", () => {
  let state = evidenceLabReducer(initialEvidenceLabState(), {
    type: "inspection-loaded",
    result: inspection(false),
  });
  assert.equal(hashBadge(state), "mismatch");
  assert.equal(badgeLabel(hashBadge(state)), "Hash mismatch");
  state = evidenceLabReducer(state, { type: "min-length", value: 100 });
  assert.equal(state.minStringLength, 64);
  state = evidenceLabReducer(state, { type: "min-length", value: 0 });
  assert.equal(state.minStringLength, 1);
  assert.equal(visibleStrings(state).length, 3);
});

test("reducer panel, ascii, error, and reset actions", () => {
  let state = initialEvidenceLabState();
  state = evidenceLabReducer(state, { type: "panel", value: "custody" });
  assert.equal(state.panel, "custody");
  state = evidenceLabReducer(state, { type: "toggle-ascii" });
  assert.equal(state.showAscii, false);
  state = evidenceLabReducer(state, { type: "error", message: "boom" });
  assert.equal(statusText(state), "boom");
  assert.equal(state.loading, false);
  state = evidenceLabReducer(state, { type: "clear-error" });
  assert.equal(state.error, null);
  state = evidenceLabReducer(state, { type: "reset" });
  assert.equal(state.panel, "hex");
  assert.equal(state.showAscii, true);
});

test("display helpers format values", () => {
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KiB");
  assert.equal(formatBytes(1024 * 1024 * 3), "3.0 MiB");
  assert.equal(formatOffset(255), "000000ff");
  assert.equal(shortHash("abcdef1234567890"), "abcdef123456");
  assert.equal(
    formatTimestamp("2024-05-01T12:00:00.000Z"),
    "2024-05-01 12:00:00Z",
  );
});

test("hex conversion helpers round-trip and reject bad input", () => {
  assert.equal(bytesToHex(new Uint8Array([0, 15, 255])), "000fff");
  assert.deepEqual(Array.from(hexToBytes("00 0f ff")), [0, 15, 255]);
  assert.throws(() => hexToBytes("abc"), /even number/);
  assert.throws(() => hexToBytes("zz"), /non-hexadecimal/);
});

test("client decodes list envelopes and forwards pagination", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (url: string) => {
    calls.push(url);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: {
          items: [record("ev-1", "disk.img")],
          total: 1,
          page: 1,
          page_size: 50,
          next_cursor: "",
          etag: "W/x",
          not_modified: false,
        },
        meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
      }),
    } as Response;
  }) as typeof fetch;
  const client = new EvidenceLabClientV4(new V4Client("/api/v4", fetchImpl));
  const { data, meta } = await client.list({ page: 2, pageSize: 10 });
  assert.equal(data.items.length, 1);
  assert.equal(data.etag, "W/x");
  assert.equal(meta.version, "v4");
  assert.ok(calls[0].includes("page=2"));
  assert.ok(calls[0].includes("page_size=10"));
});

test("client posts create payload and reads nested routes", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: { id: "x" },
        meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
      }),
    } as Response;
  }) as typeof fetch;
  const client = new EvidenceLabClientV4(new V4Client("/api/v4", fetchImpl));
  await client.create({ name: "x", size: 1, sha256: "a".repeat(64) });
  await client.get("ev 1");
  await client.inspect("ev 1");
  await client.custody("ev-1");
  await client.manifest();
  assert.equal(calls[0].init?.method, "POST");
  assert.equal(JSON.parse(String(calls[0].init?.body)).name, "x");
  assert.ok(calls[1].url.includes("ev%201"));
  assert.ok(calls[2].url.endsWith("/inspect"));
  assert.ok(calls[3].url.endsWith("/custody"));
  assert.ok(calls[4].url.endsWith("/evidence-manifest"));
});

test("client surfaces structured api errors", async () => {
  const fetchImpl = (async () => ({
    ok: false,
    status: 403,
    json: async () => ({
      error: { code: "forbidden", message: "denied", details: ["capability"] },
    }),
  })) as typeof fetch;
  const client = new EvidenceLabClientV4(new V4Client("/api/v4", fetchImpl));
  await assert.rejects(
    () => client.list(),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "forbidden",
  );
});
