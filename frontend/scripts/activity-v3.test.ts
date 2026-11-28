import assert from "node:assert/strict";
import test from "node:test";

import { V3Client } from "../src/v3/apiClient";

import {
  ActivityClient,
  makeActivityClient,
} from "../src/features/activity/client";
import {
  FILTER_KEYS,
  chipFromToken,
  chipsToQuery,
  facetChips,
  makeChip,
  parseFilterQuery,
  removeChip,
  severityRank,
  severityTone,
  tokenizeFilterQuery,
  toggleChip,
  validateFilterQuery,
} from "../src/features/activity/filters";
import {
  DENSITY_OPTIONS,
  PERIOD_OPTIONS,
  dayKeyFromTimestamp,
  densityLabel,
  digestCardData,
  entryMeta,
  entryTone,
  formatClock,
  formatCount,
  formatDayLabel,
  periodLabel,
  relativeTime,
  retrospectiveTiles,
  severitySummary,
  shortRef,
  summarizeFacets,
  truncate,
} from "../src/features/activity/format";
import {
  countByKind,
  filterEntriesByChips,
  groupEntries,
  jumpTargets,
  mergeStreams,
  pageSlice,
  sortEntries,
  uniqueValues,
} from "../src/features/activity/groups";
import {
  activityReducer,
  digestRequest,
  effectiveQuery,
  initialActivityState,
  retrospectiveRequest,
  stateSignature,
  streamRequest,
} from "../src/features/activity/state";
import type {
  ActivityEntry,
  Digest,
  FacetCounts,
  RetrospectiveSummary,
  StreamResult,
} from "../src/features/activity/types";
import { EMPTY_STREAM } from "../src/features/activity/types";

const NOW = 1_700_000_000;
const DAY = 86_400;

function entry(
  sequence: number,
  overrides: Partial<ActivityEntry> = {},
): ActivityEntry {
  return {
    sequence,
    kind: "finding.created",
    title: "Finding Created",
    summary: "SQL injection discovered",
    actor: "alice",
    severity: "info",
    timestamp: NOW - sequence * 60,
    iso_timestamp: new Date((NOW - sequence * 60) * 1000).toISOString(),
    date_key: "2023-11-14",
    week_key: "2023-W46",
    subject_ref: "finding:f-1",
    payload: { title: "SQL injection", token: "[redacted]" },
    jump: {
      ref: "finding:f-1",
      kind: "finding",
      value: "f-1",
      label: "f-1",
      route: "/resolve/finding/f-1",
      resolvable: true,
    },
    correlation_id: "batch-1",
    tags: ["web", "sqli"],
    redactions: ["token"],
    ...overrides,
  };
}

function entries(): ActivityEntry[] {
  return [
    entry(1),
    entry(2, {
      kind: "note.created",
      actor: "bob",
      severity: "trace",
      timestamp: NOW - 2 * DAY,
      date_key: "2023-11-12",
      week_key: "2023-W45",
      subject_ref: "note:n-1",
      tags: [],
    }),
    entry(3, {
      kind: "finding.updated",
      severity: "warning",
      timestamp: NOW - DAY,
      date_key: "2023-11-13",
      week_key: "2023-W46",
    }),
    entry(4, {
      kind: "evidence.added",
      actor: "carol",
      severity: "notice",
      subject_ref: "evidence:e-1",
      jump: null,
    }),
  ];
}

function facets(): FacetCounts {
  return {
    kinds: { "finding.created": 2, "note.created": 1 },
    actors: { alice: 2, bob: 1 },
    severities: { info: 2, warning: 1 },
    subjects: { "finding:f-1": 2 },
  };
}

function stream(): StreamResult {
  const rows = entries();
  return {
    ...EMPTY_STREAM,
    entries: rows,
    total: 4,
    groups: groupEntries(rows),
    facets: facets(),
    query: "kind:finding.created",
    timezone: "UTC",
    warnings: ["stale cache"],
    page: {
      page: 1,
      page_size: 10,
      total: 4,
      has_next: false,
      has_previous: false,
    },
  };
}

function json(data: unknown, status = 200): Response {
  return new Response(
    JSON.stringify({ data, meta: { request_id: "req", api_version: "3.0" } }),
    {
      status,
      headers: { "Content-Type": "application/json" },
    },
  );
}

function fakeClient(
  handler: (route: string, body: Record<string, unknown>) => unknown,
): {
  client: ActivityClient;
  calls: Array<{ route: string; body: Record<string, unknown> }>;
} {
  const calls: Array<{ route: string; body: Record<string, unknown> }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    const url = String(input);
    const route = url.slice(url.lastIndexOf("/") + 1);
    const body = JSON.parse(String(init.body ?? "{}")) as Record<
      string,
      unknown
    >;
    calls.push({ route, body });
    return json(handler(route, body));
  }) as typeof globalThis.fetch;
  return {
    client: new ActivityClient(
      new V3Client({ fetch: fetchImpl, requestId: () => "req_test" }),
    ),
    calls,
  };
}

