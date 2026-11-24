/** Query language v2 client tokenizer, parser, validation and completion. */

import {
  FIELD_VALUES,
  LINK_KINDS,
  SEARCH_FIELDS,
  isQueryIssueError,
  type AndGroupV2,
  type CompletionV2,
  type IssueCodeV2,
  type ParsedQueryV2,
  type QueryClauseV2,
  type QueryIssueV2,
  type TokenKindV2,
  type TokenV2,
} from "./types";

export const MAX_QUERY_LENGTH = 500;

const SPECIALS = new Set(['"', ":", "(", ")", "|", "\n", "\r", "\t", " "]);
const EMPTY_GROUP: AndGroupV2 = { clauses: [] };

export function foldValue(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

export function tokenizeV2(text: string): [TokenV2[], QueryIssueV2[]] {
  const tokens: TokenV2[] = [];
  const issues: QueryIssueV2[] = [];
  if (text.length > MAX_QUERY_LENGTH) {
    issues.push({
      code: "query_too_long",
      message: `Query exceeds ${MAX_QUERY_LENGTH} characters`,
      start: 0,
      end: text.length,
      field: "",
      severity: "error",
      hint: "Shorten the query or split it into a saved search.",
    });
  }
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === " " || char === "\t" || char === "\n" || char === "\r") {
      index += 1;
      continue;
    }
    if (char === '"') {
      const start = index;
      index += 1;
      const pieces: string[] = [];
      let closed = false;
      while (index < text.length) {
        const current = text[index];
        if (current === "\\" && index + 1 < text.length) {
          const next = text[index + 1];
          if (next === '"' || next === "\\") {
            pieces.push(next);
            index += 2;
            continue;
          }
        }
        if (current === '"') {
          closed = true;
          index += 1;
          break;
        }
        pieces.push(current);
        index += 1;
      }
      if (!closed) {
        issues.push({
          code: "unterminated_quote",
          message: "Unterminated quoted phrase",
          start,
          end: text.length,
          field: "",
          severity: "error",
          hint: "Close the phrase with a trailing quote.",
        });
      }
      tokens.push({
        kind: "quoted",
        value: pieces.join(""),
        start,
        end: index,
      });
      continue;
    }
    const simple: Record<string, TokenKindV2> = {
      "(": "lparen",
      ")": "rparen",
      ":": "colon",
      "|": "pipe",
      "-": "minus",
    };
    if (char in simple) {
      tokens.push({
        kind: simple[char],
        value: char,
        start: index,
        end: index + 1,
      });
      index += 1;
      continue;
    }
    const start = index;
    while (index < text.length && !SPECIALS.has(text[index])) index += 1;
    tokens.push({
      kind: "word",
      value: text.slice(start, index),
      start,
      end: index,
    });
  }
  tokens.push({ kind: "eof", value: "", start: text.length, end: text.length });
  return [tokens, issues];
}

function issue(
  code: IssueCodeV2,
  message: string,
  token: TokenV2,
  field = "",
  hint = "",
  severity: "error" | "warning" = "error",
): QueryIssueV2 {
  return {
    code,
    message,
    start: token.start,
    end: Math.max(token.end, token.start + 1),
    field,
    severity,
    hint,
  };
}

export function parseDateBoundary(value: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const timestamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return timestamp / 1000;
}

export function fieldHint(value: string): string {
  const folded = foldValue(value);
  const close = SEARCH_FIELDS.find(
    (field) => field.startsWith(folded.slice(0, 2)) && folded.length > 1,
  );
  if (close) return `Did you mean '${close}:'?`;
  return `Use one of: ${SEARCH_FIELDS.join(", ")}`;
}

function validateFieldValue(
  field: string,
  value: string,
): { normalized: string; before: number; error: IssueCodeV2 | "" } {
  const normalized = foldValue(value);
  if (!normalized) return { normalized, before: 0, error: "empty_field_value" };
  if (!SEARCH_FIELDS.includes(field as (typeof SEARCH_FIELDS)[number])) {
    return { normalized, before: 0, error: "unknown_field" };
  }
  if (field === "before") {
    const before = parseDateBoundary(normalized);
    return before === null
      ? { normalized, before: 0, error: "invalid_field_value" }
      : { normalized, before, error: "" };
  }
  const vocabulary = FIELD_VALUES[field as keyof typeof FIELD_VALUES];
  if (vocabulary.length > 0 && !vocabulary.includes(normalized)) {
    return { normalized, before: 0, error: "invalid_field_value" };
  }
  return { normalized, before: 0, error: "" };
}

