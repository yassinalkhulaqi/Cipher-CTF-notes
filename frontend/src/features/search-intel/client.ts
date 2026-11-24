/** Typed V3 API client for the search namespace. */

import { V3Client } from "../../v3/apiClient";
import type {
  CompletionV2,
  FacetResultV2,
  ClusterGroupV2,
  ParsedQueryV2,
  PivotContextV2,
  QueryTemplateV2,
  SavedFacetSetV2,
  SavedSearchV2,
  SearchResponseV2,
} from "./types";

export interface SearchIntelRequest {
  query: string;
  fields?: string[];
  selected?: Record<string, string[]>;
  cluster_by?: string;
  cluster_field?: string;
  limit?: number;
  facet_limit?: number;
  pivot_limit?: number;
  now?: number;
}

export class SearchIntelClient {
  constructor(private readonly client: V3Client = new V3Client()) {}

  async parse(query: string): Promise<ParsedQueryV2> {
    const data = await this.client.data<{ parsed: ParsedQueryV2 }>(
      "search",
      "parse",
      {
        query,
      },
    );
    return data.parsed;
  }

  async search(request: SearchIntelRequest): Promise<SearchResponseV2> {
    return this.client.data<SearchResponseV2>("search", "search", {
      ...request,
    });
  }

  async facets(query: string, fields: string[]): Promise<FacetResultV2[]> {
    const data = await this.client.data<{ facets: FacetResultV2[] }>(
      "search",
      "facets",
      { query, fields },
    );
    return data.facets;
  }

  async clusters(query: string, strategy = "field"): Promise<ClusterGroupV2[]> {
    const data = await this.client.data<{ clusters: ClusterGroupV2[] }>(
      "search",
      "clusters",
      { query, strategy },
    );
    return data.clusters;
  }

  async pivots(ref: string, depth = 1): Promise<PivotContextV2> {
    const data = await this.client.data<{ context: PivotContextV2 }>(
      "search",
      "pivots",
      { ref, depth },
    );
    return data.context;
  }

  async autocomplete(text: string): Promise<CompletionV2[]> {
    const data = await this.client.data<{ completions: CompletionV2[] }>(
      "search",
      "autocomplete",
      { text },
    );
    return data.completions;
  }

  async templates(): Promise<QueryTemplateV2[]> {
    const data = await this.client.data<{ templates: QueryTemplateV2[] }>(
      "search",
      "templates",
      {},
    );
    return data.templates;
  }

  async renderTemplate(
    id: string,
    values: Record<string, string>,
  ): Promise<string> {
    const data = await this.client.data<{ query: string }>(
      "search",
      "template_render",
      { template_id: id, values },
    );
    return data.query;
  }

  async savedList(): Promise<SavedSearchV2[]> {
    const data = await this.client.data<{ items: SavedSearchV2[] }>(
      "search",
      "saved_list",
      {},
    );
    return data.items;
  }

  async savedCreate(draft: {
    name: string;
    query: string;
    description?: string;
    tags?: string[];
    pinned?: boolean;
  }): Promise<SavedSearchV2> {
    const data = await this.client.data<{ item: SavedSearchV2 }>(
      "search",
      "saved_create",
      { ...draft },
    );
    return data.item;
  }

  async savedUpdate(
    id: string,
    patch: Partial<
      Pick<SavedSearchV2, "name" | "query" | "description" | "tags" | "pinned">
    >,
  ): Promise<SavedSearchV2> {
    const data = await this.client.data<{ item: SavedSearchV2 }>(
      "search",
      "saved_update",
      { id, ...patch },
    );
    return data.item;
  }

  async savedDelete(id: string): Promise<void> {
    await this.client.data("search", "saved_delete", { id });
  }

  async facetSets(): Promise<SavedFacetSetV2[]> {
    const data = await this.client.data<{ items: SavedFacetSetV2[] }>(
      "search",
      "facet_sets_list",
      {},
    );
    return data.items;
  }

  async snapshot(): Promise<Record<string, unknown>> {
    const data = await this.client.data<{ snapshot: Record<string, unknown> }>(
      "search",
      "snapshot",
      {},
    );
    return data.snapshot;
  }
}

export function createSearchIntelClient(client?: V3Client): SearchIntelClient {
  return new SearchIntelClient(client);
}
