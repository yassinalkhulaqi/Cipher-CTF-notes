import assert from "node:assert/strict";
import test from "node:test";
import { V2Client } from "../src/lib/apiClient";
import {
  EvidenceVaultApi,
  base64ToBytes,
  bytesToBase64,
  routeFor,
} from "../src/features/evidence/client";
import {
  DEFAULT_FILTERS,
  allTags,
  canDelete,
  canVerify,
  countByStatus,
  filterSummaries,
  formatBytes,
  formatTimestamp,
  integrityLabel,
  integrityTone,
  maskHash,
  normalizeHexPrefix,
  parseTags,
  statusLabel,
  totalBytes,
} from "../src/features/evidence/format";
import {
  describeSelection,
  evidenceReducer,
  filtersFromTags,
  hasActiveFilters,
  initialEvidenceState,
  selectIntegrity,
  selectSelected,
  selectTagOptions,
  selectVisible,
  summaryFromRecord,
} from "../src/features/evidence/state";
import type {
  EvidenceRecord,
  EvidenceSummary,
} from "../src/features/evidence/types";

const record: EvidenceRecord = {
  id: "ev_test0001",
  title: "Auth log",
  description: "Captured during triage",
  kind: "log",
  status: "acquired",
  original_filename: "auth.log",
  stored_path: "evidence://ev_test0001/auth.log",
  mime: {
    mime_type: "text/plain",
    source: "text_sniff",
    confidence: 0.8,
    extension: ".log",
    category: "document",
  },
  digests: {
    sha256: "a".repeat(64),
    md5: "b".repeat(32),
    size_bytes: 2048,
    computed_at: "2026-01-01T00:00:00Z",
  },
  thumbnail: {
    available: true,
    preview_kind: "text",
    width: 0,
    height: 0,
    page_count: 0,
    duration_seconds: 0,
    source_sha256: "a".repeat(64),
    generated_at: "2026-01-01T00:00:00Z",
    note: "",
  },
  provenance: {
    evidence_id: "ev_test0001",
    method: "manual_upload",
    tool: "redscribe",
    tool_version: "1.0",
    operator: "alice",
    source_path: "/evidence/auth.log",
    source_description: "Server log",
    acquired_at: "2026-01-01T00:00:00Z",
    case_reference: "CASE-1",
    witness: "",
    image_number: 0,
    notes: "",
  },
  tags: ["web", "auth"],
  note_id: 7,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  acquired_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
};

const summary = summaryFromRecord(record);

function makeSummary(
  overrides: Partial<EvidenceSummary> = {},
): EvidenceSummary {
  return { ...summary, ...overrides };
}

test("format helpers present evidence metadata consistently", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(2048), "2 KB");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatBytes(-1), "—");
  assert.equal(maskHash("a".repeat(64)), "aaaaaaaa…aaaaaaaa");
  assert.equal(statusLabel("acquired"), "Acquired");
  assert.equal(integrityLabel("verified"), "Verified");
  assert.equal(integrityTone(undefined), "neutral");
  assert.equal(formatTimestamp("not-a-date"), "not-a-date");
  assert.equal(formatTimestamp(""), "—");
  assert.deepEqual(parseTags("Web, web; AUTH root-cause"), [
    "web",
    "auth",
    "root-cause",
  ]);
  assert.equal(normalizeHexPrefix("  AA:bb zz "), "aabb");
  assert.equal(canVerify("acquired"), true);
  assert.equal(canVerify("disposed"), false);
  assert.equal(canDelete("sealed"), true);
});

test("filterSummaries applies query, tag, status, kind, sorting, and hash prefixes", () => {
  const items = [
    makeSummary({ id: "ev_1", title: "Alpha", tags: ["web"], size_bytes: 100 }),
    makeSummary({
      id: "ev_2",
      title: "Bravo",
      tags: ["recon"],
      size_bytes: 300,
    }),
    makeSummary({
      id: "ev_3",
      title: "Charlie",
      status: "verified",
      tags: ["web"],
      size_bytes: 200,
    }),
  ];
  assert.equal(filterSummaries(items, DEFAULT_FILTERS).length, 3);
  assert.deepEqual(
    filterSummaries(items, { ...DEFAULT_FILTERS, tag: "web" }).map(
      (item) => item.id,
    ),
    ["ev_1", "ev_3"],
  );
  assert.deepEqual(
    filterSummaries(items, { ...DEFAULT_FILTERS, status: "verified" }).map(
      (item) => item.id,
    ),
    ["ev_3"],
  );
  assert.deepEqual(
    filterSummaries(items, { ...DEFAULT_FILTERS, query: "bravo" }).map(
      (item) => item.id,
    ),
    ["ev_2"],
  );
  assert.deepEqual(
    filterSummaries(items, { ...DEFAULT_FILTERS, hashPrefix: "a" }).length,
    3,
  );
  assert.deepEqual(
    filterSummaries(items, {
      ...DEFAULT_FILTERS,
      sort: "size_bytes",
      direction: "asc",
    }).map((item) => item.id),
    ["ev_1", "ev_3", "ev_2"],
  );
  assert.deepEqual(allTags(items), ["recon", "web"]);
  assert.deepEqual(countByStatus(items), { acquired: 2, verified: 1 });
  assert.equal(totalBytes(items), 600);
});

