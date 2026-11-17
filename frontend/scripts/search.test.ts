import assert from "node:assert/strict";
import test from "node:test";
import {
  applyClientFilters,
  chipsFromFilters,
  facetsFromHits,
  filterLabel,
  filtersFromQuery,
  mergeFacets,
  selectionFromFilters,
  toggleFacetFilter,
  withFacetFilters,
} from "../src/features/search/filters";
import {
  buildHighlightSegments,
  findTermMatches,
  mergeHighlights,
  plainText,
  renderHighlightedHtml,
  snippetSegments,
} from "../src/features/search/highlight";
import {
  commandIsMutating,
  commandSuggestions,
  completeCommand,
  parseCommand,
} from "../src/features/search/commands";
import {
  extractFilters,
  isStopword,
  normalizeToken,
  parseFilterToken,
  parseSearchQuery,
  queryFingerprint,
  serializeQuery,
  stemToken,
  tokenizeText,
  validateQuery,
} from "../src/features/search/query";
import {
  explainScore,
  flattenGroups,
  groupHits,
  mergeHits,
  scoreLabel,
  sortHits,
} from "../src/features/search/ranking";
import {
  draftFromSaved,
  filterSaved,
  mergeSaved,
  normalizeDraft,
  savedTags,
  sortSaved,
  validateSavedDraft,
} from "../src/features/search/saved";
import {
  asNumber,
  normalizeFacets,
  normalizeHit,
  normalizeSaved,
  normalizeSearchResponse,
} from "../src/features/search/normalizers";
import {
  draftRequestBody,
  normalizeSearchError,
  searchRequestBody,
  SearchService,
} from "../src/features/search/service";
import {
  commandDescriptors,
  mergeCommandDescriptors,
  savedQueryDescriptors,
} from "../src/features/search/adapter";
import type {
  ParsedFilter,
  SavedQuery,
  SearchResultHit,
} from "../src/features/search/types";

function hit(
  id: number,
  overrides: Partial<SearchResultHit> = {},
): SearchResultHit {
  return {
    node_id: id,
    title: `Note ${id}`,
    path: `notes/${id}.md`,
    snippet: {
      text: `nmap found ports on host ${id}`,
      highlights: [],
      chunks: [],
      fragments: 1,
      matched: true,
    },
    score: 10 - id,
    score_details: {
      total: 10 - id,
      components: { title: 4, content: 2 },
      matched_terms: ["nmap"],
      coverage: 0.5,
    },
    metadata: {
      tags: id % 2 === 0 ? ["web"] : ["recon"],
      status: id === 1 ? "open" : "closed",
      updated_at: `2026-01-0${id}T00:00:00Z`,
    },
    group: id % 2 === 0 ? "web" : "recon",
    ...overrides,
  };
}

