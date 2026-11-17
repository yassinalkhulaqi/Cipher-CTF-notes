import {
  chunkToSegments,
  segmentsFromHighlights,
  type TextSegment,
} from "./highlight";
import type {
  CommandArgumentSuggestion,
  CommandPlan,
  FacetCount,
  ParsedCommand,
  ParsedFilter,
  ParsedQueryTerm,
  SavedQuery,
  SearchHighlight,
  SearchResponse,
  SearchResultHit,
  SearchSnippet,
  SearchTextChunk,
} from "./types";

export type UnknownRecord = Record<string, unknown>;

export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function asBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "true") return true;
  if (value === 0 || value === "0" || value === "false") return false;
  return fallback;
}

export function normalizeSnippet(value: unknown): SearchSnippet {
  const record = asRecord(value);
  const highlights: SearchHighlight[] = asArray(record.highlights)
    .map((item) => {
      const highlight = asRecord(item);
      return {
        start: asNumber(highlight.start),
        end: asNumber(highlight.end),
        term: asString(highlight.term),
        kind: asString(highlight.kind, "term"),
      };
    })
    .filter((highlight) => highlight.end > highlight.start);
  const chunks: SearchTextChunk[] = asArray(record.chunks)
    .map((item) => {
      const chunk = asRecord(item);
      return {
        text: asString(chunk.text),
        match: asBoolean(chunk.match),
      };
    })
    .filter((chunk) => chunk.text.length > 0);
  return {
    text: asString(record.text),
    highlights,
    chunks,
    fragments: asNumber(record.fragments, 1),
    matched: asBoolean(
      record.matched,
      highlights.length > 0 || chunks.length > 0,
    ),
  };
}

export function normalizeHit(value: unknown): SearchResultHit {
  const record = asRecord(value);
  const metadata = asRecord(record.metadata);
  const details = asRecord(record.score_details);
  const components = asRecord(details.components);
  const snippet = normalizeSnippet(record.snippet);
  return {
    node_id: asNumber(record.node_id ?? record.id),
    title: asString(record.title, "Untitled"),
    path: asString(record.path),
    snippet,
    score: asNumber(record.score),
    score_details: {
      total: asNumber(details.total, asNumber(record.score)),
      components: Object.fromEntries(
        Object.entries(components).map(([key, item]) => [key, asNumber(item)]),
      ),
      matched_terms: asArray(details.matched_terms).map((item) =>
        asString(item),
      ),
      coverage: asNumber(details.coverage),
    },
    metadata,
    group: asString(record.group),
  };
}

export function normalizeFacets(value: unknown): FacetCount[] {
  return asArray(value)
    .map((item) => {
      const record = asRecord(item);
      return {
        value: asString(record.value ?? record.name),
        count: asNumber(record.count),
      };
    })
    .filter((facet) => facet.value.length > 0);
}

export function normalizeSaved(value: unknown): SavedQuery {
  const record = asRecord(value);
  return {
    id: asString(record.id),
    name: asString(record.name, "Untitled query"),
    query: asString(record.query),
    description: asString(record.description),
    tags: asArray(record.tags).map((item) => asString(item)),
    created_at: asString(record.created_at),
    updated_at: asString(record.updated_at),
    use_count: asNumber(record.use_count),
    pinned: asBoolean(record.pinned),
  };
}

export function normalizeCommandPlan(value: unknown): CommandPlan {
  const record = asRecord(value);
  return {
    name: asString(record.name),
    action: asString(record.action),
    query: asString(record.query),
    filters: asArray(record.filters).map((item) => asString(item)),
    target: asString(record.target),
    message: asString(record.message),
    metadata: asRecord(record.metadata),
  };
}

