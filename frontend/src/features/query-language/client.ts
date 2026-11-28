import { V4ApiError, V4Client, v4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";

export type QueryField =
  | "title"
  | "body"
  | "tag"
  | "kind"
  | "status"
  | "flag"
  | "target"
  | "author";

export type QueryOperator =
  | "="
  | "!="
  | "contains"
  | "starts_with"
  | ">"
  | "<"
  | "in";

export type BooleanConnector = "AND" | "OR" | "NOT";

export interface QueryTokenView {
  field: QueryField;
  operator: QueryOperator;
  value: string;
  values: string[];
  boolean: BooleanConnector | null;
  negated: boolean;
  free_text: boolean;
  position: number;
}

export interface FacetValueView {
  value: string;
  count: number;
  selected: boolean;
}

export interface FacetView {
  field: QueryField;
  label: string;
  values: FacetValueView[];
}

export interface ClusterView {
  key: string;
  count: number;
  sample_ids: string[];
}

export interface ResultView {
  id?: string;
  title?: string;
  [key: string]: unknown;
}

export interface QueryHits {
  items: ResultView[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface SearchResponse {
  expression: string;
  normalized: string;
  token_count: number;
  hits: QueryHits;
  facets: FacetView[];
  clusters: ClusterView[];
  cluster_summary: Record<string, unknown>;
  warnings: string[];
  cursor_applied: boolean;
}

export interface SavedQueryView {
  id: string;
  name: string;
  expression: string;
  created_at: string;
}

export interface QuerySearchParams {
  expression: string;
  page?: number;
  pageSize?: number;
  facets?: QueryField[];
  clusterField?: QueryField;
  selectedFacets?: Record<string, string[]>;
  rank?: boolean;
  cursor?: string;
}

export interface QueryEnvelope<T> {
  data: T;
  meta: PageMetaV4;
}

export const QUERY_FIELDS: QueryField[] = [
  "title",
  "body",
  "tag",
  "kind",
  "status",
  "flag",
  "target",
  "author",
];

export const QUERY_OPERATORS: QueryOperator[] = [
  "=",
  "!=",
  "contains",
  "starts_with",
  ">",
  "<",
  "in",
];

export const FIELD_LABELS: Record<QueryField, string> = {
  title: "Title",
  body: "Body",
  tag: "Tag",
  kind: "Kind",
  status: "Status",
  flag: "Flag",
  target: "Target",
  author: "Author",
};

export const OPERATOR_LABELS: Record<QueryOperator, string> = {
  "=": "equals",
  "!=": "does not equal",
  contains: "contains",
  starts_with: "starts with",
  ">": "greater than",
  "<": "less than",
  in: "is one of",
};

export function buildSearchPath(params: QuerySearchParams): string {
  const search = new URLSearchParams();
  search.set("action", "search");
  search.set("expression", params.expression);
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined)
    search.set("page_size", String(params.pageSize));
  if (params.facets?.length) search.set("facets", params.facets.join(","));
  if (params.clusterField) search.set("cluster_field", params.clusterField);
  if (params.rank) search.set("rank", "true");
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.selectedFacets && Object.keys(params.selectedFacets).length > 0) {
    search.set("facet_selections", JSON.stringify(params.selectedFacets));
  }
  const query = search.toString();
  return query ? `/query?${query}` : "/query";
}

export class QueryLanguageClient {
  constructor(private readonly client: V4Client = v4Client) {}

  async search(
    params: QuerySearchParams,
  ): Promise<QueryEnvelope<SearchResponse>> {
    return this.client.get<SearchResponse>(buildSearchPath(params), {
      page: params.page,
      pageSize: params.pageSize,
    });
  }

  async listSaved(
    page = 1,
    pageSize = 50,
  ): Promise<QueryEnvelope<SavedQueryView[]>> {
    return this.client.get<SavedQueryView[]>("/query/saved", {
      page,
      pageSize,
    });
  }

  async save(name: string, expression: string): Promise<SavedQueryView> {
    return this.client.post<SavedQueryView>("/query/saved", {
      action: "save",
      name,
      expression,
    });
  }

  async rename(id: string, name: string): Promise<SavedQueryView> {
    return this.client.post<SavedQueryView>("/query/saved", {
      action: "rename",
      id,
      name,
    });
  }

  async remove(id: string): Promise<void> {
    await this.client.post("/query/saved", { action: "delete", id });
  }

  async exportSaved(): Promise<{ json: string; count: number }> {
    return this.client.post<{ json: string; count: number }>("/query/saved", {
      action: "export",
    });
  }
}

export { V4ApiError };