function conjoin(left: AndGroupV2[], right: AndGroupV2[]): AndGroupV2[] {
  if (left.length === 0) return right;
  if (right.length === 0) return left;
  const result: AndGroupV2[] = [];
  for (const first of left) {
    for (const second of right) {
      result.push({ clauses: [...first.clauses, ...second.clauses] });
    }
  }
  return result;
}

function negate(groups: AndGroupV2[]): AndGroupV2[] {
  return groups.map((group) => ({
    clauses: group.clauses.map((clause) => ({
      ...clause,
      negated: !clause.negated,
    })),
  }));
}

class V2Parser {
  private readonly tokens: TokenV2[];
  private readonly issues: QueryIssueV2[];
  private position = 0;

  constructor(private readonly text: string) {
    const [tokens, issues] = tokenizeV2(text);
    this.tokens = tokens;
    this.issues = issues;
  }

  private current(): TokenV2 {
    return this.tokens[this.position];
  }

  private advance(): TokenV2 {
    const token = this.current();
    if (this.position < this.tokens.length - 1) this.position += 1;
    return token;
  }

  private atEnd(): boolean {
    return this.current().kind === "eof";
  }

  private atOr(): boolean {
    const token = this.current();
    return (
      token.kind === "pipe" ||
      (token.kind === "word" && token.value.toUpperCase() === "OR")
    );
  }

  private atNot(): boolean {
    const token = this.current();
    return (
      token.kind === "minus" ||
      (token.kind === "word" && token.value.toUpperCase() === "NOT")
    );
  }

  parse(): ParsedQueryV2 {
    const groups = this.parseOr();
    if (!this.atEnd()) {
      const token = this.advance();
      this.issues.push(
        issue("unexpected_token", `Unexpected token '${token.value}'`, token),
      );
    }
    if (!this.text.trim()) {
      this.issues.push(
        issue(
          "empty_query",
          "Query is empty; add a term or field filter",
          this.current(),
          "",
          "Try 'kind:finding' or a free-text term.",
          "warning",
        ),
      );
    }
    return {
      text: this.text,
      valid: !this.issues.some(isQueryIssueError),
      fingerprint: queryFingerprint(this.text),
      groups,
      tokens: this.tokens,
      issues: this.issues,
    };
  }

  private parseOr(): AndGroupV2[] {
    let groups = this.parseAnd();
    while (this.atOr()) {
      this.advance();
      groups = [...groups, ...this.parseAnd()];
    }
    return groups;
  }

  private parseAnd(): AndGroupV2[] {
    let groups: AndGroupV2[] = [{ clauses: [] }];
    while (!this.atEnd() && !this.atOr() && this.current().kind !== "rparen") {
      if (
        this.current().kind === "word" &&
        this.current().value.toUpperCase() === "AND"
      ) {
        this.advance();
        continue;
      }
      groups = conjoin(groups, this.parseClause());
    }
    return groups;
  }

  private parseClause(): AndGroupV2[] {
    let negated = false;
    while (this.atNot()) {
      this.advance();
      negated = !negated;
    }
    if (this.atEnd() || this.atOr() || this.current().kind === "rparen") {
      this.issues.push(
        issue(
          "dangling_negation",
          "Negation must be followed by a term or field",
          this.current(),
        ),
      );
      return [{ clauses: [] }];
    }
    const groups = this.parsePrimary();
    return negated ? negate(groups) : groups;
  }

