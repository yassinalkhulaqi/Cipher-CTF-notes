/** Wire types for the V3 cross-entity search intelligence feature. */

import type { EntityKind, EntityStatus, LinkKind } from "../../v3/types";

export type SearchField =
  | "kind"
  | "tag"
  | "severity"
  | "status"
  | "before"
  | "has";

export const SEARCH_FIELDS: SearchField[] = [
  "kind",
  "tag",
  "severity",
  "status",
  "before",
  "has",
];

export const FIELD_VALUES: Record<SearchField, string[]> = {
  kind: [
    "note",
    "folder",
    "target",
    "finding",
    "evidence",
    "playbook",
    "run",
    "report",
    "section",
    "activity",
    "extension",
    "snippet",
  ],
  tag: [],
  severity: ["trace", "info", "notice", "warning", "critical"],
  status: ["draft", "active", "archived", "deleted"],
  before: [],
  has: ["link"],
};

export const LINK_KINDS: LinkKind[] = [
  "contains",
  "relates",
  "evidences",
  "derives",
  "references",
  "duplicates",
  "supersedes",
];

export type TokenKindV2 =
  | "word"
  | "quoted"
  | "colon"
  | "lparen"
  | "rparen"
  | "pipe"
  | "minus"
  | "eof";

export interface TokenV2 {
  kind: TokenKindV2;
  value: string;
  start: number;
  end: number;
}

export type IssueCodeV2 =
  | "empty_query"
  | "query_too_long"
  | "unterminated_quote"
  | "empty_field_value"
  | "unknown_field"
  | "invalid_field_value"
  | "unknown_link_kind"
  | "unexpected_token"
  | "unclosed_group"
  | "empty_group"
  | "dangling_negation";

export interface QueryIssueV2 {
  code: IssueCodeV2;
  message: string;
  start: number;
  end: number;
  field: string;
  severity: "error" | "warning";
  hint: string;
}

export type ClauseKindV2 = "term" | "field" | "has_link";

export interface QueryClauseV2 {
  kind: ClauseKindV2;
  value: string;
  raw: string;
  field: string;
  negated: boolean;
  phrase: boolean;
  start: number;
  end: number;
  link_kind: string;
  before: number;
}

export interface AndGroupV2 {
  clauses: QueryClauseV2[];
}

export interface ParsedQueryV2 {
  text: string;
  valid: boolean;
  fingerprint: string;
  groups: AndGroupV2[];
  tokens: TokenV2[];
  issues: QueryIssueV2[];
}

export interface FacetCountV2 {
  value: string;
  count: number;
  selected: boolean;
}

export interface FacetResultV2 {
  field: string;
  values: FacetCountV2[];
  total: number;
  missing: number;
}

export interface ClusterGroupV2 {
  key: string;
  label: string;
  refs: string[];
  count: number;
  score: number;
  strategy: string;
}

export interface PivotSuggestionV2 {
  ref: string;
  kind: string;
  label: string;
  role: string;
  reason: string;
  score: number;
  link_kind: string;
  query: string;
  depth: number;
}

export interface PivotContextV2 {
  origin: string;
  origin_kind: string;
  origin_title: string;
  pivots: PivotSuggestionV2[];
  destinations: string[];
}

export interface HighlightV2 {
  start: number;
  end: number;
  value: string;
  field: string;
}

export interface FragmentV2 {
  text: string;
  highlights: HighlightV2[];
  field: string;
  prefix: boolean;
  suffix: boolean;
}

export interface RankDetailsV2 {
  total: number;
  components: Record<string, number>;
  matched_terms: string[];
  coverage: number;
}

export interface IndexDocumentV2 {
  ref: string;
  kind: EntityKind | string;
  title: string;
  summary: string;
  tags: string[];
  status: EntityStatus | string;
  severity: string;
  owner: string;
  updated_at: number;
  has_links: boolean;
  link_degree: number;
  link_kinds: string[];
  version: number;
  metadata: Record<string, unknown>;
}

export interface RankedHitV2 {
  document: IndexDocumentV2;
  score: number;
  score_details: RankDetailsV2;
  fragment: FragmentV2;
}

export interface IndexStateV2 {
  generation: number;
  documents: number;
  tokens: number;
  dirty: number;
  by_kind: Record<string, number>;
  last_action: string;
}

export interface SavedSearchV2 {
  id: string;
  name: string;
  query: string;
  description: string;
  tags: string[];
  pinned: boolean;
  use_count: number;
  created_at: number;
  updated_at: number;
}

export interface SavedFacetSetV2 {
  id: string;
  name: string;
  fields: string[];
  description: string;
  created_at: number;
}

export interface QueryTemplateV2 {
  id: string;
  name: string;
  pattern: string;
  description: string;
  placeholders: string[];
  category: string;
  example: string;
}

export interface CompletionV2 {
  value: string;
  label: string;
  kind: "field" | "value" | "saved" | "template" | "tag";
  insert_text: string;
  start: number;
  end: number;
  score: number;
}

export interface SearchResponseV2 {
  query: ParsedQueryV2;
  hits: RankedHitV2[];
  total: number;
  facets: FacetResultV2[];
  clusters: ClusterGroupV2[];
  pivots: PivotContextV2[];
  index: IndexStateV2;
}

export interface SavedSearchDraftV2 {
  id: string;
  name: string;
  query: string;
  description: string;
  tags: string[];
  pinned: boolean;
}

export interface SearchResultGroupV2 {
  key: string;
  label: string;
  hits: RankedHitV2[];
  count: number;
  score: number;
}

export function isQueryIssueError(issue: QueryIssueV2): boolean {
  return issue.severity === "error";
}
