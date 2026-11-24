import assert from "node:assert/strict";
import test from "node:test";

import { EvidenceLabClient } from "../src/features/evidence-lab/client";
import {
  compareHeadline,
  compareRows,
  changedKeys,
  sizeDeltaTotal,
} from "../src/features/evidence-lab/compareModel";
import {
  custodyColumns,
  custodyHeadline,
  custodyIssues,
  flattenTimeline,
} from "../src/features/evidence-lab/custodyModel";
import {
  badgeLabel,
  badgeTone,
  bytesToBase64,
  formatBytes,
  formatOffset,
  formatSignedBytes,
  groupCells,
  hexToBytes,
  maskHash,
  parseOffset,
  textToBase64,
} from "../src/features/evidence-lab/format";
import {
  markSelection,
  navigateOffset,
  selectedByteCount,
  visibleRows,
  offsetForCell,
  describeSelection,
} from "../src/features/evidence-lab/hexModel";
import {
  createIngestItem,
  dedupeIngest,
  ingestCounts,
  ingestProgressLabel,
  validateDrop,
} from "../src/features/evidence-lab/ingestModel";
import {
  initialLabState,
  labReducer,
} from "../src/features/evidence-lab/state";
import {
  entropyBars,
  entropyTone,
  filterHits,
  stringTabs,
  topStrings,
} from "../src/features/evidence-lab/stringsModel";
import type {
  BundleDiffData,
  CustodyGraphData,
  EntropyReportData,
  EvidenceReportData,
  HexRowData,
  HexWindowData,
  StringHitData,
  StringScanData,
} from "../src/features/evidence-lab/types";

function row(offset: number, cells: string[]): HexRowData {
  return {
    offset,
    offset_hex: offset.toString(16).padStart(8, "0"),
    cells,
    ascii: cells.map(() => ".").join(""),
    selected: false,
  };
}

function hexWindow(rows: HexRowData[]): HexWindowData {
  return {
    start: rows[0]?.offset ?? 0,
    length: rows.length * 16,
    end: (rows[0]?.offset ?? 0) + rows.length * 16,
    bytes_per_row: 16,
    total_bytes: 4096,
    truncated: false,
    selection_start: null,
    selection_end: null,
    rows,
  };
}

function hits(): StringHitData[] {
  return [
    {
      offset: 4,
      end: 12,
      text: "https://x.test",
      encoding: "ascii",
      length: 15,
      printable_ratio: 1,
      kind: "url",
    },
    {
      offset: 32,
      end: 37,
      text: "hello world",
      encoding: "ascii",
      length: 11,
      printable_ratio: 1,
      kind: "plain",
    },
  ];
}

function scan(): StringScanData {
  const list = hits();
  return {
    hits: list,
    encoding: "ascii",
    min_length: 4,
    bytes_scanned: 512,
    truncated: false,
    counts: { url: 1, plain: 1 },
  };
}

function entropy(): EntropyReportData {
  return {
    sample_bytes: 256,
    total_bytes: 4096,
    entropy: 7.5,
    normalized: 0.94,
    classification: "very_high",
    truncated: true,
    histogram: new Array(256).fill(1),
    buckets: [
      { label: "empty", low: 0, high: 31, count: 32 },
      { label: "very_low", low: 32, high: 63, count: 64 },
    ],
  };
}

function report(): EvidenceReportData {
  return {
    ref: "evidence:sample.bin",
    size_bytes: 4096,
    panel: {
      sha256: "a".repeat(64),
      blake2b: "b".repeat(64),
      sha256_short: "aaaa...aaaa",
      blake2b_short: "bbbb...bbbb",
      size_bytes: 4096,
      computed_at: "2026-01-01T00:00:00Z",
      blake2b_size: 32,
      combined_id: "a:b",
    },
    badge: {
      state: "verified",
      sha256_match: true,
      blake2b_match: true,
      size_match: true,
      ok: true,
      reasons: [],
    },
    file_class: {
      matches: [],
      primary: null,
      media_type: "application/octet-stream",
      category: "unknown",
      extension_hint: "",
      header_bytes: 512,
    },
    hex_window: hexWindow([
      row(0, ["89", "50", "4e", "47"]),
      row(16, ["00", "ff", "41", "42"]),
    ]),
    strings: scan(),
    entropy: entropy(),
    thumbnail: null,
    warnings: [],
  };
}

function graph(): CustodyGraphData {
  const summary = {
    root: "evidence:disk-1",
    nodes: 2,
    edges: 1,
    depth: 1,
    actions: ["acquired"],
    actors: ["ana"],
    verified: true,
  };
  return {
    root: "evidence:disk-1",
    nodes: [
      {
        kind: "evidence",
        value: "disk-1",
        ref: "evidence:disk-1",
        label: "disk",
        action: "acquired",
        timestamp: "2026-01-01T00:00:00Z",
        depth: 0,
        terminal: false,
      },
      {
        kind: "evidence",
        value: "disk-1#1",
        ref: "evidence:disk-1#1",
        label: "acquired",
        action: "acquired",
        timestamp: "2026-01-01T00:00:00Z",
        depth: 1,
        terminal: true,
      },
    ],
    edges: [
      {
        source: "evidence:disk-1",
        target: "evidence:disk-1#1",
        kind: "derives",
        label: "",
        timestamp: "2026-01-01T00:00:00Z",
        sequence: 1,
      },
    ],
    timeline: [
      {
        date: "2026-01-01",
        events: [
          {
            date: "2026-01-01",
            sequence: 1,
            action: "acquired",
            actor: "ana",
            description: "seized",
            timestamp: "2026-01-01T00:00:00Z",
            hash: "f".repeat(64),
            previous_hash: "0".repeat(64),
            node: "evidence:disk-1#1",
          },
        ],
      },
    ],
    problems: [],
    cycle_free: true,
    verified: true,
    depth: 1,
    summary,
  };
}

