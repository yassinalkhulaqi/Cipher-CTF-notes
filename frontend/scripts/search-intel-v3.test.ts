import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_QUERY_LENGTH,
  allClauses,
  completeQuery,
  describeParsedQuery,
  foldValue,
  formatClause,
  parseDateBoundary,
  parseQueryV2,
  queryFingerprint,
  serializeQueryV2,
  tokenizeV2,
  validateQueryText,
} from "../src/features/search-intel/query";
import {
  facetSelectionCount,
  mergeFacetResult,
  selectionFromQuery,
  selectionToQuery,
  toggleFacetValue,
} from "../src/features/search-intel/facets";
import {
  clusterSummary,
  clusterTone,
  groupHitsByCluster,
  ungroupedHits,
} from "../src/features/search-intel/clusters";
import {
  groupPivotsByRole,
  pivotChipLabel,
  pivotQuery,
  roleTone,
  topPivots,
} from "../src/features/search-intel/pivots";
import {
  draftFromSaved,
  filterSaved,
  isDirty,
  mergeSaved,
  normalizeDraft,
  sortSaved,
  validateDraft,
} from "../src/features/search-intel/saved";
import {
  formatCount,
  formatScore,
  relativeTime,
  severityTone,
} from "../src/features/search-intel/format";
import {
  fragmentPreview,
  splitFragment,
} from "../src/features/search-intel/highlight";
import { SearchIntelClient } from "../src/features/search-intel/client";
import type {
  ClusterGroupV2,
  FacetResultV2,
  FragmentV2,
  PivotContextV2,
  RankedHitV2,
  SavedSearchV2,
} from "../src/features/search-intel/types";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function hit(ref: string, kind: string, score = 1): RankedHitV2 {
  return {
    document: {
      ref,
      kind,
      title: `Title ${ref}`,
      summary: "A summary with a TLS cipher",
      tags: ["web"],
      status: "active",
      severity: "critical",
      owner: "operator",
      updated_at: 1700000000,
      has_links: true,
      link_degree: 1,
      link_kinds: ["evidences"],
      version: 1,
      metadata: {},
    },
    score,
    score_details: {
      total: score,
      components: {},
      matched_terms: [],
      coverage: 1,
    },
    fragment: {
      text: "A summary with a TLS cipher",
      highlights: [{ start: 17, end: 20, value: "TLS", field: "summary" }],
      field: "summary",
      prefix: false,
      suffix: false,
    },
  };
}

function saved(id: string, name: string, query: string): SavedSearchV2 {
  return {
    id,
    name,
    query,
    description: "",
    tags: [],
    pinned: false,
    use_count: 0,
    created_at: 100,
    updated_at: 100,
  };
}

test("tokenizer emits positions and special tokens", () => {
  const [tokens, issues] = tokenizeV2('-kind:finding "weak cipher"');
  assert.deepEqual(issues, []);
  assert.deepEqual(
    tokens.slice(0, 5).map((token) => token.kind),
    ["minus", "word", "colon", "word", "quoted"],
  );
  assert.equal(tokens[4].value, "weak cipher");
  const source = '-kind:finding "weak cipher"';
  assert.equal(source.slice(tokens[4].start, tokens[4].end), '"weak cipher"');
});

test("tokenizer reports unterminated quotes and long queries", () => {
  const [, issues] = tokenizeV2('kind:finding "open');
  assert.deepEqual(
    issues.map((issue) => issue.code),
    ["unterminated_quote"],
  );
  const [, longIssues] = tokenizeV2("a".repeat(MAX_QUERY_LENGTH + 1));
  assert.deepEqual(
    longIssues.map((issue) => issue.code),
    ["query_too_long"],
  );
});

test("parser reads field clauses and free terms", () => {
  const parsed = parseQueryV2("kind:finding tag:web critical");
  assert.equal(parsed.valid, true);
  assert.equal(allClauses(parsed).length, 3);
  assert.deepEqual(
    allClauses(parsed).map((clause) => clause.value),
    ["finding", "web", "critical"],
  );
});

test("parser handles negation, OR and groups", () => {
  const parsed = parseQueryV2("-kind:note OR (tag:web has:link(evidences))");
  assert.equal(parsed.valid, true);
  assert.equal(parsed.groups.length, 2);
  assert.equal(parsed.groups[0].clauses[0].negated, true);
  const link = parsed.groups[1].clauses[1];
  assert.equal(link.kind, "has_link");
  assert.equal(link.link_kind, "evidences");
});