function saved(id: string, overrides: Partial<SavedQuery> = {}): SavedQuery {
  return {
    id,
    name: `Query ${id}`,
    query: "nmap ports",
    description: "scan notes",
    tags: ["recon"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    use_count: 1,
    pinned: false,
    ...overrides,
  };
}

test("normalizeToken strips accents and punctuation", () => {
  assert.equal(normalizeToken("Café-Scan!"), "cafescan");
  assert.equal(stemToken("scanning"), "scan");
  assert.equal(stemToken("stories"), "story");
  assert.equal(stemToken("a"), "a");
  assert.equal(isStopword("the"), true);
  assert.equal(isStopword("nmap"), false);
});

test("tokenizeText extracts Unicode words", () => {
  assert.deepEqual(tokenizeText("Nmap — ports, 80/tcp"), [
    "nmap",
    "ports",
    "80",
    "tcp",
  ]);
});

test("parseFilterToken supports fields and operators", () => {
  assert.deepEqual(parseFilterToken("tag:web"), {
    field: "tag",
    operator: ":",
    value: "web",
    negated: false,
  });
  assert.deepEqual(parseFilterToken("-status!=closed"), {
    field: "status",
    operator: "!=",
    value: "closed",
    negated: true,
  });
  assert.deepEqual(parseFilterToken('title:"sql injection"'), {
    field: "title",
    operator: ":",
    value: "sql injection",
    negated: false,
  });
  assert.throws(() => parseFilterToken("bogus:value"));
  assert.throws(() => parseFilterToken("tag:"));
});

test("extractFilters removes filter tokens from free text", () => {
  const result = extractFilters('nmap tag:web -status:closed "exact phrase"');
  assert.equal(result.text, 'nmap "exact phrase"');
  assert.equal(result.filters.length, 2);
  assert.equal(result.filters[0].value, "web");
  assert.equal(result.filters[1].negated, true);
});

test("parseSearchQuery parses fields, boosts, negation and phrases", () => {
  const parsed = parseSearchQuery(
    'title:"sql injection"^3 +port* -banner~ tag:web',
    "updated",
    "tag",
  );
  assert.equal(parsed.sort, "updated");
  assert.equal(parsed.group_by, "tag");
  assert.equal(parsed.filters.length, 1);
  const fields = parsed.terms.map((term) => term.field);
  assert.deepEqual(fields, ["title", "", ""]);
  assert.equal(parsed.terms[0].phrase, true);
  assert.equal(parsed.terms[0].boost, 3);
  assert.equal(parsed.terms[1].prefix, true);
  assert.equal(parsed.terms[2].negated, true);
  assert.equal(parsed.terms[2].fuzzy, true);
});

test("serializeQuery round-trips non-synonym terms", () => {
  const parsed = parseSearchQuery('nmap tag:web +"open ports"');
  const serialized = serializeQuery(parsed);
  assert.match(serialized, /nmap/);
  assert.match(serialized, /tag:web/);
  assert.match(serialized, /\+"open ports"/);
});

test("validateQuery reports useful problems", () => {
  assert.deepEqual(validateQuery("nmap"), []);
  assert.ok(validateQuery("").some((value) => value.includes("Enter")));
  assert.ok(
    validateQuery('"unclosed').some((value) => value.includes("Close")),
  );
  assert.ok(
    validateQuery("bogus:value").some((value) => value.includes("Unsupported")),
  );
});

test("queryFingerprint is stable and case-insensitive", () => {
  assert.equal(queryFingerprint("NMAP Ports"), queryFingerprint("nmap ports"));
  assert.notEqual(queryFingerprint("nmap"), queryFingerprint("ssh"));
});

test("filtersFromQuery ignores free text", () => {
  assert.deepEqual(filtersFromQuery("nmap tag:web status:open"), [
    {
      field: "tag",
      operator: ":",
      value: "web",
      negated: false,
    },
    {
      field: "status",
      operator: ":",
      value: "open",
      negated: false,
    },
  ]);
});

test("chips and facet toggles deduplicate filters", () => {
  const filters = filtersFromQuery("tag:web status:open");
  assert.equal(chipsFromFilters(filters)[0].label, "tag: web");
  assert.equal(filterLabel(filters[1]), "status: open");
  const toggled = toggleFacetFilter(filters, "tag", "web");
  assert.equal(toggled.length, 1);
  const added = toggleFacetFilter(filters, "tag", "recon");
  assert.equal(added.length, 3);
  assert.equal(withFacetFilters("nmap", filters), "nmap tag:web status:open");
  assert.deepEqual(selectionFromFilters(filters), [
    { field: "tag", selected: ["web"] },
    { field: "status", selected: ["open"] },
  ]);
});

test("facetsFromHits counts metadata values", () => {
  const facets = facetsFromHits([hit(1), hit(2), hit(3)], "tags");
  assert.deepEqual(facets, [
    { value: "recon", count: 2 },
    { value: "web", count: 1 },
  ]);
  const merged = mergeFacets([{ value: "web", count: 7 }], facets, ["missing"]);
  assert.equal(merged[0].value, "web");
  assert.equal(merged[0].count, 7);
  assert.ok(merged.some((facet) => facet.value === "missing"));
});

test("applyClientFilters evaluates field values", () => {
  const hits = [hit(1), hit(2), hit(3)];
  const result = applyClientFilters(hits, [
    { field: "tag", operator: ":", value: "recon", negated: false },
  ]);
  assert.deepEqual(
    result.map((item) => item.node_id),
    [1, 3],
  );
  const status = applyClientFilters(hits, [
    { field: "status", operator: "!=", value: "closed", negated: false },
  ]);
  assert.deepEqual(
    status.map((item) => item.node_id),
    [1],
  );
});

test("findTermMatches respects token boundaries", () => {
  const matches = findTermMatches("nmap scanning and scanner", "scan");
  assert.equal(matches.length, 2);
  assert.deepEqual(matches[0], {
    start: 5,
    end: 13,
    term: "scan",
    kind: "exact",
  });
});

test("mergeHighlights coalesces overlaps", () => {
  const merged = mergeHighlights([
    { start: 0, end: 4, term: "nmap", kind: "exact" },
    { start: 3, end: 8, term: "ports", kind: "prefix" },
    { start: 10, end: 12, term: "80", kind: "exact" },
  ]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].end, 8);
  assert.equal(merged[0].kind, "mixed");
});