function diff(): BundleDiffData {
  return {
    left_id: "before",
    right_id: "after",
    deltas: [
      {
        key: "a",
        kind: "added",
        left: null,
        right: {
          key: "a",
          sha256: "c".repeat(64),
          blake2b: "",
          size_bytes: 20,
          label: "a",
        },
        size_delta: 20,
        hash_changed: true,
      },
      {
        key: "b",
        kind: "unchanged",
        left: {
          key: "b",
          sha256: "d".repeat(64),
          blake2b: "",
          size_bytes: 8,
          label: "b",
        },
        right: {
          key: "b",
          sha256: "d".repeat(64),
          blake2b: "",
          size_bytes: 8,
          label: "b",
        },
        size_delta: 0,
        hash_changed: false,
      },
    ],
    counts: { added: 1, unchanged: 1 },
    fingerprint_left: "1".repeat(64),
    fingerprint_right: "2".repeat(64),
    identical: false,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope<T>(data: T): object {
  return { data, meta: { request_id: "req_test", api_version: "3.0" } };
}

test("format helpers are deterministic", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(1024), "1.0 KiB");
  assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MiB");
  assert.equal(formatOffset(26, 4), "001a");
  assert.equal(formatSignedBytes(-2048), "-2.0 KiB");
  assert.equal(maskHash("abcdefghijklmnopqrst", 4), "abcd...qrst");
  assert.equal(
    groupCells(["00", "01", "02", "03", "04"], 4),
    "00 01 02 03  04",
  );
  assert.equal(parseOffset("0x1f"), 31);
  assert.equal(parseOffset("ff"), 255);
  assert.equal(parseOffset("42"), 42);
  assert.equal(parseOffset("not-a-number"), null);
});

test("base64 and hex conversion round-trip", () => {
  assert.deepEqual(Array.from(hexToBytes("000102faff")), [0, 1, 2, 250, 255]);
  assert.equal(bytesToBase64(new Uint8Array([0x41])), "QQ==");
  assert.equal(bytesToBase64(new Uint8Array([0x41, 0x42])), "QkI=");
  assert.equal(bytesToBase64(new Uint8Array([0x41, 0x42, 0x43])), "QUJD");
  assert.equal(textToBase64("abc"), "YWJj");
});

test("integrity badge tone and label", () => {
  assert.equal(badgeTone(report().badge), "good");
  assert.equal(badgeLabel(report().badge), "VERIFIED");
  assert.equal(
    badgeTone({
      state: "mismatch",
      sha256_match: false,
      blake2b_match: false,
      size_match: false,
      ok: false,
      reasons: [],
    }),
    "bad",
  );
  assert.equal(badgeTone(null), "neutral");
});

test("hex viewer virtualizes rows and navigates", () => {
  const many = Array.from({ length: 500 }, (_, index) =>
    row(index * 16, ["41", "42"]),
  );
  const slice = visibleRows(many, 2000, 220, 22, 4);
  assert.ok(slice.start > 80);
  assert.ok(slice.end - slice.start < 30);
  assert.equal(slice.items[0], many[slice.start]);
  assert.equal(navigateOffset(0, -10, 4096), 0);
  assert.equal(navigateOffset(4090, 20, 4096), 4095);
  assert.equal(offsetForCell(hexWindow(many), 3, 5), 53);
});

test("hex selection marks only intersecting rows", () => {
  const window = hexWindow([row(0, ["41"]), row(16, ["42"]), row(32, ["43"])]);
  const marked = markSelection(window, { start: 17, end: 20 });
  assert.deepEqual(
    marked.rows.map((item) => item.selected),
    [false, true, false],
  );
  assert.equal(selectedByteCount(marked), 1);
  assert.equal(marked.selection_start, 17);
  assert.equal(describeSelection(marked).includes("11..14"), true);
  assert.equal(describeSelection(window), "No selection");
});

test("strings model filters and groups hits", () => {
  const scanData = scan();
  const tabs = stringTabs(scanData);
  assert.equal(tabs[0].id, "url");
  assert.equal(tabs[1].id, "plain");
  assert.equal(filterHits(scanData.hits, "hello", "all").length, 1);
  assert.equal(filterHits(scanData.hits, "", "url").length, 1);
  assert.equal(filterHits(scanData.hits, "", "hex").length, 0);
  assert.equal(topStrings(scanData.hits, 1)[0].text, "https://x.test");
  const bars = entropyBars(entropy().buckets);
  assert.equal(bars[1].ratio, 1);
  assert.equal(entropyTone(entropy()), "random");
});