test("parser reports stable error codes", () => {
  assert.deepEqual(
    validateQueryText("bogus:x").map((issue) => issue.code),
    ["unknown_field"],
  );
  assert.deepEqual(
    validateQueryText("kind:").map((issue) => issue.code),
    ["empty_field_value"],
  );
  assert.deepEqual(
    validateQueryText("severity:ultra").map((issue) => issue.code),
    ["invalid_field_value"],
  );
  assert.deepEqual(
    validateQueryText("has:link(nope)").map((issue) => issue.code),
    ["unknown_link_kind"],
  );
  assert.deepEqual(
    validateQueryText("(kind:finding").map((issue) => issue.code),
    ["unclosed_group"],
  );
});

test("empty query is a warning, not an error", () => {
  const parsed = parseQueryV2("   ");
  assert.equal(parsed.valid, true);
  assert.equal(parsed.issues[0].code, "empty_query");
  assert.equal(parsed.issues[0].severity, "warning");
});

test("fingerprint and folding are deterministic", () => {
  assert.equal(
    queryFingerprint("kind:finding"),
    queryFingerprint("  KIND:FINDING "),
  );
  assert.equal(foldValue("  High  Priority "), "high priority");
  assert.match(queryFingerprint("x"), /^[0-9a-f]{8}$/);
});

test("date boundary rejects impossible dates", () => {
  assert.ok(parseDateBoundary("2024-02-29") !== null);
  assert.equal(parseDateBoundary("2023-02-29"), null);
  assert.equal(parseDateBoundary("today"), null);
});

test("format and serialize clauses", () => {
  const parsed = parseQueryV2('kind:finding -"weak cipher"');
  assert.equal(formatClause(parsed.groups[0].clauses[0]), "kind:finding");
  assert.equal(serializeQueryV2(parsed), 'kind:finding -"weak cipher"');
  assert.match(describeParsedQuery(parsed), /not weak cipher/);
});

test("completion suggests fields, values, saved searches and tags", () => {
  const suggestions = completeQuery("ki", {
    saved: [{ name: "Critical", query: "kind:finding" }],
    tags: ["web"],
  });
  assert.ok(
    suggestions.some((item) => item.kind === "field" && item.value === "kind:"),
  );
  const valueSuggestions = completeQuery("kind:fi");
  assert.ok(valueSuggestions.some((item) => item.value === "finding"));
  assert.deepEqual(completeQuery(""), []);
});

test("facet selection toggling is case-insensitive and idempotent", () => {
  let selection = toggleFacetValue({}, "kind", "Finding");
  assert.deepEqual(selection, { kind: ["Finding"] });
  selection = toggleFacetValue(selection, "kind", "finding");
  assert.deepEqual(selection, {});
  assert.equal(facetSelectionCount({ kind: ["a"], tag: ["b", "c"] }), 3);
});

test("facet selection converts to and from query text", () => {
  const selection = selectionFromQuery(
    'kind:finding tag:web -tag:draft status:"in progress"',
  );
  assert.deepEqual(selection, {
    kind: ["finding"],
    tag: ["web"],
    status: ["in progress"],
  });
  const rendered = selectionToQuery(selection);
  assert.ok(rendered.includes('status:"in progress"'));
});

test("facet result merge marks selected values", () => {
  const facet: FacetResultV2 = {
    field: "kind",
    values: [
      { value: "finding", count: 4, selected: false },
      { value: "note", count: 2, selected: false },
    ],
    total: 6,
    missing: 0,
  };
  const merged = mergeFacetResult(facet, { kind: ["FINDING"] });
  assert.equal(merged.values[0].selected, true);
  assert.equal(merged.values[1].selected, false);
});

test("cluster grouping preserves hit references", () => {
  const hits = [hit("finding:a", "finding", 3), hit("note:b", "note", 1)];
  const clusters: ClusterGroupV2[] = [
    {
      key: "finding",
      label: "Finding",
      refs: ["finding:a"],
      count: 1,
      score: 3,
      strategy: "field",
    },
    {
      key: "note",
      label: "Note",
      refs: ["note:b"],
      count: 1,
      score: 1,
      strategy: "field",
    },
  ];
  const grouped = groupHitsByCluster(hits, clusters);
  assert.deepEqual(
    grouped.map((group) => group.hits[0].document.ref),
    ["finding:a", "note:b"],
  );
  assert.equal(ungroupedHits(hits).count, 2);
  assert.equal(clusterTone("finding"), "bad");
  assert.match(clusterSummary(clusters[0]), /1 result/);
});

