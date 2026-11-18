import type {
  ParsedFilter,
  ParsedQueryTerm,
  SearchFilterOperator,
  SearchSort,
} from "./types";

export interface ClientQuery {
  text: string;
  terms: ParsedQueryTerm[];
  filters: ParsedFilter[];
  sort: SearchSort;
  group_by: string;
}

export const SEARCH_FIELDS = [
  "title",
  "content",
  "tags",
  "target",
  "flag",
  "path",
] as const;

export const FILTER_FIELDS = [
  "tag",
  "tags",
  "status",
  "kind",
  "target",
  "path",
  "title",
  "flag",
  "difficulty",
  "pinned",
  "id",
  "node_id",
  "created",
  "updated",
  "group",
  ...SEARCH_FIELDS,
] as const;

export const SORT_KEYS: SearchSort[] = ["relevance", "updated", "title", "id"];

const STOPWORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "but",
  "by",
  "for",
  "from",
  "how",
  "in",
  "is",
  "it",
  "of",
  "on",
  "or",
  "that",
  "the",
  "this",
  "to",
  "was",
  "what",
  "when",
  "where",
  "which",
  "with",
]);

const SYNONYM_GROUPS: string[][] = [
  ["ctf", "challenge", "challenges"],
  ["flag", "flags", "answer", "answers"],
  ["port", "ports", "openport", "openports"],
  ["scan", "scanner", "scanning", "nmap"],
  ["host", "hosts", "target", "targets", "ip"],
  ["domain", "domains", "dns", "hostname"],
  ["web", "website", "http", "https"],
  ["vulnerability", "vuln", "vulns"],
  ["exploit", "exploits", "payload", "poc"],
  ["password", "passwords", "credential", "credentials"],
  ["note", "notes", "entry", "entries"],
  ["tag", "tags", "label", "labels"],
  ["subdomain", "subdomains", "subs"],
  ["directory", "folder", "folders", "dir"],
];

const FILTER_PATTERN = /^(-)?([a-z_][a-z0-9_]*)(!=|>=|<=|:|=|~|>|<)(.+)$/i;
const TOKEN_PATTERN = /[-+]?(?:[a-z_][a-z0-9_]*:)?"[^"]*"[~^*0-9.]*|\S+/gi;
const WORD_PATTERN = /[\p{L}\p{N}]+/gu;
const SUFFIXES = [
  "iness",
  "ingly",
  "ations",
  "ation",
  "ings",
  "ies",
  "ing",
  "ed",
  "es",
  "s",
];

export function foldText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function normalizeToken(value: string): string {
  return foldText(value).replace(/[^\p{L}\p{N}]/gu, "");
}

export function stemToken(value: string): string {
  const token = normalizeToken(value);
  if (token.length < 5) return token;
  for (const suffix of SUFFIXES) {
    if (!token.endsWith(suffix)) continue;
    const root = token.slice(0, -suffix.length);
    if (suffix === "ies" && root.length >= 2) return `${root}y`;
    if (["ing", "ed", "es", "s"].includes(suffix) && root.length >= 3) {
      if (
        ["ing", "ed"].includes(suffix) &&
        root.length >= 4 &&
        root.at(-1) === root.at(-2)
      ) {
        return root.slice(0, -1);
      }
      return root;
    }
    if (root.length >= 4) return root;
  }
  return token;
}

export function isStopword(value: string): boolean {
  return STOPWORDS.has(normalizeToken(value));
}

export function tokenizeText(text: string): string[] {
  return Array.from(text.matchAll(WORD_PATTERN))
    .map((match) => normalizeToken(match[0]))
    .filter(Boolean);
}

export function parseFilterToken(token: string): ParsedFilter {
  const match = FILTER_PATTERN.exec(token.trim());
  if (!match) throw new Error(`Invalid filter: ${token}`);
  const field = match[2].toLowerCase();
  if (!(FILTER_FIELDS as readonly string[]).includes(field)) {
    throw new Error(`Unsupported filter field: ${field}`);
  }
  const value = match[4].trim().replace(/^"|"$/g, "");
  if (!value) throw new Error(`Filter value for ${field} cannot be empty`);
  if (/[~^]|\*$/.test(value)) {
    throw new Error(`Filter value for ${field} cannot use term modifiers`);
  }
  return {
    field,
    operator: match[3] as SearchFilterOperator,
    value,
    negated: match[1] === "-",
  };
}

export function formatFilter(filter: ParsedFilter): string {
  const value = /\s/.test(filter.value) ? `"${filter.value}"` : filter.value;
  return `${filter.negated ? "-" : ""}${filter.field}${filter.operator}${value}`;
}

export function extractFilters(text: string): {
  text: string;
  filters: ParsedFilter[];
} {
  const remaining: string[] = [];
  const filters: ParsedFilter[] = [];
  for (const match of text.matchAll(TOKEN_PATTERN)) {
    try {
      filters.push(parseFilterToken(match[0]));
    } catch {
      remaining.push(match[0]);
    }
  }
  return { text: remaining.join(" ").trim(), filters };
}

