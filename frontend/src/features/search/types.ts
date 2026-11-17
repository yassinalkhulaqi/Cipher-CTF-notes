export type SearchField =
  | "title"
  | "content"
  | "tags"
  | "target"
  | "flag"
  | "path";

export type SearchSort = "relevance" | "updated" | "title" | "id";

export type SearchFilterOperator =
  | ":"
  | "="
  | "!="
  | "~"
  | ">"
  | ">="
  | "<"
  | "<=";

export interface SearchHighlight {
  start: number;
  end: number;
  term: string;
  kind: string;
}

export interface SearchTextChunk {
  text: string;
  match: boolean;
}

export interface SearchSnippet {
  text: string;
  highlights: SearchHighlight[];
  chunks: SearchTextChunk[];
  fragments: number;
  matched: boolean;
}

export interface SearchScoreDetails {
  total: number;
  components: Record<string, number>;
  matched_terms: string[];
  coverage: number;
}

export interface SearchResultHit {
  node_id: number;
  title: string;
  path: string;
  snippet: SearchSnippet;
  score: number;
  score_details: SearchScoreDetails;
  metadata: Record<string, unknown>;
  group: string;
}

export interface FacetCount {
  value: string;
  count: number;
}

export interface ParsedQueryTerm {
  value: string;
  field: string;
  boost: number;
  prefix: boolean;
  fuzzy: boolean;
  phrase: boolean;
  negated: boolean;
  optional: boolean;
  synonym: boolean;
}

export interface ParsedFilter {
  field: string;
  operator: SearchFilterOperator;
  value: string;
  negated: boolean;
}

export interface QueryDescription {
  text: string;
  terms: ParsedQueryTerm[];
  filters: ParsedFilter[];
  sort: SearchSort;
  group_by: string;
  fingerprint: string;
}

export interface SearchResultPage {
  cursor: string | null;
  next: string | null;
  total: number | null;
  limit: number | null;
  has_more: boolean;
}

export interface SearchResponseData {
  query: QueryDescription;
  items: SearchResultHit[];
  total: number;
  facets: FacetCount[];
  suggestions: string[];
  generation: number;
  elapsed_ms: number;
}

export interface SearchResponse {
  result: SearchResponseData;
  page: SearchResultPage;
}

export interface SavedQuery {
  id: string;
  name: string;
  query: string;
  description: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  use_count: number;
  pinned: boolean;
}

export interface SavedQueryDraft {
  id: string;
  name: string;
  query: string;
  description: string;
  tags: string[];
  pinned: boolean;
}

export interface SavedQueryValidation {
  ok: boolean;
  errors: Record<string, string>;
}

export interface CommandArgumentSuggestion {
  label: string;
  value: string;
  kind: "command" | "saved" | "argument" | "option" | "term" | "example";
  description: string;
  score: number;
  insert_text: string;
  start: number;
  end: number;
  metadata: Record<string, unknown>;
}

export interface CommandCompletion {
  text: string;
  cursor: number;
  prefix: string;
  context: "command" | "argument" | "option";
  suggestions: CommandArgumentSuggestion[];
}

export interface CommandPlan {
  name: string;
  action: string;
  query: string;
  filters: string[];
  target: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface ParsedCommand {
  raw: string;
  ok: boolean;
  node: {
    name: string;
    arguments: Array<{
      name: string;
      value: string;
      position: number;
      quoted: boolean;
    }>;
    options: Record<string, string>;
    raw: string;
    leading: string;
    text: string;
  } | null;
  issues: Array<{ code: string; message: string; position: number }>;
  tokens: Array<{
    text: string;
    start: number;
    end: number;
    kind: string;
    quoted: boolean;
  }>;
  plan?: CommandPlan;
}

export interface ResultGroup {
  key: string;
  label: string;
  hits: SearchResultHit[];
  total: number;
}

export interface SearchRequestOptions {
  query: string;
  limit?: number;
  cursor?: string | null;
  sort?: SearchSort;
  groupBy?: string;
  facetField?: string;
  width?: number;
  filters?: ParsedFilter[];
}

export type SearchErrorCode =
  | "invalid_request"
  | "invalid_type"
  | "not_found"
  | "unknown_route"
  | "network_error"
  | "aborted"
  | "timeout"
  | string;

export interface SearchErrorShape {
  code: SearchErrorCode;
  message: string;
  retryable?: boolean;
}