export function normalizeParsedCommand(value: unknown): ParsedCommand {
  const record = asRecord(value);
  const node = asRecord(record.node);
  return {
    raw: asString(record.raw),
    ok: asBoolean(record.ok),
    node: record.node
      ? {
          name: asString(node.name),
          arguments: asArray(node.arguments).map((item) => {
            const argument = asRecord(item);
            return {
              name: asString(argument.name),
              value: asString(argument.value),
              position: asNumber(argument.position),
              quoted: asBoolean(argument.quoted),
            };
          }),
          options: Object.fromEntries(
            Object.entries(asRecord(node.options)).map(([key, item]) => [
              key,
              asString(item),
            ]),
          ),
          raw: asString(node.raw),
          leading: asString(node.leading),
          text: asString(node.text),
        }
      : null,
    issues: asArray(record.issues).map((item) => {
      const issue = asRecord(item);
      return {
        code: asString(issue.code, "issue"),
        message: asString(issue.message),
        position: asNumber(issue.position),
      };
    }),
    tokens: asArray(record.tokens).map((item) => {
      const token = asRecord(item);
      return {
        text: asString(token.text),
        start: asNumber(token.start),
        end: asNumber(token.end),
        kind: asString(token.kind),
        quoted: asBoolean(token.quoted),
      };
    }),
    plan: record.plan ? normalizeCommandPlan(record.plan) : undefined,
  };
}

export function normalizeCommandSuggestions(
  value: unknown,
): CommandArgumentSuggestion[] {
  return asArray(value).map((item) => {
    const record = asRecord(item);
    return {
      label: asString(record.label),
      value: asString(record.value),
      kind: asString(
        record.kind,
        "argument",
      ) as CommandArgumentSuggestion["kind"],
      description: asString(record.description),
      score: asNumber(record.score),
      insert_text: asString(record.insert_text, asString(record.value)),
      start: asNumber(record.start),
      end: asNumber(record.end),
      metadata: asRecord(record.metadata),
    };
  });
}

export function normalizeSearchResponse(value: unknown): SearchResponse {
  const envelope = asRecord(value);
  const data = asRecord(envelope.result ?? envelope.data ?? envelope);
  const page = asRecord(envelope.page ?? data.page);
  const query = asRecord(data.query);
  return {
    result: {
      query: {
        text: asString(query.text),
        terms: asArray(query.terms).map((item): ParsedQueryTerm => {
          const term = asRecord(item);
          return {
            value: asString(term.value),
            field: asString(term.field),
            boost: asNumber(term.boost, 1),
            prefix: asBoolean(term.prefix),
            fuzzy: asBoolean(term.fuzzy),
            phrase: asBoolean(term.phrase),
            negated: asBoolean(term.negated),
            optional: asBoolean(term.optional),
            synonym: asBoolean(term.synonym),
          };
        }),
        filters: asArray(query.filters).map((item): ParsedFilter => {
          const filter = asRecord(item);
          return {
            field: asString(filter.field),
            operator: asString(
              filter.operator,
              ":",
            ) as ParsedFilter["operator"],
            value: asString(filter.value),
            negated: asBoolean(filter.negated),
          };
        }),
        sort: asString(
          query.sort,
          "relevance",
        ) as SearchResponse["result"]["query"]["sort"],
        group_by: asString(query.group_by),
        fingerprint: asString(query.fingerprint),
      },
      items: asArray(data.items ?? data.hits).map(normalizeHit),
      total: asNumber(data.total),
      facets: normalizeFacets(data.facets),
      suggestions: asArray(data.suggestions).map((item) => asString(item)),
      generation: asNumber(data.generation),
      elapsed_ms: asNumber(data.elapsed_ms),
    },
    page: {
      cursor: (page.cursor ?? null) as string | null,
      next: (page.next ?? null) as string | null,
      total:
        page.total === null
          ? null
          : page.total === undefined
            ? null
            : asNumber(page.total),
      limit: page.limit === undefined ? null : asNumber(page.limit),
      has_more: asBoolean(page.has_more),
    },
  };
}

export function snippetSegmentsForHit(hit: SearchResultHit): TextSegment[] {
  if (hit.snippet.chunks.length) return chunkToSegments(hit.snippet.chunks);
  return segmentsFromHighlights(hit.snippet.text, hit.snippet.highlights);
}
