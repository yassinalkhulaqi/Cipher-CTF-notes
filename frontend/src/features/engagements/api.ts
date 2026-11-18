import { V2Client, requestId, type CallOptions } from "../../lib/apiClient";
import type {
  Activity,
  Asset,
  CoverageReport,
  Credential,
  DashboardPayload,
  EngagementSummary,
  Finding,
  ListResponse,
  PageMeta,
  PortfolioPayload,
  ScopeEvaluation,
  ScopeRule,
  Service,
  Target,
  Workflow,
} from "./types";

export interface EngagementApiOptions {
  client?: V2Client;
  basePath?: string;
}

export class EngagementApi {
  private readonly client: V2Client;
  private sequence = 0;

  constructor(options: EngagementApiOptions = {}) {
    this.client =
      options.client ?? new V2Client({ basePath: options.basePath });
  }

  private mutationKey(route: string): string {
    this.sequence += 1;
    return `eng-${route.replace(/[^a-z0-9]+/gi, "-")}-${Date.now().toString(36)}-${this.sequence}`;
  }

  private mutate<T>(route: string, body: Record<string, unknown>): Promise<T> {
    const options: CallOptions = {
      idempotencyKey: this.mutationKey(route),
      requestId: requestId("eng"),
    };
    return this.client.call<T>(route, body, options);
  }

  private async list<T>(
    route: string,
    body: Record<string, unknown>,
  ): Promise<ListResponse<T>> {
    const options: CallOptions = { raw: true };
    const raw = await this.client.call<{
      data: unknown;
      meta: PageMeta | null;
    }>(route, body, options);
    const data = raw.data;
    const items = Array.isArray(data)
      ? (data as T[])
      : data &&
          typeof data === "object" &&
          "items" in data &&
          Array.isArray(data.items)
        ? (data.items as T[])
        : [];
    const meta = raw.meta ?? {};
    const page: PageMeta = {
      cursor: meta.cursor ?? null,
      next: meta.next ?? null,
      total: meta.total ?? items.length,
      limit: meta.limit ?? items.length,
      has_more: meta.has_more ?? false,
    };
    return { items, page };
  }

