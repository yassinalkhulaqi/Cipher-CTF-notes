import { V2Client } from "../../lib/apiClient";
import type {
  CustodyView,
  EvidenceDetail,
  EvidenceManifest,
  EvidenceRecord,
  EvidenceStats,
  EvidenceSummary,
  EvidenceUpload,
  FindingLink,
  ImportPlan,
  IntegrityReport,
  LinksView,
  ManifestImportResult,
  ManifestPreview,
  RetentionDecision,
  RetentionPolicy,
  RetentionView,
} from "./types";

export interface EvidenceApiOptions {
  client?: V2Client;
  basePath?: string;
  timeout?: number;
}

export interface IngestOptions {
  title?: string;
  description?: string;
  tags?: string[];
  noteId?: number;
  mimeType?: string;
  actor?: string;
  operator?: string;
  sourcePath?: string;
  caseReference?: string;
  dedupe?: boolean;
}

export interface VerifyAllResult {
  reports: IntegrityReport[];
  summary: Record<string, number>;
}

export interface BundleResult {
  manifest: EvidenceManifest;
  files: Record<string, string>;
}

export interface HashResult {
  sha256: string;
  md5: string;
  size_bytes: number;
  computed_at: string;
  expected_match: boolean | null;
}

export interface ThumbnailResult {
  mime: {
    mime_type: string;
    source: string;
    confidence: number;
    extension: string;
    category: string;
  };
  thumbnail: {
    available: boolean;
    preview_kind: string;
    width: number;
    height: number;
    page_count: number;
    duration_seconds: number;
    note: string;
  };
}

function chunk(value: string, size: number): string[] {
  const parts: string[] = [];
  for (let index = 0; index < value.length; index += size) {
    parts.push(value.slice(index, index + size));
  }
  return parts;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const encoded = btoa(binary);
  return chunk(encoded, 76).join("");
}