  private parsePrimary(): AndGroupV2[] {
    const token = this.current();
    if (token.kind === "lparen") {
      this.advance();
      if (this.current().kind === "rparen") {
        this.issues.push(
          issue("empty_group", "Group cannot be empty", this.advance()),
        );
        return [{ clauses: [] }];
      }
      const groups = this.parseOr();
      if (this.current().kind === "rparen") {
        this.advance();
      } else {
        this.issues.push(
          issue(
            "unclosed_group",
            "Group is missing a closing ')'",
            this.current(),
          ),
        );
      }
      return groups;
    }
    if (token.kind === "quoted") {
      this.advance();
      const value = foldValue(token.value);
      if (!value) return [{ clauses: [] }];
      return [
        {
          clauses: [
            {
              kind: "term",
              value,
              raw: `"${token.value}"`,
              field: "",
              negated: false,
              phrase: true,
              start: token.start,
              end: token.end,
              link_kind: "",
              before: 0,
            },
          ],
        },
      ];
    }
    if (token.kind === "word") {
      if (this.tokens[this.position + 1]?.kind === "colon") {
        return this.parseFieldClause();
      }
      this.advance();
      const value = foldValue(token.value);
      if (!value) return [{ clauses: [] }];
      return [
        {
          clauses: [
            {
              kind: "term",
              value,
              raw: token.value,
              field: "",
              negated: false,
              phrase: false,
              start: token.start,
              end: token.end,
              link_kind: "",
              before: 0,
            },
          ],
        },
      ];
    }
    this.advance();
    this.issues.push(
      issue(
        "unexpected_token",
        `Unexpected token '${token.value || token.kind}'`,
        token,
      ),
    );
    return [{ clauses: [] }];
  }

  private parseFieldClause(): AndGroupV2[] {
    const fieldToken = this.advance();
    const colon = this.advance();
    const field = foldValue(fieldToken.value);
    if (!SEARCH_FIELDS.includes(field as (typeof SEARCH_FIELDS)[number])) {
      this.issues.push(
        issue(
          "unknown_field",
          `Unknown field '${field}'`,
          fieldToken,
          field,
          fieldHint(field),
        ),
      );
    }
    const valueToken = this.current();
    if (valueToken.kind !== "word" && valueToken.kind !== "quoted") {
      this.issues.push(
        issue(
          "empty_field_value",
          `Field '${field}' needs a value`,
          colon,
          field,
        ),
      );
      return [{ clauses: [] }];
    }
    this.advance();
    const result = validateFieldValue(field, valueToken.value);
    if (
      result.error &&
      SEARCH_FIELDS.includes(field as (typeof SEARCH_FIELDS)[number])
    ) {
      this.issues.push(
        issue(
          result.error,
          `Invalid value '${valueToken.value}' for field '${field}'`,
          valueToken,
          field,
        ),
      );
      return [{ clauses: [] }];
    }
    const linkKind = field === "has" ? this.parseLinkKind() : "";
    const clause: QueryClauseV2 = {
      kind: field === "has" ? "has_link" : "field",
      value: result.normalized,
      raw: `${field}:${valueToken.value}`,
      field,
      negated: false,
      phrase: valueToken.kind === "quoted",
      start: fieldToken.start,
      end: valueToken.end,
      link_kind: linkKind,
      before: result.before,
    };
    return [{ clauses: [clause] }];
  }

  private parseLinkKind(): string {
    if (this.current().kind !== "lparen") return "";
    this.advance();
    const token = this.current();
    let kind = "";
    if (token.kind === "word") {
      this.advance();
      kind = foldValue(token.value);
      if (!LINK_KINDS.includes(kind as (typeof LINK_KINDS)[number])) {
        this.issues.push(
          issue(
            "unknown_link_kind",
            `Unknown link kind '${token.value}'`,
            token,
            "has",
          ),
        );
        kind = "";
      }
    } else {
      this.issues.push(
        issue(
          "unknown_link_kind",
          "has:link expects a link kind in parentheses",
          token,
          "has",
        ),
      );
    }
    if (this.current().kind === "rparen") {
      this.advance();
    } else {
      this.issues.push(
        issue(
          "unexpected_token",
          "Expected ')' after link kind",
          this.current(),
        ),
      );
    }
    return kind;
  }
}

export function parseQueryV2(text: string): ParsedQueryV2 {
  return new V2Parser(text).parse();
}

export function validateQueryText(text: string): QueryIssueV2[] {
  return parseQueryV2(text).issues.filter(isQueryIssueError);
}