  listEngagements(
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<EngagementSummary>> {
    return this.list<EngagementSummary>("engagements.list", query);
  }

  getEngagement(id: number): Promise<EngagementSummary> {
    return this.client.call<EngagementSummary>("engagements.get", { id });
  }

  createEngagement(data: Record<string, unknown>): Promise<EngagementSummary> {
    return this.mutate<EngagementSummary>("engagements.create", data);
  }

  updateEngagement(
    id: number,
    data: Record<string, unknown>,
  ): Promise<EngagementSummary> {
    return this.mutate<EngagementSummary>("engagements.update", {
      id,
      ...data,
    });
  }

  transitionEngagement(
    id: number,
    action: string,
    data: Record<string, unknown> = {},
  ): Promise<EngagementSummary> {
    return this.mutate<EngagementSummary>("engagements.transition", {
      id,
      action,
      ...data,
    });
  }

  deleteEngagement(id: number): Promise<{ id: number; deleted: boolean }> {
    return this.mutate("engagements.delete", { id });
  }

  dashboard(id: number): Promise<DashboardPayload> {
    return this.client.call<DashboardPayload>("engagements.dashboard", { id });
  }

  portfolio(): Promise<PortfolioPayload> {
    return this.client.call<PortfolioPayload>("engagements.portfolio", {});
  }

  workflows(): Promise<{ workflows: Workflow[] }> {
    return this.client.call("engagements.workflows", {});
  }

  options(): Promise<Record<string, string[]>> {
    return this.client.call("engagements.options", {});
  }

  activity(id: number, limit = 50): Promise<ListResponse<Activity>> {
    return this.list<Activity>("engagements.activity", { id, limit });
  }

  seedDemo(): Promise<{
    created: boolean;
    engagement: EngagementSummary | null;
  }> {
    return this.mutate("engagements.seed_demo", {});
  }

  listScopeRules(engagementId: number): Promise<ListResponse<ScopeRule>> {
    return this.list<ScopeRule>("scope.list", { engagement_id: engagementId });
  }

  addScopeRule(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<ScopeRule> {
    return this.mutate<ScopeRule>("scope.add", {
      engagement_id: engagementId,
      ...data,
    });
  }

  removeScopeRule(engagementId: number, id: number): Promise<ScopeRule> {
    return this.mutate<ScopeRule>("scope.remove", {
      engagement_id: engagementId,
      id,
    });
  }

  evaluateScope(engagementId: number, value: string): Promise<ScopeEvaluation> {
    return this.client.call<ScopeEvaluation>("scope.evaluate", {
      engagement_id: engagementId,
      value,
    });
  }

  listTargets(
    engagementId: number,
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<Target>> {
    return this.list<Target>("targets.list", {
      engagement_id: engagementId,
      ...query,
    });
  }

  getTarget(id: number): Promise<Target> {
    return this.client.call<Target>("targets.get", { id });
  }

  createTarget(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<Target> {
    return this.mutate<Target>("targets.create", {
      engagement_id: engagementId,
      ...data,
    });
  }

  updateTarget(id: number, data: Record<string, unknown>): Promise<Target> {
    return this.mutate<Target>("targets.update", { id, ...data });
  }

  transitionTarget(id: number, action: string, reason = ""): Promise<Target> {
    return this.mutate<Target>("targets.transition", { id, action, reason });
  }

  transitionTargetScope(id: number, action: string): Promise<Target> {
    return this.mutate<Target>("targets.scope_transition", { id, action });
  }

  removeTarget(id: number): Promise<Target> {
    return this.mutate<Target>("targets.remove", { id });
  }

  coverage(engagementId: number): Promise<CoverageReport> {
    return this.client.call<CoverageReport>("targets.coverage", {
      engagement_id: engagementId,
    });
  }

  listAssets(
    engagementId: number,
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<Asset>> {
    return this.list<Asset>("assets.list", {
      engagement_id: engagementId,
      ...query,
    });
  }

  createAsset(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<Asset> {
    return this.mutate<Asset>("assets.create", {
      engagement_id: engagementId,
      ...data,
    });
  }

  updateAsset(id: number, data: Record<string, unknown>): Promise<Asset> {
    return this.mutate<Asset>("assets.update", { id, ...data });
  }

  removeAsset(id: number): Promise<Asset> {
    return this.mutate<Asset>("assets.remove", { id });
  }

  listServices(
    engagementId: number,
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<Service>> {
    return this.list<Service>("services.list", {
      engagement_id: engagementId,
      ...query,
    });
  }

  createService(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<Service> {
    return this.mutate<Service>("services.create", {
      engagement_id: engagementId,
      ...data,
    });
  }

  updateService(id: number, data: Record<string, unknown>): Promise<Service> {
    return this.mutate<Service>("services.update", { id, ...data });
  }

  removeService(id: number): Promise<Service> {
    return this.mutate<Service>("services.remove", { id });
  }

  listCredentials(
    engagementId: number,
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<Credential>> {
    return this.list<Credential>("credentials.list", {
      engagement_id: engagementId,
      ...query,
    });
  }

  createCredential(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<Credential> {
    return this.mutate<Credential>("credentials.create", {
      engagement_id: engagementId,
      ...data,
    });
  }

  updateCredential(
    id: number,
    data: Record<string, unknown>,
  ): Promise<Credential> {
    return this.mutate<Credential>("credentials.update", { id, ...data });
  }

  rotateCredential(id: number, secretRef = ""): Promise<Credential> {
    return this.mutate<Credential>("credentials.rotate", {
      id,
      secret_ref: secretRef,
    });
  }

  removeCredential(id: number): Promise<Credential> {
    return this.mutate<Credential>("credentials.remove", { id });
  }

  listFindings(
    engagementId: number,
    query: Record<string, unknown> = {},
  ): Promise<ListResponse<Finding>> {
    return this.list<Finding>("findings.list", {
      engagement_id: engagementId,
      ...query,
    });
  }

  getFinding(id: number): Promise<Finding> {
    return this.client.call<Finding>("findings.get", { id });
  }

  createFinding(
    engagementId: number,
    data: Record<string, unknown>,
  ): Promise<Finding> {
    return this.mutate<Finding>("findings.create", {
      engagement_id: engagementId,
      ...data,
    });
  }

  updateFinding(id: number, data: Record<string, unknown>): Promise<Finding> {
    return this.mutate<Finding>("findings.update", { id, ...data });
  }

  transitionFinding(
    id: number,
    action: string,
    data: Record<string, unknown> = {},
  ): Promise<Finding> {
    return this.mutate<Finding>("findings.transition", { id, action, ...data });
  }

  markDuplicate(id: number, canonicalId: number): Promise<Finding> {
    return this.mutate<Finding>("findings.duplicate", {
      id,
      canonical_id: canonicalId,
    });
  }

  removeFinding(id: number): Promise<Finding> {
    return this.mutate<Finding>("findings.remove", { id });
  }
}