test("filter DSL tokenizes quoted values and builds chips", () => {
  assert.deepEqual(
    tokenizeFilterQuery('kind:finding.created text:"hello world"'),
    ["kind:finding.created", "text:hello world"],
  );
  assert.deepEqual(tokenizeFilterQuery("  a   b\\ c "), ["a", "b c"]);
  const parsed = parseFilterQuery(
    'kind:finding.created -actor:bob text:"sql injection"',
  );
  assert.equal(parsed.errors.length, 0);
  assert.equal(parsed.chips.length, 3);
  assert.equal(parsed.chips[1].operator, "exclude");
  assert.equal(parsed.chips[2].value, "sql injection");
  assert.equal(
    parsed.normalized,
    "kind:finding.created -actor:bob text:sql injection",
  );
  assert.deepEqual(chipFromToken("!kind:note.created")?.operator, "exclude");
  assert.equal(chipFromToken(""), null);
  assert.equal(chipFromToken("kind:"), null);
  assert.deepEqual(FILTER_KEYS.slice(0, 3), ["kind", "actor", "subject"]);
});

test("filter DSL validation reports unknown keys and severities", () => {
  const valid = validateFilterQuery("kind:finding.created severity:warning");
  assert.equal(valid.valid, true);
  const invalid = validateFilterQuery("bogus:value severity:nope since:xyz");
  assert.equal(invalid.valid, false);
  assert.equal(invalid.errors.length, 3);
  assert.ok(invalid.errors[0].includes("Unsupported filter key"));
  const numeric = validateFilterQuery("since:1700000000");
  assert.equal(numeric.valid, true);
});

test("chip helpers toggle, remove, and render tokens", () => {
  const chips = [
    makeChip("kind", "finding.created"),
    makeChip("actor", "alice", "exclude"),
  ];
  assert.equal(chipsToQuery(chips), "kind:finding.created -actor:alice");
  assert.equal(chips[1].token, "-actor:alice");
  const added = toggleChip(chips, makeChip("severity", "warning"));
  assert.equal(added.length, 3);
  assert.equal(toggleChip(added, makeChip("severity", "warning")).length, 2);
  assert.equal(removeChip(chips, "actor:alice").length, 2);
  assert.equal(removeChip(chips, "-actor:alice").length, 1);
  const suggestions = facetChips(facets(), "kinds", 1);
  assert.equal(suggestions[0].key, "kind");
  assert.equal(suggestions[0].value, "finding.created");
  assert.equal(facetChips(facets(), "severities")[0].key, "severity");
  assert.equal(facetChips(facets(), "subjects")[0].key, "subject");
});

test("severity helpers rank and classify values", () => {
  assert.ok(severityRank("critical") > severityRank("info"));
  assert.equal(severityRank("unknown"), -1);
  assert.equal(severityTone("critical"), "critical");
  assert.equal(severityTone("warning"), "warning");
  assert.equal(severityTone("notice"), "notice");
  assert.equal(severityTone("info"), "info");
  assert.equal(severityTone("bogus"), "trace");
});

test("formatting helpers render readable activity values", () => {
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatCount(Number.NaN), "0");
  assert.equal(truncate("a  b   c", 4), "a b…");
  assert.equal(shortRef("finding:f-1"), "f-1");
  assert.equal(shortRef("plain"), "plain");
  assert.equal(relativeTime(NOW - 30, NOW), "just now");
  assert.equal(relativeTime(NOW - 300, NOW), "5m ago");
  assert.equal(relativeTime(NOW - 7200, NOW), "2h ago");
  assert.equal(relativeTime(NOW - 3 * DAY, NOW), "3d ago");
  assert.equal(relativeTime(NOW - 30 * DAY, NOW), "2023-10-15");
  assert.equal(dayKeyFromTimestamp(NOW), "2023-11-14");
  assert.equal(formatDayLabel("2023-11-14", NOW), "Today");
  assert.equal(formatDayLabel("2023-11-13", NOW), "Yesterday");
  assert.equal(formatDayLabel("2023-11-01", NOW), "2023-11-01");
  assert.equal(formatClock(NOW), "22:13");
  assert.equal(densityLabel("compact"), "Compact");
  assert.equal(periodLabel("weekly"), "Weekly digest");
  assert.deepEqual(DENSITY_OPTIONS, ["compact", "comfortable", "detailed"]);
  assert.deepEqual(PERIOD_OPTIONS, ["daily", "weekly"]);
});