test("custody model flattens timeline and lanes", () => {
  const chain = graph();
  assert.equal(flattenTimeline(chain).length, 1);
  assert.equal(custodyColumns(chain).length, 2);
  assert.equal(custodyColumns(chain)[1][0].ref, "evidence:disk-1#1");
  assert.deepEqual(custodyIssues(chain), []);
  assert.ok(custodyHeadline(chain).includes("2 nodes"));
});

test("comparison model produces rows and totals", () => {
  const bundleDiff = diff();
  assert.equal(changedKeys(bundleDiff).length, 1);
  assert.equal(compareRows(bundleDiff).length, 2);
  assert.equal(sizeDeltaTotal(bundleDiff), 20);
  assert.ok(compareHeadline(bundleDiff).includes("1 added"));
  assert.equal(compareHeadline(null), "No comparison loaded");
});

test("ingest validation and queue model", () => {
  const validation = validateDrop(
    [
      { name: "capture.png", size: 100 },
      { name: "empty.bin", size: 0 },
      { name: "huge.bin", size: 999999999999 },
      { name: "doc.unknown", size: 20 },
    ],
    1024 * 1024,
  );
  assert.equal(validation.accepted.length, 1);
  assert.equal(validation.rejected.length, 3);
  assert.match(validation.rejected[1].reason, /Exceeds/);
  const item = createIngestItem({ name: "capture.png", size: 100 } as File, 1);
  assert.equal(item.phase, "queued");
  assert.equal(ingestProgressLabel(item), "Queued");
  assert.equal(dedupeIngest([item], [item]).length, 1);
  assert.equal(ingestCounts([item]).queued, 1);
});

test("lab reducer manages navigation and selection transitions", () => {
  let state = initialLabState();
  state = labReducer(state, {
    type: "manifest",
    manifest: { signatures: 35 } as never,
  });
  assert.equal(state.manifest?.signatures, 35);
  state = labReducer(state, { type: "report", report: report() });
  assert.equal(state.report?.ref, "evidence:sample.bin");
  state = labReducer(state, { type: "anchor", offset: 0 });
  state = labReducer(state, { type: "head", offset: 15 });
  assert.equal(state.selectionAnchor, 0);
  assert.equal(state.selectionHead, 15);
  assert.equal(state.window?.selection_end, 15);
  state = labReducer(state, { type: "tab", tab: "entropy" });
  assert.equal(state.tab, "entropy");
  state = labReducer(state, {
    type: "notice",
    tone: "warn",
    message: "careful",
  });
  assert.equal(state.notices.length, 1);
  state = labReducer(state, { type: "dismiss-notice", id: 1 });
  assert.equal(state.notices.length, 0);
});

test("evidence lab client calls the v3 namespace with encoded data", async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    const url = String(input);
    const body = JSON.parse(String(init.body ?? "{}")) as Record<
      string,
      unknown
    >;
    calls.push({ url, body });
    if (url.endsWith("/manifest"))
      return json(envelope({ signatures: 35, enabled: true }));
    if (url.endsWith("/inspect")) return json(envelope(report()));
    if (url.endsWith("/hex")) return json(envelope(report().hex_window));
    if (url.endsWith("/strings")) return json(envelope(scan()));
    if (url.endsWith("/entropy")) return json(envelope(entropy()));
    if (url.endsWith("/classify")) return json(envelope(report().file_class));
    if (url.endsWith("/hashes"))
      return json(envelope({ panel: report().panel, badge: report().badge }));
    if (url.endsWith("/compare")) return json(envelope(diff()));
    if (url.endsWith("/custody")) return json(envelope(graph()));
    return json(envelope({}));
  }) as typeof globalThis.fetch;

  const client = new EvidenceLabClient({
    fetch: fetchImpl,
    requestId: () => "req_test",
  });
  const manifest = await client.manifest();
  assert.equal(manifest.signatures, 35);
  assert.equal(calls[0].url, "/api/v3/evidence/manifest");

  const bytes = new Uint8Array([1, 2, 3, 4]);
  const inspected = await client.inspect("sample.bin", bytes, {
    hexLength: 256,
  });
  assert.equal(inspected.ref, "evidence:sample.bin");
  assert.equal(calls[1].body.data, "AQIDBA==");
  assert.equal(calls[1].body.hex_length, 256);

  assert.ok((await client.hex("sample.bin", bytes, 16, 32)).rows.length > 0);
  assert.equal((await client.strings("sample.bin", bytes)).hits.length, 2);
  assert.equal((await client.entropy("sample.bin", bytes)).normalized, 0.94);
  assert.equal(
    (await client.classify("sample.bin", bytes)).category,
    "unknown",
  );
  assert.equal(
    (await client.hashes("sample.bin", bytes)).panel.sha256.length,
    64,
  );
  assert.equal((await client.compare([], [])).deltas.length, 2);
  assert.equal((await client.custody("disk-1", [])).verified, true);
  assert.equal(calls.length, 10);
});
