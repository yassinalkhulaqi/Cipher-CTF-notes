/** Typed V3 client wrapper for every graph workbench action. */

import { V3Client } from "../../v3/apiClient";
import type {
  ArticulationResult,
  ClusterResult,
  EditRecord,
  GraphPayload,
  LayoutResult,
  PathResult,
  RelationshipDraft,
  SnapshotMeta,
  SnapshotRecord,
  SnapshotDiff,
} from "./types";
import { draftToBody } from "./editor";

export interface GraphWorkbenchClientOptions {
  client?: V3Client;
  basePath?: string;
  fetch?: typeof globalThis.fetch;
}

export interface OverviewResult {
  stats: Record<string, number>;
  structure: ArticulationResult["summary"];
  tags: Record<string, number>;
  layouts: string[];
  clusters: string[];
  snapshots: number;
  history: Record<string, unknown>;
}

export class GraphWorkbenchClient {
  readonly client: V3Client;

  constructor(options: GraphWorkbenchClientOptions = {}) {
    this.client =
      options.client ??
      new V3Client({ basePath: options.basePath, fetch: options.fetch });
  }

  private async action<T>(
    name: string,
    body: Record<string, unknown> = {},
  ): Promise<T> {
    return this.client.data<T>("graph", name, body);
  }

  overview(): Promise<OverviewResult> {
    return this.action<OverviewResult>("overview");
  }

  graph(filters: Record<string, unknown> = {}): Promise<GraphPayload> {
    return this.action<GraphPayload>("graph", filters);
  }

  entities(
    query = "",
  ): Promise<Array<{ ref: string; label: string; kind: string }>> {
    return this.action<Array<{ ref: string; label: string; kind: string }>>(
      "entities",
      {
        query,
      },
    );
  }

  layout(
    strategy: string,
    options: Record<string, unknown> = {},
  ): Promise<LayoutResult> {
    return this.action<LayoutResult>("layout", { strategy, options });
  }

  clusters(dimension: string, tagPrefix = ""): Promise<ClusterResult> {
    return this.action<ClusterResult>("clusters", {
      dimension,
      tag_prefix: tagPrefix,
    });
  }

  path(
    source: string,
    target: string,
    options: { directed?: boolean; weighted?: boolean; maxHops?: number } = {},
  ): Promise<PathResult> {
    return this.action<PathResult>("path", { source, target, ...options });
  }

  articulation(): Promise<ArticulationResult> {
    return this.action<ArticulationResult>("articulation");
  }

  inspect(id: string): Promise<Record<string, unknown>> {
    return this.action<Record<string, unknown>>("inspect", { node: id });
  }

  connect(draft: RelationshipDraft): Promise<EditRecord> {
    return this.action<EditRecord>("connect", draftToBody(draft));
  }

  disconnect(draft: RelationshipDraft): Promise<EditRecord> {
    return this.action<EditRecord>("disconnect", draftToBody(draft));
  }

  update(draft: RelationshipDraft): Promise<EditRecord> {
    return this.action<EditRecord>("update-relationship", draftToBody(draft));
  }

  undo(): Promise<{ applied: boolean; record: EditRecord | null }> {
    return this.action("undo");
  }

  redo(): Promise<{ applied: boolean; record: EditRecord | null }> {
    return this.action("redo");
  }

  capture(label = ""): Promise<SnapshotRecord> {
    return this.action<SnapshotRecord>("snapshot", { label });
  }

  snapshots(limit = 20): Promise<{
    count: number;
    snapshots: SnapshotMeta[];
    latestId: string | null;
  }> {
    return this.action("snapshots", { limit });
  }

  diff(left: string, right: string): Promise<SnapshotDiff> {
    return this.action<SnapshotDiff>("diff", { left, right });
  }

  exportGraph(
    format: "json" | "dot" | "mermaid",
    direction = "LR",
  ): Promise<{ content: string; format: string; mime: string }> {
    return this.action("export", { format, direction });
  }
}