export function queryFingerprint(text: string): string {
  let hash = 2166136261;
  const value = text.replace(/\s+/g, " ").trim().toLowerCase();
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function formatClause(clause: QueryClauseV2): string {
  const prefix = clause.negated ? "-" : "";
  if (clause.kind === "has_link") {
    return `${prefix}has:link${clause.link_kind ? `(${clause.link_kind})` : ""}`;
  }
  if (clause.kind === "field") {
    const value = /\s/.test(clause.value) ? `"${clause.value}"` : clause.value;
    return `${prefix}${clause.field}:${value}`;
  }
  const value = clause.phrase ? `"${clause.value}"` : clause.value;
  return `${prefix}${value}`;
}

export function serializeQueryV2(parsed: ParsedQueryV2): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const group of parsed.groups) {
    const rendered = group.clauses.map(formatClause).filter((part) => {
      if (seen.has(part)) return false;
      seen.add(part);
      return true;
    });
    if (rendered.length) parts.push(rendered.join(" "));
  }
  return parts.join(" OR ");
}

export function allClauses(parsed: ParsedQueryV2): QueryClauseV2[] {
  return parsed.groups.flatMap((group) => group.clauses);
}

export interface CompletionOptions {
  fields?: string[];
  values?: string[];
  saved?: Array<{ name: string; query: string }>;
  templates?: Array<{
    id: string;
    name: string;
    pattern: string;
    example?: string;
  }>;
  tags?: string[];
  limit?: number;
}

export function completeQuery(
  text: string,
  options: CompletionOptions = {},
): CompletionV2[] {
  const start = text.lastIndexOf(" ") + 1;
  const partial = text.slice(start);
  const needle = partial.toLowerCase();
  if (!needle) return [];
  const results: CompletionV2[] = [];
  const limit = options.limit ?? 8;
  const add = (item: CompletionV2) => results.push(item);
  if (partial.includes(":")) {
    const [fieldPart, valuePart = ""] = partial.split(":", 2);
    const field = fieldPart.replace(/^-/, "").toLowerCase();
    const vocabulary = [
      ...((FIELD_VALUES as Record<string, string[]>)[field] ?? []),
      ...(options.values ?? []),
      ...(options.tags ?? []),
    ];
    for (const value of vocabulary) {
      if (!value.toLowerCase().startsWith(valuePart.toLowerCase())) continue;
      add({
        value,
        label: `${field}:${value}`,
        kind: "value",
        insert_text: `${field}:${value} `,
        start,
        end: text.length,
        score: 10 - valuePart.length,
      });
    }
  } else {
    const fields = options.fields ?? SEARCH_FIELDS;
    for (const field of fields) {
      if (!field.startsWith(needle.replace(/^-/, ""))) continue;
      add({
        value: `${field}:`,
        label: `${field}:`,
        kind: "field",
        insert_text: `${field}:`,
        start,
        end: text.length,
        score: 20 - partial.length,
      });
    }
    for (const saved of options.saved ?? []) {
      if (!saved.name.toLowerCase().includes(needle)) continue;
      add({
        value: saved.query,
        label: saved.name,
        kind: "saved",
        insert_text: saved.query,
        start,
        end: text.length,
        score: 8,
      });
    }
    for (const template of options.templates ?? []) {
      const haystack = `${template.name} ${template.pattern}`.toLowerCase();
      if (!haystack.includes(needle)) continue;
      add({
        value: template.id,
        label: template.name,
        kind: "template",
        insert_text: template.example ?? template.pattern,
        start,
        end: text.length,
        score: 6,
      });
    }
    for (const tag of options.tags ?? []) {
      if (!tag.toLowerCase().startsWith(needle.replace(/^-/, ""))) continue;
      add({
        value: tag,
        label: `tag:${tag}`,
        kind: "tag",
        insert_text: `tag:${tag} `,
        start,
        end: text.length,
        score: 4,
      });
    }
  }
  results.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
  const seen = new Set<string>();
  return results
    .filter((item) => {
      if (seen.has(item.label)) return false;
      seen.add(item.label);
      return true;
    })
    .slice(0, limit);
}

export function describeParsedQuery(parsed: ParsedQueryV2): string {
  const clauses = allClauses(parsed);
  if (!clauses.length) return "Matches all entities";
  return clauses
    .map((clause) => {
      const rendered = formatClause(clause).replace(/^-/, "").replace(/"/g, "");
      return clause.negated ? `not ${rendered}` : rendered;
    })
    .join(clauses.length > 1 ? " and " : "");
}
