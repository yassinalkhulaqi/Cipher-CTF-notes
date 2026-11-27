/** Typed v4 API client for the professional block editor. */

import { V4ApiError, V4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";
import type { EditPayload, ProDocument, SnapshotMeta } from "./state";

export interface DocumentResult {
  document: ProDocument;
  checksum: string;
  word_count: number;
  revision: number;
  not_modified: boolean;
}

export interface MutationResult {
  document: ProDocument;
  revision: number;
  checksum: string;
  created?: boolean;
}

export interface PatchResult extends MutationResult {
  applied: EditPayload[];
  summary: Record<string, number>;
}

export interface HistoryResult {
  items: unknown[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface SnapshotResult {
  snapshots: SnapshotMeta[];
  count: number;
  document_id: string;
}

export interface BlockEditorClientOptions {
  client?: V4Client;
}

export class BlockEditorClient {
  private readonly client: V4Client;

  constructor(options: BlockEditorClientOptions = {}) {
    this.client = options.client ?? new V4Client();
  }

  async getDocument(
    id: string,
    etag = "",
  ): Promise<{ data: DocumentResult; meta: PageMetaV4 }> {
    const path = `/blocks?id=${encodeURIComponent(id)}`;
    return this.client.get<DocumentResult>(path, etag ? { etag } : {});
  }

  async listDocuments(
    page = 1,
    pageSize = 25,
    query = "",
  ): Promise<{ items: ProDocument[]; total: number; meta: PageMetaV4 }> {
    const suffix = query ? `&query=${encodeURIComponent(query)}` : "";
    const response = await this.client.get<{
      items: ProDocument[];
      total: number;
    }>(`/blocks?page=${page}&page_size=${pageSize}${suffix}`);
    return {
      items: response.data.items,
      total: response.data.total,
      meta: response.meta,
    };
  }

  async putDocument(
    document: ProDocument,
    expectedChecksum = "",
  ): Promise<MutationResult> {
    return this.client.put<MutationResult>("/blocks/document", {
      document,
      ...(expectedChecksum ? { expected_checksum: expectedChecksum } : {}),
    });
  }

  async patchDocument(
    id: string,
    operations: EditPayload[],
    expectedChecksum = "",
  ): Promise<PatchResult> {
    return this.client.patch<PatchResult>("/blocks/patch", {
      id,
      operations,
      ...(expectedChecksum ? { expected_checksum: expectedChecksum } : {}),
    });
  }

  async history(
    id: string,
    page = 1,
    pageSize = 25,
  ): Promise<{ data: HistoryResult; meta: PageMetaV4 }> {
    const path = `/blocks/history?id=${encodeURIComponent(id)}&page=${page}&page_size=${pageSize}`;
    return this.client.get<HistoryResult>(path);
  }

  async snapshots(id: string): Promise<SnapshotResult> {
    return this.client
      .get<SnapshotResult>(`/blocks/snapshots?id=${encodeURIComponent(id)}`)
      .then((response) => response.data);
  }

  async createSnapshot(id: string, reason: string): Promise<SnapshotResult> {
    return this.client.mutate<SnapshotResult>("/blocks/snapshots", "PATCH", {
      id,
      action: "create",
      reason,
    });
  }

  async restoreSnapshot(
    id: string,
    snapshotId: string,
    expectedChecksum = "",
  ): Promise<MutationResult> {
    return this.client.mutate<MutationResult>("/blocks/snapshots", "PATCH", {
      id,
      action: "restore",
      snapshot_id: snapshotId,
      ...(expectedChecksum ? { expected_checksum: expectedChecksum } : {}),
    });
  }
}

export { V4ApiError };
export const blockEditorClient = new BlockEditorClient();
