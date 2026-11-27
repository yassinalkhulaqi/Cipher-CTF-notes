import { V4ApiError, V4Client } from "../../v4-kernel/client";
import type { PageMetaV4 } from "../../v4-kernel/types-v4";

export { V4ApiError };

export interface GraphNodeDto {
  id: string;
  kind: string;
  label: string;
  weight: number;
}

export interface GraphEdgeDto {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface GraphFilterDto {
  kinds: string[];
  relations: string[];
  min_weight: number;
  label_contains: string;
}

export interface GraphLegendDto {
  relation: string;
  count: number;
  average_weight: number;
}

export interface GraphOverviewDto {
  node_count: number;
  edge_count: number;
  component_count: number;
  isolated_count: number;
  density: number;
  hidden_nodes: number;
  hidden_edges: number;
  legend: GraphLegendDto[];
  filter: GraphFilterDto;
}

export interface GraphMetricsDto {
  node_count: number;
  edge_count: number;
  degree: Record<string, number>;
  component_count: number;
  isolated_count: number;
  max_degree: number;
  average_degree: number;
  density: number;
}

export interface GraphPointDto {
  node_id: string;
  x: number;
  y: number;
}

export interface GraphLayoutDto {
  kind: string;
  width: number;
  height: number;
  points: GraphPointDto[];
  seed: number;
  iterations: number;
}

export interface GraphPathDto {
  source: string;
  target: string;
  path: string[];
  hops: number;
  found: boolean;
}

export interface GraphPageDto<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface GraphSnapshotDto {
  name: string;
  data: { nodes: GraphNodeDto[]; edges: GraphEdgeDto[] };
  filter: GraphFilterDto;
  layout: string;
  created_at: string;
  tags: string[];
}

export interface GraphEnvelope<T> {
  data: T;
  meta: PageMetaV4;
}

export interface GraphQuery {
  page?: number;
  pageSize?: number;
  kinds?: string[];
  relations?: string[];
  minWeight?: number;
  labelContains?: string;
  layout?: string;
  seed?: number;
  width?: number;
  height?: number;
  iterations?: number;
  source?: string;
  target?: string;
  name?: string;
}

const PARAM_KEYS: Record<keyof GraphQuery, string> = {
  page: "page",
  pageSize: "page_size",
  kinds: "kinds",
  relations: "relations",
  minWeight: "min_weight",
  labelContains: "label_contains",
  layout: "layout",
  seed: "seed",
  width: "width",
  height: "height",
  iterations: "iterations",
  source: "source",
  target: "target",
  name: "name",
};

export function graphQueryString(query: GraphQuery = {}): string {
  const params = new URLSearchParams();
  const keys = Object.keys(PARAM_KEYS) as (keyof GraphQuery)[];
  for (const key of keys.sort()) {
    const value = query[key];
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      params.set(PARAM_KEYS[key], value.join(","));
    } else if (typeof value === "number") {
      if (!Number.isFinite(value) || value === 0) continue;
      params.set(PARAM_KEYS[key], String(value));
    } else {
      params.set(PARAM_KEYS[key], value);
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export class GraphWorkbenchClient {
  constructor(private readonly client: V4Client = new V4Client("/api/v4")) {}

  private async get<T>(
    path: string,
    query: GraphQuery = {},
  ): Promise<GraphEnvelope<T>> {
    const result = await this.client.get<T>(
      `${path}${graphQueryString(query)}`,
    );
    return { data: result.data, meta: result.meta };
  }

  overview(query: GraphQuery = {}): Promise<GraphEnvelope<GraphOverviewDto>> {
    return this.get<GraphOverviewDto>("/graph", query);
  }

  nodes(
    query: GraphQuery = {},
  ): Promise<GraphEnvelope<GraphPageDto<GraphNodeDto>>> {
    return this.get<GraphPageDto<GraphNodeDto>>("/graph/nodes", query);
  }

  edges(
    query: GraphQuery = {},
  ): Promise<GraphEnvelope<GraphPageDto<GraphEdgeDto>>> {
    return this.get<GraphPageDto<GraphEdgeDto>>("/graph/edges", query);
  }

  metrics(query: GraphQuery = {}): Promise<GraphEnvelope<GraphMetricsDto>> {
    return this.get<GraphMetricsDto>("/graph/metrics", query);
  }

  layout(query: GraphQuery = {}): Promise<GraphEnvelope<GraphLayoutDto>> {
    return this.get<GraphLayoutDto>("/graph/layout", query);
  }

  path(query: GraphQuery = {}): Promise<GraphEnvelope<GraphPathDto>> {
    return this.get<GraphPathDto>("/graph/path", query);
  }

  snapshots(
    query: GraphQuery = {},
  ): Promise<GraphEnvelope<GraphPageDto<string>>> {
    return this.get<GraphPageDto<string>>("/graph/snapshots", query);
  }

  snapshot(name: string): Promise<GraphEnvelope<GraphSnapshotDto>> {
    return this.get<GraphSnapshotDto>("/graph/snapshot", { name });
  }

  filters(
    query: GraphQuery = {},
  ): Promise<GraphEnvelope<Record<string, unknown>>> {
    return this.get<Record<string, unknown>>("/graph/filters", query);
  }
}

export const graphWorkbenchClient = new GraphWorkbenchClient();