test("evidence reducer manages loading, filters, selection, notices, and removal", () => {
  let state = initialEvidenceState();
  state = evidenceReducer(state, { type: "loading" });
  assert.equal(state.loading, true);
  state = evidenceReducer(state, {
    type: "loaded",
    items: [summary],
    stats: {
      total: 1,
      by_status: { acquired: 1 },
      by_kind: { log: 1 },
      total_bytes: 2048,
      verified: 0,
      alerts: 0,
      custody_events: 1,
      links: 0,
      legal_holds: 0,
    },
  });
  assert.equal(state.loading, false);
  assert.equal(state.stats?.total, 1);
  state = evidenceReducer(state, {
    type: "set-filter",
    key: "tag",
    value: "web",
  });
  assert.equal(hasActiveFilters(state.filters), true);
  assert.equal(selectVisible(state).length, 1);
  state = evidenceReducer(state, { type: "select", id: record.id });
  assert.equal(selectSelected(state)?.id, record.id);
  assert.equal(describeSelection(state).includes(record.id), true);
  state = evidenceReducer(state, {
    type: "integrity",
    id: record.id,
    report: {
      evidence_id: record.id,
      state: "verified",
      digest_match: true,
      md5_match: true,
      custody_valid: true,
      manifest_match: null,
      checked_at: "2026-01-01T00:00:00Z",
      issues: [],
    },
  });
  assert.equal(selectIntegrity(state)?.state, "verified");
  state = evidenceReducer(state, {
    type: "notice",
    tone: "good",
    message: "done",
  });
  assert.equal(state.notices[0].message, "done");
  state = evidenceReducer(state, { type: "dismiss-notice", id: 1 });
  assert.equal(state.notices.length, 0);
  state = evidenceReducer(state, { type: "remove", id: record.id });
  assert.equal(selectSelected(state), null);
  assert.deepEqual(state.items, []);
  state = evidenceReducer(state, { type: "reset-filters" });
  assert.equal(hasActiveFilters(state.filters), false);
  assert.deepEqual(filtersFromTags(["web", "auth"]), {
    ...DEFAULT_FILTERS,
    tag: "web",
  });
  assert.deepEqual(selectTagOptions(state), []);
});

test("base64 helpers round-trip arbitrary bytes", () => {
  const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255]);
  const encoded = bytesToBase64(bytes);
  assert.deepEqual(Array.from(base64ToBytes(encoded)), Array.from(bytes));
  assert.equal(routeFor("evidence", "custody.list"), "evidence/custody.list");
});

test("EvidenceVaultApi targets the evidence namespace routes", async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push({
      url: String(input),
      body: JSON.parse(String(init.body)) as Record<string, unknown>,
    });
    return new Response(
      JSON.stringify({ ok: true, data: { id: "ev_api0001" } }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  }) as typeof globalThis.fetch;
  const api = new EvidenceVaultApi({
    client: new V2Client({ fetch, requestId: () => "req_evidence" }),
  });
  const created = await api.ingestBytes(new Uint8Array([104, 105]), "hi.txt", {
    tags: ["web"],
  });
  assert.equal(created.id, "ev_api0001");
  assert.equal(calls[0].url, "/api/v2/evidence/ingest");
  assert.equal(calls[0].body.filename, "hi.txt");
  assert.equal(calls[0].body.content_base64, "aGk=");
  await api.detail("ev_api0001");
  assert.equal(calls[1].url, "/api/v2/evidence/detail");
  await api.custody("ev_api0001");
  assert.equal(calls[2].url, "/api/v2/evidence/custody.list");
  await api.verifyAll();
  assert.equal(calls[3].url, "/api/v2/evidence/verify_all");
  await api.exportManifest();
  assert.equal(calls[4].url, "/api/v2/evidence/manifest.export");
  await api.search({ query: "auth" });
  assert.equal(calls[5].url, "/api/v2/evidence/search");
});