export function parseSearchQuery(
  text: string,
  sort: SearchSort = "relevance",
  groupBy = "",
): ClientQuery {
  const extracted = extractFilters(text);
  const terms: ParsedQueryTerm[] = [];
  let negateNext = false;
  let optionalNext = false;
  const tokens = extracted.text.match(TOKEN_PATTERN) ?? [];
  for (const raw of tokens) {
    const upper = raw.toUpperCase();
    if (upper === "NOT") {
      negateNext = true;
      continue;
    }
    if (upper === "OR") {
      optionalNext = true;
      continue;
    }
    if (upper === "AND" || raw === "(" || raw === ")") continue;
    let value = raw;
    let field = "";
    let negated = false;
    let optional = false;
    let prefix = false;
    let fuzzy = false;
    let boost = 1;
    let phrase = false;
    if (value.startsWith("-")) {
      negated = true;
      value = value.slice(1);
    } else if (value.startsWith("+")) {
      optional = true;
      value = value.slice(1);
    }
    const fieldMatch = /^([a-z_][a-z0-9_]*):(.*)$/i.exec(value);
    if (
      fieldMatch &&
      (SEARCH_FIELDS as readonly string[]).includes(fieldMatch[1].toLowerCase())
    ) {
      field = fieldMatch[1].toLowerCase();
      value = fieldMatch[2];
    }
    const boostMatch = /\^([0-9.]+)$/.exec(value);
    if (boostMatch) {
      boost = Math.max(0, Math.min(10, Number(boostMatch[1])));
      value = value.slice(0, boostMatch.index);
    }
    const fuzzyMatch = /~(\d*)$/.exec(value);
    if (fuzzyMatch) {
      fuzzy = true;
      value = value.slice(0, fuzzyMatch.index);
    }
    if (value.endsWith("*")) {
      prefix = true;
      value = value.slice(0, -1);
    }
    if (value.startsWith('"') && value.endsWith('"') && value.length >= 2) {
      value = value.slice(1, -1);
      phrase = true;
    }
    const normalized = phrase ? foldText(value) : stemToken(value);
    if (!normalized || isStopword(normalized)) continue;
    terms.push({
      value: normalized,
      field,
      boost,
      prefix,
      fuzzy,
      phrase: phrase || normalized.includes(" "),
      negated: negated || negateNext,
      optional: optional || optionalNext,
      synonym: false,
    });
    negateNext = false;
    optionalNext = false;
  }
  const deduped = new Map<string, ParsedQueryTerm>();
  for (const term of terms) {
    const key = term.field ? `${term.field}:${term.value}` : term.value;
    const existing = deduped.get(key);
    if (!existing) {
      deduped.set(key, term);
      continue;
    }
    deduped.set(key, {
      ...term,
      boost: Math.max(existing.boost, term.boost),
      prefix: existing.prefix || term.prefix,
      fuzzy: existing.fuzzy || term.fuzzy,
      optional: existing.optional || term.optional,
    });
  }
  return {
    text,
    terms: [...deduped.values()],
    filters: extracted.filters,
    sort,
    group_by: groupBy,
  };
}

export function expandSynonyms(terms: ParsedQueryTerm[]): ParsedQueryTerm[] {
  const result = [...terms];
  const known = new Set(result.map((term) => term.field + ":" + term.value));
  for (const term of terms) {
    if (term.negated || term.phrase) continue;
    const group = SYNONYM_GROUPS.find((values) =>
      values.some((value) => stemToken(value) === term.value),
    );
    if (!group) continue;
    for (const value of group) {
      const normalized = stemToken(value);
      const key = term.field ? `${term.field}:${normalized}` : normalized;
      if (normalized === term.value || known.has(key)) continue;
      known.add(key);
      result.push({
        ...term,
        value: normalized,
        boost: Math.round(term.boost * 0.55 * 1000) / 1000,
        prefix: false,
        fuzzy: false,
        optional: true,
        synonym: true,
      });
    }
  }
  return result;
}

export function serializeQuery(query: ClientQuery): string {
  const parts: string[] = [];
  for (const filter of query.filters) parts.push(formatFilter(filter));
  for (const term of query.terms) {
    if (term.synonym) continue;
    const prefix = term.negated ? "-" : term.optional ? "+" : "";
    const field = term.field ? `${term.field}:` : "";
    const value = term.phrase ? `"${term.value}"` : term.value;
    const suffix = `${term.prefix ? "*" : ""}${term.fuzzy ? "~" : ""}${
      term.boost !== 1 ? `^${term.boost}` : ""
    }`;
    parts.push(`${prefix}${field}${value}${suffix}`);
  }
  return parts.join(" ").trim();
}

export function validateQuery(text: string): string[] {
  const errors: string[] = [];
  if (!text.trim()) errors.push("Enter a query or choose a saved search.");
  if (text.length > 500) errors.push("Query must be 500 characters or fewer.");
  for (const match of text.matchAll(TOKEN_PATTERN)) {
    try {
      parseFilterToken(match[0]);
    } catch (error) {
      if (match[0].includes(":")) {
        errors.push(error instanceof Error ? error.message : "Invalid filter.");
      }
    }
  }
  const openQuotes = (text.match(/"/g) ?? []).length % 2;
  if (openQuotes !== 0)
    errors.push("Close quoted phrases with a trailing quote.");
  return [...new Set(errors)];
}

export function queryFingerprint(text: string): string {
  let hash = 2166136261;
  const value = foldText(text);
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function describeFilters(filters: ParsedFilter[]): string {
  if (!filters.length) return "No filters";
  return filters
    .map(
      (filter) =>
        `${filter.field} ${filter.operator} ${filter.value}${
          filter.negated ? " (excluded)" : ""
        }`,
    )
    .join(", ");
}

export function completeTerm(
  text: string,
  vocabulary: string[],
  limit = 8,
): string[] {
  const prefix = (text.split(/\s+/).pop() ?? "").toLowerCase();
  if (!prefix) return [];
  return vocabulary
    .filter((term) => term.startsWith(prefix))
    .sort((a, b) => a.localeCompare(b))
    .slice(0, limit);
}

export function queryTerms(text: string): string[] {
  return parseSearchQuery(text)
    .terms.filter((term) => !term.negated && !term.synonym)
    .map((term) => term.value);
}