test("buildHighlightSegments preserves original text", () => {
  const segments = buildHighlightSegments("Nmap found ports", ["nmap", "port"]);
  assert.equal(plainText(segments), "Nmap found ports");
  assert.equal(segments.filter((segment) => segment.match).length, 2);
});

test("snippetSegments prefers backend chunks", () => {
  const result = snippetSegments({
    text: "ignored",
    highlights: [],
    chunks: [
      { text: "before ", match: false },
      { text: "nmap", match: true },
    ],
    fragments: 1,
    matched: true,
  });
  assert.equal(plainText(result), "before nmap");
  assert.equal(result[1].match, true);
});

test("renderHighlightedHtml escapes markup", () => {
  const html = renderHighlightedHtml("<script> nmap", ["nmap"]);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /<mark>nmap<\/mark>/);
});

test("groupHits and flattenGroups preserve hits", () => {
  const groups = groupHits([hit(1), hit(2), hit(3)], "tags");
  assert.deepEqual(
    groups.map((group) => group.key),
    ["recon", "web"],
  );
  assert.equal(groups[0].label, "Recon");
  assert.equal(flattenGroups(groups).length, 3);
});

test("sortHits and mergeHits deduplicate by node id", () => {
  const sorted = sortHits([hit(3), hit(1), hit(2)], "id");
  assert.deepEqual(
    sorted.map((item) => item.node_id),
    [1, 2, 3],
  );
  assert.equal(mergeHits([hit(1)], [hit(1), hit(2)]).length, 2);
});

test("score labels and explanations are stable", () => {
  assert.equal(scoreLabel(hit(1)), "weak");
  assert.match(explainScore(hit(1)), /title=4\.00/);
});

test("saved drafts validate and normalize", () => {
  const draft = draftFromSaved(saved("abc"));
  assert.equal(validateSavedDraft(draft).ok, true);
  const invalid = { ...draft, name: "", query: "", tags: [""] };
  const validation = validateSavedDraft(invalid);
  assert.equal(validation.ok, false);
  assert.ok(validation.errors.name);
  assert.ok(validation.errors.query);
  assert.ok(validation.errors.tags);
  const normalized = normalizeDraft({ ...draft, tags: ["  Web ", "web"] });
  assert.deepEqual(normalized.tags, ["web"]);
});

