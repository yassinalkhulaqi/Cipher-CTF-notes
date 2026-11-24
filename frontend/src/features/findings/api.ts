/** Typed V3 API wrapper for the finding studio. */

import { V3Client } from "../../v3/apiClient";
import type {
  CweEntry,
  FindingDetail,
  FindingList,
  FindingWire,
  ScorePreview,
  StudioSummary,
} from "./types";

export interface FindingsListQuery {
  query?: string;
  state?: string;
  severity?: string;
  owner?: string;
  tag?: string;
  size?: number;
  offset?: number;
  cursor?: string;
  hasThreat?: boolean;
}

export class FindingsApi {
  constructor(private readonly client: V3Client = new V3Client()) {}

  async list(query: FindingsListQuery = {}): Promise<FindingList> {
    const body: Record<string, unknown> = {
      query: query.query ?? "",
      state: query.state ?? "",
      severity: query.severity ?? "",
      owner: query.owner ?? "",
      tag: query.tag ?? "",
      size: query.size ?? 50,
    };
    if (query.cursor) body.cursor = query.cursor;
    else if (query.offset !== undefined) body.offset = query.offset;
    if (query.hasThreat !== undefined) body.has_threat = query.hasThreat;
    return this.client.data<FindingList>("findings", "list", body);
  }

  async create(values: {
    title: string;
    summary?: string;
    vector?: string;
    owner?: string;
    cwes?: string[];
    cves?: string[];
    tags?: string[];
    targetRef?: string;
  }): Promise<FindingWire> {
    const data = await this.client.data<{ finding: FindingWire }>("findings", "create", {
      title: values.title,
      summary: values.summary ?? "",
      vector: values.vector ?? "",
      owner: values.owner ?? "",
      cwes: values.cwes ?? [],
      cves: values.cves ?? [],
      tags: values.tags ?? [],
      target_ref: values.targetRef ?? "",
    });
    return data.finding;
  }

  async detail(ref: string): Promise<FindingDetail> {
    return this.client.data<FindingDetail>("findings", "detail", { ref });
  }

  async preview(vector: string): Promise<ScorePreview> {
    return this.client.data<ScorePreview>("findings", "score_preview", { vector });
  }

  async setScore(ref: string, vector: string): Promise<FindingDetail> {
    await this.client.data("findings", "score", { ref, vector });
    return this.detail(ref);
  }

  async transition(ref: string, action: string, note = ""): Promise<FindingDetail> {
    await this.client.data("findings", "transition", { ref, action, note });
    return this.detail(ref);
  }

  async addRemediation(ref: string, lines: string): Promise<FindingDetail> {
    await this.client.data("findings", "remediation_add", { ref, lines });
    return this.detail(ref);
  }

  async updateTask(ref: string, taskId: string, status: string): Promise<FindingDetail> {
    await this.client.data("findings", "remediation_update", { ref, task_id: taskId, status });
    return this.detail(ref);
  }

  async retest(
    ref: string,
    verdict: string,
    testedBy: string,
    notes = "",
    proofRefs: string[] = [],
  ): Promise<FindingDetail> {
    await this.client.data("findings", "retest", {
      ref,
      verdict,
      tested_by: testedBy,
      notes,
      proof_refs: proofRefs,
    });
    return this.detail(ref);
  }

  async addProof(
    ref: string,
    blockId: string,
    target: string,
    excerpt: string,
    role = "supporting",
  ): Promise<FindingDetail> {
    await this.client.data("findings", "proof_add", {
      ref,
      block_id: blockId,
      target,
      excerpt,
      role,
    });
    return this.detail(ref);
  }

  async markDuplicate(ref: string, canonical: string, note = ""): Promise<FindingDetail> {
    await this.client.data("findings", "mark_duplicate", { ref, canonical, note });
    return this.detail(ref);
  }

  async duplicates(ref: string, threshold = 0.62): Promise<FindingDetail> {
    await this.client.data("findings", "duplicates", { ref, threshold });
    return this.detail(ref);
  }

  async cweCatalog(query = ""): Promise<CweEntry[]> {
    const data = await this.client.data<{ entries: CweEntry[] }>("findings", "cwe_catalog", {
      query,
    });
    return data.entries;
  }

  async summary(): Promise<StudioSummary> {
    return this.client.data<StudioSummary>("findings", "summary", {});
  }
}
