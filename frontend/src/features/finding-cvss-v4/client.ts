import { V4ApiError, V4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";

export type SeverityV4 = "none" | "low" | "medium" | "high" | "critical";

export type LifecycleStateV4 =
  | "draft"
  | "open"
  | "confirmed"
  | "remediating"
  | "retest"
  | "closed"
  | "accepted_risk";

export type RetestVerdictV4 = "pass" | "fail" | "partial";

export interface FindingV4 {
  id: string;
  title: string;
  description: string;
  vector: string;
  severity: SeverityV4;
  lifecycle_state: LifecycleStateV4;
  remediation_due: string | null;
  remediation_notes: string;
  retest_count: number;
  created_at: string;
}

export interface ScoreV4 {
  vector: string;
  base: number;
  threat: number;
  environmental: number;
  final: number;
  severity: SeverityV4;
  nomenclature: string;
}

export interface FindingListV4 {
  items: FindingV4[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface FindingSnapshotV4 {
  version: number;
  findings: FindingV4[];
  retests: Array<{ finding_id: string; sequence: number; verdict: string }>;
  indexes: { severity: Record<string, number>; state: Record<string, number> };
}

export interface FindingPageV4 {
  data: FindingListV4;
  meta: PageMetaV4;
}

export interface FindingListOptions {
  page?: number;
  pageSize?: number;
  severity?: SeverityV4;
  state?: LifecycleStateV4;
  etag?: string;
}

export interface CreateFindingInput {
  title: string;
  vector: string;
  description?: string;
}

export interface FindingMutationResult {
  finding: FindingV4;
  score?: ScoreV4;
  retest?: {
    finding_id: string;
    sequence: number;
    verdict: RetestVerdictV4;
    note: string;
    occurred_at: string;
    score: number;
  };
}

export class FindingClient {
  constructor(private readonly client: V4Client = new V4Client()) {}

  async list(options: FindingListOptions = {}): Promise<FindingPageV4> {
    const params = new URLSearchParams();
    if (options.severity) params.set("severity", options.severity);
    if (options.state) params.set("state", options.state);
    const query = params.toString();
    const path = query ? `/findings?${query}` : "/findings";
    return this.client.get<FindingListV4>(path, {
      page: options.page,
      pageSize: options.pageSize,
      etag: options.etag,
    });
  }

  async create(input: CreateFindingInput): Promise<FindingMutationResult> {
    return this.client.post<FindingMutationResult>("/findings", input);
  }

  async score(id: string): Promise<FindingMutationResult> {
    return this.mutate({ id, action: "score" });
  }

  async transition(
    id: string,
    state: LifecycleStateV4,
  ): Promise<FindingMutationResult> {
    return this.mutate({ id, action: "transition", state });
  }

  async assignRemediation(
    id: string,
    due: string,
    notes: string,
  ): Promise<FindingMutationResult> {
    return this.mutate({ id, action: "remediation", due, notes });
  }

  async retest(
    id: string,
    verdict: RetestVerdictV4,
    note: string,
  ): Promise<FindingMutationResult> {
    return this.mutate({ id, action: "retest", verdict, note });
  }

  async snapshot(): Promise<FindingSnapshotV4> {
    const page = await this.client.get<FindingSnapshotV4>(
      "/findings?view=snapshot",
    );
    return page.data;
  }

  private mutate(
    body: Record<string, unknown>,
  ): Promise<FindingMutationResult> {
    return this.client.put<FindingMutationResult>("/findings", body);
  }
}

export { V4ApiError };