test("saved queries sort, filter and expose tags", () => {
  const items = [
    saved("a", { pinned: true }),
    saved("b", { name: "Weekly review", tags: ["review", "web"] }),
    saved("c", { use_count: 10 }),
  ];
  assert.equal(sortSaved(items)[0].id, "a");
  assert.deepEqual(savedTags(items), ["recon", "review", "web"]);
  assert.deepEqual(
    filterSaved(items, "weekly").map((item) => item.id),
    ["b"],
  );
  assert.deepEqual(
    filterSaved(items, "", "web").map((item) => item.id),
    ["b"],
  );
});

test("mergeSaved prefers incoming values", () => {
  const merged = mergeSaved(
    [saved("a", { name: "Old" })],
    [saved("a", { name: "New" }), saved("b")],
  );
  assert.equal(merged.length, 2);
  assert.equal(merged.find((item) => item.id === "a")?.name, "New");
});

test("parseCommand handles arguments and options", () => {
  const parsed = parseCommand('/search "open ports" tag:web --limit=10');
  assert.equal(parsed.ok, true);
  assert.equal(parsed.node?.name, "search");
  assert.equal(parsed.node?.arguments[0].value, "open ports");
  assert.equal(parsed.node?.arguments[0].quoted, true);
  assert.equal(parsed.node?.options.limit, "10");
  assert.equal(parsed.plan?.action, "search");
});

test("parseCommand reports invalid commands", () => {
  assert.equal(parseCommand("search nmap").ok, false);
  assert.equal(parseCommand("/bogus").ok, false);
  assert.equal(parseCommand("/search --limit=500").ok, false);
  assert.ok(parseCommand("/bogus").issues[0].code);
});

test("commandSuggestions offers names, options and saved queries", () => {
  assert.ok(commandSuggestions("/se").some((item) => item.label === "/search"));
  assert.ok(
    commandSuggestions("/search --li").some((item) => item.label === "--limit"),
  );
  const savedSuggestions = commandSuggestions("/saved week", [
    saved("b", { name: "Weekly" }),
  ]);
  assert.equal(savedSuggestions[0].kind, "saved");
  const completion = completeCommand("/search nm");
  assert.equal(completion.context, "argument");
  assert.equal(completion.cursor, "/search nm".length);
});

test("commandIsMutating identifies write commands", () => {
  assert.equal(commandIsMutating(parseCommand("/tag web triaged")), true);
  assert.equal(commandIsMutating(parseCommand("/search nmap")), false);
  assert.equal(commandIsMutating(parseCommand("/bogus")), false);
});

test("normalizers accept partial backend payloads", () => {
  const normalized = normalizeHit({
    id: 7,
    title: "Partial",
    snippet: { text: "nmap", highlights: [{ start: 0, end: 4, term: "nmap" }] },
  });
  assert.equal(normalized.node_id, 7);
  assert.equal(normalized.snippet.highlights[0].kind, "term");
  assert.deepEqual(normalizeFacets([{ name: "web", count: "2" }]), [
    { value: "web", count: 2 },
  ]);
  assert.equal(
    normalizeSaved({ id: "a", tags: ["x"], pinned: "true" }).pinned,
    true,
  );
  assert.equal(asNumber("12"), 12);
  assert.equal(asNumber("bad", 5), 5);
});

test("normalizeSearchResponse maps result and page metadata", () => {
  const response = normalizeSearchResponse({
    result: {
      query: { text: "nmap", sort: "relevance" },
      items: [{ id: 1, title: "Note", score: 3 }],
      total: 9,
      facets: [{ value: "web", count: 4 }],
      generation: 2,
      elapsed_ms: 1.5,
    },
    page: { cursor: "a", next: "b", total: 9, limit: 20, has_more: true },
  });
  assert.equal(response.result.items.length, 1);
  assert.equal(response.result.query.sort, "relevance");
  assert.equal(response.page.next, "b");
  assert.equal(response.page.has_more, true);
});