test("entry formatting covers tones, metadata, and payload notes", () => {
  const rows = entries();
  assert.equal(entryTone(rows[2]), "warning");
  assert.equal(entryMeta(rows[0], "compact", NOW), "by alice");
  assert.ok(entryMeta(rows[0], "detailed", NOW).includes("f-1"));
  assert.ok(entryMeta(rows[0], "detailed", NOW).includes("1m ago"));
  const digest: Digest = {
    period: "daily",
    key: "2023-11-14",
    label: "2023-11-14",
    start: NOW - DAY,
    end: NOW,
    iso_start: "2023-11-13T22:13:20.000Z",
    iso_end: "2023-11-14T22:13:20.000Z",
    timezone: "UTC",
    entry_count: 4,
    counts: { "finding.created": 2, "note.created": 1 },
    actor_counts: { alice: 3, bob: 1 },
    sections: [],
    highlights: rows.slice(0, 2),
  };
  const card = digestCardData(digest);
  assert.equal(card.title, "2023-11-14");
  assert.equal(card.count, "4");
  assert.ok(card.subtitle.includes("finding.created"));
  assert.equal(card.highlights.length, 2);
  assert.ok(summarizeFacets(facets()).includes("2 kinds"));
  assert.ok(severitySummary(facets()).includes("warning: 1"));
});

test("grouping sorts entries and builds newest-first date groups", () => {
  const rows = entries();
  assert.deepEqual(
    sortEntries(rows).map((item) => item.sequence),
    [4, 3, 2, 1],
  );
  const grouped = groupEntries(rows);
  assert.deepEqual(
    grouped.map((group) => group.key),
    ["2023-11-14", "2023-11-13", "2023-11-12"],
  );
  assert.equal(grouped[0].count, 2);
  const weekly = groupEntries(rows, "weekly");
  assert.equal(weekly.length, 2);
  assert.deepEqual(uniqueValues(rows, "actor"), ["alice", "bob", "carol"]);
  assert.equal(jumpTargets(rows).length, 3);
  assert.equal(countByKind(rows)["finding.created"], 1);
  assert.deepEqual(
    pageSlice(rows, 2, 2).map((item) => item.sequence),
    [2, 1],
  );
});

test("client-side chip filtering handles include and exclude operators", () => {
  const rows = entries();
  assert.equal(filterEntriesByChips(rows, []).length, 4);
  assert.equal(
    filterEntriesByChips(rows, [makeChip("kind", "finding.created")]).length,
    1,
  );
  assert.equal(
    filterEntriesByChips(rows, [makeChip("actor", "bob")]).length,
    1,
  );
  assert.equal(
    filterEntriesByChips(rows, [makeChip("severity", "warning")]).length,
    1,
  );
  assert.equal(filterEntriesByChips(rows, [makeChip("tag", "web")]).length, 3);
  assert.equal(
    filterEntriesByChips(rows, [makeChip("kind", "finding.created", "exclude")])
      .length,
    3,
  );
  assert.equal(
    filterEntriesByChips(rows, [makeChip("text", "sql injection")]).length,
    4,
  );
  assert.equal(filterEntriesByChips(rows, [makeChip("since", "1")]).length, 4);
});

test("mergeStreams combines entries and warnings", () => {
  const first = stream();
  const second = stream();
  second.entries = [entry(9)];
  second.warnings = ["second"];
  const merged = mergeStreams(first, second);
  assert.equal(merged.entries.length, 5);
  assert.equal(merged.entries[0].sequence, 9);
  assert.deepEqual(merged.warnings, ["stale cache", "second"]);
  assert.equal(merged.total, 4);
});

test("reducer handles loading, stream, chips, density, and errors", () => {
  let state = initialActivityState({ now: NOW });
  assert.equal(state.stream.total, 0);
  assert.equal(state.density, "comfortable");
  state = activityReducer(state, { type: "loading" });
  assert.equal(state.loading, true);
  state = activityReducer(state, { type: "stream", value: stream() });
  assert.equal(state.loading, false);
  assert.equal(state.stream.total, 4);
  state = activityReducer(state, { type: "query", value: "actor:alice" });
  assert.equal(state.query, "actor:alice");
  state = activityReducer(state, {
    type: "toggle-chip",
    value: makeChip("kind", "note.created"),
  });
  assert.equal(state.chips.length, 1);
  state = activityReducer(state, {
    type: "toggle-chip",
    value: makeChip("kind", "note.created"),
  });
  assert.equal(state.chips.length, 0);
  state = activityReducer(state, {
    type: "chips",
    value: [makeChip("actor", "bob")],
  });
  assert.equal(state.chips[0].value, "bob");
  state = activityReducer(state, { type: "remove-chip", value: "actor:bob" });
  assert.equal(state.chips.length, 0);
  state = activityReducer(state, { type: "clear-chips" });
  assert.equal(state.query, "");
  state = activityReducer(state, { type: "density", value: "detailed" });
  assert.equal(state.density, "detailed");
  state = activityReducer(state, { type: "period", value: "weekly" });
  assert.equal(state.period, "weekly");
  state = activityReducer(state, { type: "tab", value: "digest" });
  assert.equal(state.tab, "digest");
  state = activityReducer(state, { type: "select", value: 3 });
  assert.equal(state.selectedSequence, 3);
  state = activityReducer(state, { type: "error", value: "boom" });
  assert.equal(state.error, "boom");
  state = activityReducer(state, { type: "now", value: NOW + 1 });
  assert.equal(state.now, NOW + 1);
  state = activityReducer(state, { type: "reset" });
  assert.equal(state.error, "");
  assert.equal(state.now, NOW + 1);
});

