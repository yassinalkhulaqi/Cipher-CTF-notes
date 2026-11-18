import { V2Client } from "../../lib/apiClient";
import type {
  GraphFilterState,
  GraphLayoutPayload,
  GraphLinkDetail,
  GraphMetrics,
  GraphNode,
  GraphOverview,
  GraphPathPayload,
  GraphRecommendation,
  GraphSnapshotMeta,
} from "./types";

interface PageEnvelope<T> {
  items: T[];
  page: Record<string, unknown>;
}

interface CountEnvelope<T> {
  count: number;
  items: T[];
}

function filterBody(
  filters: Partial<GraphFilterState> = {},
): Record<string, unknown> {
  return {
    kinds: filters.kinds ?? [],
    tags: filters.tags ?? [],
    statuses: filters.statuses ?? [],
    query: filters.query ?? "",
    max_nodes: filters.maxNodes ?? 0,
  };
}

export class GraphApiClient {
  readonly client: V2Client;

  constructor(client: V2Client = new V2Client()) {
    this.client = client;
  }

  async overview(refresh = false): Promise<GraphOverview> {
    return this.client.call<GraphOverview>("graph.overview", { refresh });
  }

  async nodes(
    filters: Partial<GraphFilterState> = {},
    limit = 200,
  ): Promise<GraphNode[]> {
    const response = await this.client.call<PageEnvelope<GraphNode>>(
      "graph.nodes",
      {
        ...filterBody(filters),
        limit,
      },
    );
    return response.items;
  }

  async edges(
    filters: Partial<GraphFilterState> = {},
    limit = 500,
  ): Promise<GraphLayoutPayload["edges"]> {
    const response = await this.client.call<
      PageEnvelope<GraphLayoutPayload["edges"][number]>
    >("graph.edges", { ...filterBody(filters), limit });
    return response.items;
  }

  async layout(
    filters: Partial<GraphFilterState> = {},
  ): Promise<GraphLayoutPayload> {
    return this.client.call<GraphLayoutPayload>(
      "graph.layout",
      filterBody(filters),
    );
  }

  async metrics(): Promise<GraphMetrics> {
    const overview = await this.overview();
    return overview.metrics;
  }

  async path(
    source: number | string,
    target: number | string,
    options: { weighted?: boolean; directed?: boolean; maxHops?: number } = {},
  ): Promise<GraphPathPayload> {
    return this.client.call<GraphPathPayload>("graph.path", {
      source,
      target,
      weighted: options.weighted ?? false,
      directed: options.directed ?? false,
      max_hops: options.maxHops,
    });
  }

  async neighbors(id: number, depth = 1): Promise<GraphLayoutPayload> {
    return this.client.call<GraphLayoutPayload>("graph.neighbors", {
      id,
      depth,
    });
  }

  async backlinks(id: number): Promise<GraphLinkDetail["backlinks"]> {
    const response = await this.client.call<{
      backlinks: GraphLinkDetail["backlinks"];
    }>("graph.backlinks", { id });
    return response.backlinks;
  }

  async outlinks(id: number): Promise<GraphLinkDetail> {
    return this.client.call<GraphLinkDetail>("graph.outlinks", { id });
  }

  async centrality(
    measure = "degree",
    limit = 20,
  ): Promise<Array<Record<string, unknown>>> {
    const response = await this.client.call<{
      items: Array<Record<string, unknown>>;
    }>("graph.centrality", { measure, limit });
    return response.items;
  }

  async components(minSize = 2): Promise<Array<Record<string, unknown>>> {
    const response = await this.client.call<
      CountEnvelope<Record<string, unknown>>
    >("graph.components", { min_size: minSize });
    return response.items;
  }

  async communities(): Promise<Array<Record<string, unknown>>> {
    const response = await this.client.call<
      CountEnvelope<Record<string, unknown>>
    >("graph.communities", {});
    return response.items;
  }

  async cycles(limit = 25): Promise<Array<Record<string, unknown>>> {
    const response = await this.client.call<
      CountEnvelope<Record<string, unknown>>
    >("graph.cycles", { limit });
    return response.items;
  }

  async recommendations(limit = 10): Promise<GraphRecommendation[]> {
    const response = await this.client.call<{
      missing_links: GraphRecommendation[];
      popular: GraphRecommendation[];
    }>("graph.recommend", { limit });
    return [...response.missing_links, ...response.popular];
  }

  async related(id: number, limit = 10): Promise<GraphRecommendation[]> {
    const response = await this.client.call<{ items: GraphRecommendation[] }>(
      "graph.related",
      {
        id,
        limit,
      },
    );
    return response.items;
  }

  async insights(limit = 10): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>("graph.insights", {
      limit,
    });
  }

  async capture(label = ""): Promise<GraphSnapshotMeta> {
    const response = await this.client.call<{ meta: GraphSnapshotMeta }>(
      "graph.snapshot.create",
      {
        label,
      },
    );
    return response.meta;
  }

  async snapshots(limit = 20): Promise<GraphSnapshotMeta[]> {
    const response = await this.client.call<{ snapshots: GraphSnapshotMeta[] }>(
      "graph.snapshot.list",
      { limit },
    );
    return response.snapshots;
  }

  async resolve(label: string): Promise<number> {
    const response = await this.client.call<{ id: number }>("graph.resolve", {
      label,
    });
    return response.id;
  }
}