test("pivot helpers group by role and preserve origin", () => {
  const context: PivotContextV2 = {
    origin: "finding:a",
    origin_kind: "finding",
    origin_title: "TLS issue",
    destinations: ["evidence", "report"],
    pivots: [
      {
        ref: "evidence:a",
        kind: "evidence",
        label: "Scan output",
        role: "evidences",
        reason: "evidences link",
        score: 5,
        link_kind: "evidences",
        query: 'kind:evidence "Scan output"',
        depth: 1,
      },
      {
        ref: "report:a",
        kind: "report",
        label: "Report",
        role: "report",
        reason: "references link",
        score: 4,
        link_kind: "references",
        query: "kind:report Report",
        depth: 1,
      },
    ],
  };
  const groups = groupPivotsByRole(context.pivots);
  assert.deepEqual(
    groups.map((group) => group.role),
    ["evidences", "report"],
  );
  assert.equal(topPivots(context, 1)[0].ref, "evidence:a");
  assert.equal(pivotQuery(context.pivots[0]), 'kind:evidence "Scan output"');
  assert.match(pivotChipLabel(context.pivots[0]), /Evidence: Scan output/);
  assert.equal(roleTone("report"), "info");
});

test("saved drafts validate, normalize and order", () => {
  const item = saved("q1", "Triage", "kind:finding");
  const draft = draftFromSaved(item);
  assert.equal(validateDraft(draft).ok, true);
  const bad = { ...draft, name: "", query: "" };
  assert.deepEqual(Object.keys(validateDraft(bad).errors).sort(), [
    "name",
    "query",
  ]);
  const normalized = normalizeDraft({
    ...draft,
    name: "  Triage ",
    tags: [" Web ", "web"],
  });
  assert.deepEqual(normalized.tags, ["web"]);
  assert.equal(isDirty(normalized, item), true);
  assert.deepEqual(
    sortSaved([item, saved("q2", "Alpha", "kind:note")]).map((x) => x.name),
    ["Alpha", "Triage"],
  );
  assert.equal(filterSaved([item], "triage")[0].id, "q1");
  assert.equal(mergeSaved([item], [item]).length, 1);
});

test("fragment splitting preserves highlight offsets", () => {
  const fragment: FragmentV2 = {
    text: "prefix TLS suffix",
    highlights: [{ start: 7, end: 10, value: "TLS", field: "summary" }],
    field: "summary",
    prefix: true,
    suffix: false,
  };
  const chunks = splitFragment(fragment);
  assert.deepEqual(
    chunks.map((chunk) => chunk.match),
    [false, true, false],
  );
  assert.equal(chunks[1].text, "TLS");
  assert.equal(fragmentPreview(fragment), "…prefix TLS suffix");
  assert.deepEqual(
    splitFragment({ ...fragment, highlights: [] }).map((c) => c.match),
    [false],
  );
});

test("format helpers render compact values", () => {
  assert.equal(formatCount(999), "999");
  assert.equal(formatCount(1500), "1.5k");
  assert.equal(formatScore(1.234), "1.2");
  assert.equal(relativeTime(0), "unknown");
  assert.equal(severityTone("critical"), "bad");
});

test("client decodes search envelopes and sends query body", async () => {
  const calls: string[] = [];
  const { V3Client } = await import("../src/v3/apiClient");
  const api = new SearchIntelClient(
    new V3Client({
      fetch: (async (input: RequestInfo | URL, init: RequestInit = {}) => {
        calls.push(String(input));
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        assert.equal(body.query, "kind:finding");
        return json({
          data: {
            query: {
              text: "kind:finding",
              valid: true,
              groups: [],
              tokens: [],
              issues: [],
            },
            hits: [],
            total: 0,
            facets: [],
            clusters: [],
            pivots: [],
            index: {
              generation: 1,
              documents: 0,
              tokens: 0,
              dirty: 0,
              by_kind: {},
              last_action: "init",
            },
          },
          meta: { request_id: "r1", api_version: "3.0" },
        });
      }) as typeof globalThis.fetch,
    }),
  );
  const response = await api.search({ query: "kind:finding" });
  assert.equal(response.total, 0);
  assert.deepEqual(calls, ["/api/v3/search/search"]);
});

test("client saved-search methods unwrap data", async () => {
  const { V3Client } = await import("../src/v3/apiClient");
  const api = new SearchIntelClient(
    new V3Client({
      fetch: (async (_input: RequestInfo | URL, init: RequestInit = {}) => {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        if (body.id) return json({ data: { deleted: true }, meta: {} });
        return json({
          data: { items: [saved("q1", "A", "kind:note")] },
          meta: {},
        });
      }) as typeof globalThis.fetch,
    }),
  );
  assert.equal((await api.savedList())[0].id, "q1");
  await api.savedDelete("q1");
});

test("result formatting is deterministic across renders", () => {
  const first = hit("finding:a", "finding", 2.5);
  const second = hit("finding:a", "finding", 2.5);
  assert.equal(formatScore(first.score), formatScore(second.score));
  assert.equal(splitFragment(first.fragment)[1].text, "TLS");
});