test("state request builders derive query and windows", () => {
  let state = initialActivityState({ now: NOW });
  state = activityReducer(state, { type: "query", value: "text:sql" });
  state = activityReducer(state, {
    type: "toggle-chip",
    value: makeChip("kind", "finding.created"),
  });
  assert.equal(effectiveQuery(state), "text:sql kind:finding.created");
  assert.equal(streamRequest(state).size, 100);
  assert.equal(streamRequest(state).density, "comfortable");
  assert.equal(streamRequest(state).query, "text:sql kind:finding.created");
  assert.equal(digestRequest(state).period, "daily");
  assert.equal(digestRequest(state).generated_at, NOW);
  const retro = retrospectiveRequest(state);
  assert.equal(retro.end, NOW);
  assert.equal(retro.start, NOW - 30 * DAY);
  const first = stateSignature(state);
  state = activityReducer(state, { type: "density", value: "compact" });
  assert.notEqual(stateSignature(state), first);
});

test("retrospective tiles render display values", () => {
  const summary: RetrospectiveSummary = {
    start: NOW - DAY,
    end: NOW,
    iso_start: "2023-11-13T22:13:20.000Z",
    iso_end: "2023-11-14T22:13:20.000Z",
    timezone: "UTC",
    total_events: 12,
    active_days: 3,
    active_weeks: 1,
    longest_streak: 2,
    trailing_streak: 1,
    busiest_day: { date_key: "2023-11-14", count: 5 },
    top_kinds: [{ value: "finding.created", count: 4 }],
    top_actors: [{ value: "alice", count: 6 }],
    top_subjects: [],
    severity_mix: { info: 10, warning: 2 },
    highlights: entries().slice(0, 2),
    daily_counts: [],
  };
  const tiles = retrospectiveTiles(summary);
  assert.equal(tiles.length, 4);
  assert.equal(tiles[0].value, "12");
  assert.equal(tiles[3].value, "2023-11-14");
});

test("client exposes every activity route and forwards bodies", async () => {
  const { client, calls } = fakeClient(() => ({ ok: true }));
  assert.equal(Object.keys(client.routes).length, 12);
  assert.ok(Object.values(client.routes).every((route) => route.length > 0));
  assert.ok(Object.values(client.routes).includes("stream"));
  assert.ok(Object.values(client.routes).includes("retrospective"));
  await client.stream({ query: "kind:finding.created", size: 5 });
  assert.deepEqual(calls[0].body, { query: "kind:finding.created", size: 5 });
  await client.validate("actor:bob");
  assert.deepEqual(calls[1].body, { query: "actor:bob" });
  await client.digest({ period: "weekly" });
  assert.deepEqual(calls[2].body, { period: "weekly" });
  await client.since("alice", 10);
  assert.deepEqual(calls[3].body, { identity: "alice", limit: 10 });
  await client.mark("alice", "note", 7);
  assert.deepEqual(calls[4].body, {
    identity: "alice",
    note: "note",
    sequence: 7,
  });
  await client.retrospective(1, 2, 3);
  assert.deepEqual(calls[5].body, { start: 1, end: 2, top_limit: 3 });
  await client.redact({ token: "x" });
  assert.deepEqual(calls[6].body, { payload: { token: "x" } });
  await client.entry(4);
  assert.deepEqual(calls[7].body, { sequence: 4 });
  await client.stats();
  await client.health();
  await client.modes();
  assert.equal(calls.length, 11);
});

test("client decodes stream responses and propagates errors", async () => {
  const fetchImpl = (async () => json(stream())) as typeof globalThis.fetch;
  const client = makeActivityClient({ fetch: fetchImpl });
  const result = await client.stream();
  assert.equal(result.total, 4);
  assert.equal(result.groups.length, 3);
  assert.equal(result.facets.actors.alice, 2);

  const failing = (async () =>
    json(
      {
        error: {
          code: "not_found",
          message: "missing",
          field: "",
          retryable: false,
          context: {},
        },
        meta: {},
      },
      404,
    )) as typeof globalThis.fetch;
  await assert.rejects(() => makeActivityClient({ fetch: failing }).entry(99));
});
