/** Typed client for the V3 sync/portability namespace. */

import { V3Client } from "../../v3/apiClient";
import type {
  BundlePlan,
  ConflictView,
  DryRunView,
  ProgressView,
  ReceiptView,
  VectorView,
} from "./types";

export interface PortabilityRequestOptions {
  signal?: AbortSignal;
  etag?: string;
}

export function compact(
  value: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (item === undefined || item === null || item === "") continue;
    result[key] = item;
  }
  return result;
}

export function bundleCreateRequest(
  plan: BundlePlan,
  entities: unknown[],
  links: unknown[] = [],
): Record<string, unknown> {
  return compact({
    label: plan.label,
    device_id: plan.deviceId,
    passphrase: plan.passphrase,
    entities,
    links,
    include_deleted: plan.includeDeleted,
    include_links: plan.includeLinks,
    dry_run: plan.dryRun,
    families: plan.scope,
  });
}

export function bundleVerifyRequest(
  bundleId: string,
  passphrase: string,
): Record<string, unknown> {
  return compact({ bundle_id: bundleId, passphrase });
}

export function previewRequest(
  bundleId: string,
  passphrase: string,
  base: unknown[],
  local: unknown[],
  families: string[] = [],
): Record<string, unknown> {
  return compact({
    bundle_id: bundleId,
    passphrase,
    base,
    local,
    families,
  });
}

export function resolveRequest(
  previewId: string,
  decisions: Record<string, string>,
  actor = "local",
  device = "local",
): Record<string, unknown> {
  return compact({
    preview_id: previewId,
    decisions,
    actor,
    device,
  });
}

export function transferChunkRequest(
  transferId: string,
  index: number,
  chunk: string,
): Record<string, unknown> {
  return compact({ transfer_id: transferId, index, chunk });
}

export function transferStartRequest(
  bundleId: string,
  chunkSize: number,
): Record<string, unknown> {
  return compact({ bundle_id: bundleId, chunk_size: chunkSize });
}

export class PortabilityClient {
  private async request<T>(
    namespace: string,
    action: string,
    body: Record<string, unknown>,
    options: PortabilityRequestOptions,
  ): Promise<T> {
    const envelope = await this.client.call<T>(
      namespace,
      action,
      body,
      options,
    );
    return envelope.data;
  }

  constructor(private readonly client: V3Client) {}

  health(
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("sync", "health", {}, options);
  }

  reasons(options: PortabilityRequestOptions = {}): Promise<{
    reasons: Array<{ code: string; description: string; severity: string }>;
    strategies: string[];
  }> {
    return this.request("sync", "reasons", {}, options);
  }

  devices(
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      "sync",
      "devices",
      {},
      options,
    );
  }

  registerDevice(
    deviceId: string,
    label: string,
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "device.register",
      { device_id: deviceId, label },
      options,
    );
  }

  trustDevice(
    deviceId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "device.trust",
      { device_id: deviceId },
      options,
    );
  }

  compareVectors(
    local: Record<string, number>,
    remote: Record<string, number>,
    options: PortabilityRequestOptions = {},
  ): Promise<VectorView> {
    return this.request<VectorView>(
      "sync",
      "vectors.compare",
      { local, remote },
      options,
    );
  }

  planBundle(
    entities: unknown[],
    links: unknown[] = [],
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request("sync", "bundle.plan", { entities, links }, options);
  }

  createBundle(
    plan: BundlePlan,
    entities: unknown[],
    links: unknown[] = [],
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "bundle.create",
      bundleCreateRequest(plan, entities, links),
      options,
    );
  }

  inspectBundle(
    bundleId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "bundle.inspect",
      { bundle_id: bundleId },
      options,
    );
  }

  openBundle(
    bundleId: string,
    passphrase: string,
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "bundle.open",
      bundleVerifyRequest(bundleId, passphrase),
      options,
    );
  }

  verifyBundle(
    bundleId: string,
    passphrase: string,
    options: PortabilityRequestOptions = {},
  ): Promise<{ receipt: ReceiptView; verification: { ok: boolean } }> {
    return this.request(
      "sync",
      "bundle.verify",
      bundleVerifyRequest(bundleId, passphrase),
      options,
    );
  }

  detectConflicts(
    payload: Record<string, unknown>,
    options: PortabilityRequestOptions = {},
  ): Promise<{ count: number; conflicts: ConflictView[] }> {
    return this.request("sync", "conflicts.detect", payload, options);
  }

  previewImport(
    bundleId: string,
    passphrase: string,
    base: unknown[],
    local: unknown[],
    families: string[] = [],
    options: PortabilityRequestOptions = {},
  ): Promise<DryRunView & { preview_id: string }> {
    return this.request(
      "sync",
      "merge.preview",
      previewRequest(bundleId, passphrase, base, local, families),
      options,
    );
  }

  resolveConflicts(
    previewId: string,
    decisions: Record<string, string>,
    actor?: string,
    device?: string,
    options: PortabilityRequestOptions = {},
  ): Promise<{
    merge: { conflicts: ConflictView[] };
    receipt: ReceiptView;
    ledger_intact: boolean;
  }> {
    return this.request(
      "sync",
      "conflicts.resolve",
      resolveRequest(previewId, decisions, actor, device),
      options,
    );
  }

  receipt(
    receiptId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<ReceiptView> {
    return this.request(
      "sync",
      "receipt.get",
      { receipt_id: receiptId },
      options,
    );
  }

  receipts(
    options: PortabilityRequestOptions = {},
  ): Promise<{ count: number; receipts: ReceiptView[] }> {
    return this.request("sync", "receipt.list", {}, options);
  }

  audit(
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request("sync", "audit.list", {}, options);
  }

  beginTransfer(
    bundleId: string,
    chunkSize = 64 * 1024,
    options: PortabilityRequestOptions = {},
  ): Promise<ProgressView> {
    return this.request(
      "sync",
      "transfer.start",
      transferStartRequest(bundleId, chunkSize),
      options,
    );
  }

  pushChunk(
    transferId: string,
    index: number,
    chunk: string,
    options: PortabilityRequestOptions = {},
  ): Promise<ProgressView> {
    return this.request(
      "sync",
      "transfer.chunk",
      transferChunkRequest(transferId, index, chunk),
      options,
    );
  }

  pauseTransfer(
    transferId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<ProgressView> {
    return this.request(
      "sync",
      "transfer.pause",
      { transfer_id: transferId },
      options,
    );
  }

  resumeTransfer(
    transferId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<ProgressView> {
    return this.request(
      "sync",
      "transfer.resume",
      { transfer_id: transferId },
      options,
    );
  }

  cancelTransfer(
    transferId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<ProgressView> {
    return this.request(
      "sync",
      "transfer.cancel",
      { transfer_id: transferId },
      options,
    );
  }

  finishTransfer(
    transferId: string,
    options: PortabilityRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.request(
      "sync",
      "transfer.finish",
      { transfer_id: transferId },
      options,
    );
  }
}

export function createPortabilityClient(
  fetchImpl?: typeof globalThis.fetch,
): PortabilityClient {
  return new PortabilityClient(new V3Client({ fetch: fetchImpl }));
}