export function base64ToBytes(value: string): Uint8Array {
  const normalized = value.replace(/\s/g, "");
  const binary = atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function routeFor(namespace: string, action: string): string {
  return `${namespace}/${action}`;
}

export class EvidenceVaultApi {
  readonly client: V2Client;

  constructor(options: EvidenceApiOptions = {}) {
    this.client =
      options.client ??
      new V2Client({
        basePath: options.basePath,
        timeout: options.timeout,
      });
  }

  list(body: Record<string, unknown> = {}): Promise<EvidenceSummary[]> {
    return this.client.call<EvidenceSummary[]>(
      routeFor("evidence", "list"),
      body,
    );
  }

  view(body: Record<string, unknown> = {}): Promise<EvidenceSummary[]> {
    return this.client.call<EvidenceSummary[]>(
      routeFor("evidence", "view"),
      body,
    );
  }

  get(id: string): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(routeFor("evidence", "get"), {
      id,
    });
  }

  detail(id: string): Promise<EvidenceDetail> {
    return this.client.call<EvidenceDetail>(routeFor("evidence", "detail"), {
      id,
    });
  }

  create(body: Record<string, unknown>): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(
      routeFor("evidence", "create"),
      body,
    );
  }

  update(
    id: string,
    changes: Record<string, unknown>,
  ): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(routeFor("evidence", "update"), {
      id,
      ...changes,
    });
  }

  setStatus(id: string, status: string, actor = "ui"): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(
      routeFor("evidence", "set_status"),
      {
        id,
        status,
        actor,
      },
    );
  }

  delete(id: string, removeBlob = true): Promise<{ deleted: boolean }> {
    return this.client.call<{ deleted: boolean }>(
      routeFor("evidence", "delete"),
      {
        id,
        remove_blob: removeBlob,
      },
    );
  }

  ingestBytes(
    bytes: Uint8Array,
    filename: string,
    options: IngestOptions = {},
  ): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(routeFor("evidence", "ingest"), {
      content_base64: bytesToBase64(bytes),
      filename,
      ...options,
    });
  }

  async ingestFile(
    file: File,
    options: IngestOptions = {},
  ): Promise<EvidenceRecord> {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return this.ingestBytes(bytes, file.name, options);
  }

  async ingestUpload(upload: EvidenceUpload): Promise<EvidenceRecord> {
    return this.ingestFile(upload.file, {
      title: upload.title,
      description: upload.description,
      tags: upload.tags,
      operator: upload.operator,
      caseReference: upload.caseReference,
    });
  }

  ingestPath(
    path: string,
    options: Record<string, unknown> = {},
  ): Promise<EvidenceRecord> {
    return this.client.call<EvidenceRecord>(
      routeFor("evidence", "ingest_path"),
      {
        path,
        ...options,
      },
    );
  }

  hash(bytes: Uint8Array, expectedSha256 = ""): Promise<HashResult> {
    return this.client.call<HashResult>(routeFor("evidence", "hash"), {
      content_base64: bytesToBase64(bytes),
      expected_sha256: expectedSha256,
    });
  }

  thumbnail(bytes: Uint8Array, filename: string): Promise<ThumbnailResult> {
    return this.client.call<ThumbnailResult>(
      routeFor("evidence", "thumbnail"),
      {
        content_base64: bytesToBase64(bytes),
        filename,
      },
    );
  }

  verify(id: string): Promise<IntegrityReport> {
    return this.client.call<IntegrityReport>(routeFor("evidence", "verify"), {
      id,
    });
  }

  verifyAll(includeUnavailable = true): Promise<VerifyAllResult> {
    return this.client.call<VerifyAllResult>(
      routeFor("evidence", "verify_all"),
      {
        include_unavailable: includeUnavailable,
      },
    );
  }

  custody(id: string): Promise<CustodyView> {
    return this.client.call<CustodyView>(routeFor("evidence", "custody.list"), {
      id,
    });
  }

  addCustody(
    id: string,
    action: string,
    options: Record<string, unknown> = {},
  ): Promise<{ id: number }> {
    return this.client.call<{ id: number }>(
      routeFor("evidence", "custody.add"),
      {
        id,
        action,
        ...options,
      },
    );
  }

  verifyCustody(id: string): Promise<{ valid: boolean; problems: string[] }> {
    return this.client.call<{ valid: boolean; problems: string[] }>(
      routeFor("evidence", "custody.verify"),
      { id },
    );
  }

  provenance(id: string): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      routeFor("evidence", "provenance.get"),
      { id },
    );
  }

  updateProvenance(
    id: string,
    changes: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      routeFor("evidence", "provenance.update"),
      { id, ...changes },
    );
  }

  links(id = "", findingId = ""): Promise<LinksView> {
    return this.client.call<LinksView>(routeFor("evidence", "links.list"), {
      id,
      finding_id: findingId,
    });
  }

  addLink(
    id: string,
    findingId: string,
    options: Record<string, unknown> = {},
  ): Promise<FindingLink> {
    return this.client.call<FindingLink>(routeFor("evidence", "links.add"), {
      id,
      finding_id: findingId,
      ...options,
    });
  }

  removeLink(linkId: number): Promise<{ removed: boolean }> {
    return this.client.call<{ removed: boolean }>(
      routeFor("evidence", "links.remove"),
      {
        link_id: linkId,
      },
    );
  }

  linksView(id = "", findingId = ""): Promise<LinksView> {
    return this.client.call<LinksView>(routeFor("evidence", "links.view"), {
      id,
      finding_id: findingId,
    });
  }

  retention(id: string): Promise<RetentionView> {
    return this.client.call<RetentionView>(
      routeFor("evidence", "retention.get"),
      { id },
    );
  }

  setRetention(
    id: string,
    changes: Record<string, unknown>,
  ): Promise<RetentionPolicy> {
    return this.client.call<RetentionPolicy>(
      routeFor("evidence", "retention.set"),
      {
        id,
        ...changes,
      },
    );
  }

  setHold(id: string, held: boolean, reason = ""): Promise<RetentionPolicy> {
    return this.client.call<RetentionPolicy>(
      routeFor("evidence", "retention.hold"),
      {
        id,
        held,
        reason,
      },
    );
  }

  retentionPlan(now = ""): Promise<RetentionDecision[]> {
    return this.client.call<RetentionDecision[]>(
      routeFor("evidence", "retention.plan"),
      {
        now,
      },
    );
  }

  applyRetention(
    now = "",
    destroy = false,
  ): Promise<{ decisions: RetentionDecision[]; disposed: string[] }> {
    return this.client.call<{
      decisions: RetentionDecision[];
      disposed: string[];
    }>(routeFor("evidence", "retention.apply"), { now, destroy });
  }

  exportManifest(caseReference = ""): Promise<EvidenceManifest> {
    return this.client.call<EvidenceManifest>(
      routeFor("evidence", "manifest.export"),
      {
        case_reference: caseReference,
      },
    );
  }

  manifestJson(): Promise<string> {
    return this.client.call<string>(routeFor("evidence", "manifest.json"), {});
  }

  previewImport(
    manifest: EvidenceManifest | Record<string, unknown> | string,
    strategy = "skip",
  ): Promise<ManifestPreview> {
    return this.client.call<ManifestPreview>(
      routeFor("evidence", "manifest.preview"),
      {
        manifest,
        strategy,
      },
    );
  }

  importManifest(
    manifest: EvidenceManifest | Record<string, unknown> | string,
    strategy = "skip",
  ): Promise<ManifestImportResult> {
    return this.client.call<ManifestImportResult>(
      routeFor("evidence", "manifest.import"),
      {
        manifest,
        strategy,
      },
    );
  }

  bundle(): Promise<BundleResult> {
    return this.client.call<BundleResult>(
      routeFor("evidence", "manifest.bundle"),
      {},
    );
  }

  stats(): Promise<EvidenceStats> {
    return this.client.call<EvidenceStats>(routeFor("evidence", "stats"), {});
  }

  search(body: Record<string, unknown> = {}): Promise<EvidenceSummary[]> {
    return this.client.call<EvidenceSummary[]>(
      routeFor("evidence", "search"),
      body,
    );
  }

  importPlan(
    manifest: EvidenceManifest,
    strategy = "skip",
  ): Promise<ImportPlan> {
    return this.previewImport(manifest, strategy).then(
      (preview) => preview.plan,
    );
  }
}
