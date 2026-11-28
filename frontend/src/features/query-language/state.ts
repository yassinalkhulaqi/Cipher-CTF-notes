import type {
  BooleanConnector,
  FacetView,
  QueryField,
  QueryOperator,
  SavedQueryView,
  SearchResponse,
} from "./client";

export interface QueryState {
  expression: string;
  submittedExpression: string;
  selectedFacets: Record<string, string[]>;
  savedQueries: SavedQueryView[];
  results: SearchResponse["hits"]["items"];
  facets: FacetView[];
  clusters: SearchResponse["clusters"];
  clusterSummary: Record<string, unknown>;
  total: number;
  page: number;
  pageSize: number;
  nextCursor: string;
  warnings: string[];
  loading: boolean;
  error: string;
  saveName: string;
  activeChip: string;
}

export type QueryAction =
  | { type: "expression"; value: string }
  | { type: "submit" }
  | { type: "loading"; value: boolean }
  | { type: "error"; message: string }
  | { type: "results"; response: SearchResponse }
  | { type: "toggle-facet"; field: QueryField; value: string }
  | { type: "clear-facets" }
  | { type: "saved"; queries: SavedQueryView[] }
  | { type: "save-name"; value: string }
  | { type: "apply-saved"; query: SavedQueryView }
  | {
      type: "apply-clause";
      field: QueryField;
      operator: QueryOperator;
      value: string;
    }
  | { type: "page"; value: number }
  | { type: "reset" };

export interface HighlightSegment {
  text: string;
  kind: "field" | "operator" | "boolean" | "value" | "text" | "space";
}

const BOOLEAN_WORDS: BooleanConnector[] = ["AND", "OR", "NOT"];
const OPERATOR_WORDS: string[] = ["contains", "starts_with", "in"];

export function initialQueryState(saved: SavedQueryView[] = []): QueryState {
  return {
    expression: "",
    submittedExpression: "",
    selectedFacets: {},
    savedQueries: [...saved],
    results: [],
    facets: [],
    clusters: [],
    clusterSummary: {},
    total: 0,
    page: 1,
    pageSize: 10,
    nextCursor: "",
    warnings: [],
    loading: false,
    error: "",
    saveName: "",
    activeChip: "",
  };
}

export function appendClause(
  expression: string,
  field: QueryField,
  operator: QueryOperator,
  value: string,
): string {
  const clean = value.trim();
  if (!clean) return expression;
  const literal = clean.replace(/"/g, '\\"');
  const clause =
    operator === "="
      ? `${field}:"${literal}"`
      : `${field}:${operator}(${clean.includes(" ") ? `"${literal}"` : clean})`;
  return expression.trim() ? `${expression.trim()} AND ${clause}` : clause;
}

export function toggleFacetValues(
  selected: Record<string, string[]>,
  field: QueryField,
  value: string,
): Record<string, string[]> {
  const current = selected[field] ?? [];
  const needle = value.toLowerCase();
  const found = current.some((item) => item.toLowerCase() === needle);
  const next = found
    ? current.filter((item) => item.toLowerCase() !== needle)
    : [...current, value];
  return { ...selected, [field]: next };
}

export function queryReducer(
  state: QueryState,
  action: QueryAction,
): QueryState {
  switch (action.type) {
    case "expression":
      return { ...state, expression: action.value, error: "" };
    case "submit":
      return {
        ...state,
        submittedExpression: state.expression.trim(),
        page: 1,
        nextCursor: "",
        error: "",
      };
    case "loading":
      return { ...state, loading: action.value };
    case "error":
      return { ...state, loading: false, error: action.message };
    case "results": {
      const hits = action.response.hits;
      return {
        ...state,
        results: hits.items,
        facets: action.response.facets,
        clusters: action.response.clusters,
        clusterSummary: action.response.cluster_summary,
        total: hits.total,
        page: hits.page,
        pageSize: hits.page_size,
        nextCursor: hits.next_cursor,
        warnings: action.response.warnings,
        loading: false,
        error: "",
      };
    }
    case "toggle-facet":
      return {
        ...state,
        selectedFacets: toggleFacetValues(
          state.selectedFacets,
          action.field,
          action.value,
        ),
        page: 1,
        nextCursor: "",
      };
    case "clear-facets":
      return { ...state, selectedFacets: {}, page: 1, nextCursor: "" };
    case "saved":
      return { ...state, savedQueries: [...action.queries] };
    case "save-name":
      return { ...state, saveName: action.value };
    case "apply-saved":
      return {
        ...state,
        expression: action.query.expression,
        submittedExpression: action.query.expression,
        saveName: action.query.name,
        activeChip: action.query.id,
        page: 1,
        nextCursor: "",
        error: "",
      };
    case "apply-clause":
      return {
        ...state,
        expression: appendClause(
          state.expression,
          action.field,
          action.operator,
          action.value,
        ),
        error: "",
      };
    case "page":
      return {
        ...state,
        page: Math.max(1, action.value),
        nextCursor: "",
        error: "",
      };
    case "reset":
      return initialQueryState(state.savedQueries);
  }
}

export function selectedFacetCount(state: QueryState): number {
  return Object.values(state.selectedFacets).reduce(
    (total, values) => total + values.length,
    0,
  );
}

export function buildFacetSelections(
  state: QueryState,
): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const [field, values] of Object.entries(state.selectedFacets)) {
    if (values.length > 0) result[field] = [...values];
  }
  return result;
}

export function highlightExpression(expression: string): HighlightSegment[] {
  const segments: HighlightSegment[] = [];
  const pattern =
    /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\(|\)|,|:|\s+|[^\s():,]+)/g;
  let pendingField: string | null = null;
  for (const match of expression.matchAll(pattern)) {
    const text = match[0];
    if (/^\s+$/.test(text)) {
      segments.push({ text, kind: "space" });
      continue;
    }
    if (text === ":") {
      segments.push({ text, kind: "operator" });
      continue;
    }
    if (text === "(" || text === ")" || text === ",") {
      segments.push({ text, kind: "operator" });
      continue;
    }
    if (pendingField !== null) {
      pendingField = null;
      const operator = OPERATOR_WORDS.includes(text.toLowerCase());
      const isSymbol = /^(=|!=|>|contains|starts_with|in)$/i.test(text);
      segments.push({
        text,
        kind: operator || isSymbol ? "operator" : "value",
      });
      continue;
    }
    const upper = text.toUpperCase();
    if (BOOLEAN_WORDS.includes(upper as BooleanConnector)) {
      segments.push({ text, kind: "boolean" });
      continue;
    }
    if (/^(title|body|tag|kind|status|flag|target|author)$/i.test(text)) {
      pendingField = text;
      segments.push({ text, kind: "field" });
      continue;
    }
    segments.push({ text, kind: "value" });
  }
  return segments;
}

export function resultLabel(
  result: SearchResponse["hits"]["items"][number],
): string {
  if (typeof result.title === "string" && result.title) return result.title;
  if (typeof result.id === "string" && result.id) return result.id;
  return "Untitled result";
}