test("searchRequestBody serializes options and filters", () => {
  const body = searchRequestBody({
    query: "nmap",
    limit: 10,
    cursor: "abc",
    sort: "updated",
    groupBy: "tag",
    facetField: "status",
    width: 200,
    filters: [{ field: "tag", operator: ":", value: "web", negated: false }],
  });
  assert.equal(body.query, "nmap tag:web");
  assert.equal(body.limit, 10);
  assert.equal(body.cursor, "abc");
  assert.equal(body.group_by, "tag");
  assert.equal(body.width, 200);
});

test("draftRequestBody maps saved draft fields", () => {
  const body = draftRequestBody({
    id: "a",
    name: "Query",
    query: "nmap",
    description: "desc",
    tags: ["web"],
    pinned: true,
  });
  assert.equal(body.name, "Query");
  assert.equal(body.pinned, true);
  assert.deepEqual(body.tags, ["web"]);
  assert.equal("id" in body, false);
});

test("normalizeSearchError preserves API error details", () => {
  const error = normalizeSearchError({
    code: "invalid_request",
    message: "Bad query",
    retryable: false,
  });
  assert.equal(error.code, "network_error");
  assert.equal(error.retryable, true);
  const generic = normalizeSearchError("boom");
  assert.equal(generic.message, "boom");
});

test("SearchService routes calls and normalizes responses", async () => {
  const calls: Array<{ route: string; body: Record<string, unknown> }> = [];
  const service = new SearchService({
    call: async (route, body) => {
      calls.push({
        route: String(route),
        body: (body ?? {}) as Record<string, unknown>,
      });
      if (route === "search.query") {
        return { result: { items: [{ id: 1 }], total: 1 }, page: {} };
      }
      if (route === "saved.list") return { items: [saved("a")] };
      if (route === "commands.parse")
        return {
          raw: "/search",
          ok: true,
          node: { name: "search", arguments: [], options: {} },
          issues: [],
          tokens: [],
        };
      return {};
    },
  });
  const response = await service.search({ query: "nmap", limit: 5 });
  assert.equal(response.result.items[0].node_id, 1);
  assert.equal(calls[0].route, "search.query");
  assert.equal(
    await service.listSaved().then((items) => items[0].name),
    "Query a",
  );
  assert.equal((await service.parseCommand("/search")).node?.name, "search");
  await service.suggest("nmap");
  await service.facets("tag", "nmap");
  await service.status();
  assert.ok(calls.some((call) => call.route === "search.suggest"));
  assert.ok(calls.some((call) => call.route === "search.facets"));
  assert.ok(calls.some((call) => call.route === "search.status"));
});

test("SearchService surfaces typed errors", async () => {
  const service = new SearchService({
    call: async () => {
      throw new Error("offline");
    },
  });
  await assert.rejects(service.search({ query: "nmap" }), /offline/);
});

test("adapter builds command and saved descriptors", () => {
  const executed: string[] = [];
  const handlers = {
    runCommand: (text: string) => {
      executed.push(text);
    },
    runQuery: (query: string) => {
      executed.push(query);
    },
  };
  const commands = commandDescriptors(handlers, ["search"]);
  assert.equal(commands.length, 1);
  assert.equal(commands[0].group, "Search");
  commands[0].run();
  const savedCommands = savedQueryDescriptors(
    [saved("a", { pinned: true })],
    handlers,
  );
  assert.equal(savedCommands[0].group, "Pinned searches");
  savedCommands[0].run();
  assert.deepEqual(executed, ["/search nmap ports", "nmap ports"]);
  assert.equal(mergeCommandDescriptors(commands, commands).length, 1);
});

test("filter chips and literals remain serializable", () => {
  const filter: ParsedFilter = {
    field: "title",
    operator: ":",
    value: "open ports",
    negated: false,
  };
  assert.equal(filterLabel(filter), "title: open ports");
  assert.equal(withFacetFilters("scan", [filter]), 'scan title:"open ports"');
});
