/** Shared V3 wire types mirroring the Python API v3 contracts. */

export type EntityKind =
  | "note"
  | "folder"
  | "target"
  | "finding"
  | "evidence"
  | "playbook"
  | "run"
  | "report"
  | "section"
  | "activity"
  | "extension"
  | "snippet";

export type EntityStatus = "draft" | "active" | "archived" | "deleted";

export type LinkKind =
  | "contains"
  | "relates"
  | "evidences"
  | "derives"
  | "references"
  | "duplicates"
  | "supersedes";

export interface EntityRef {
  kind: EntityKind;
  value: string;
  ref: string;
  label?: string;
}

export interface EntityRecord {
  entity_id: string;
  kind: EntityKind;
  title: string;
  status: EntityStatus;
  tags: string[];
  summary: string;
  owner: string;
  created_at: number;
  updated_at: number;
  version: number;
  metadata: Record<string, unknown>;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ResponseMeta {
  request_id: string;
  api_version: string;
  etag?: string;
  page?: PageMeta;
  warnings?: string[];
}

export interface Envelope<T> {
  data: T;
  meta: ResponseMeta;
}

export interface ErrorDetail {
  code: string;
  message: string;
  field: string;
  retryable: boolean;
  context: Record<string, unknown>;
}

export interface ErrorEnvelope {
  error: ErrorDetail;
  meta: ResponseMeta;
  status?: number;
}

export interface RouteInfo {
  path: string;
  methods: string[];
  public: boolean;
}

export interface RouteManifest {
  version: string;
  namespaces: string[];
  routes: RouteInfo[];
}

export interface CapabilityMap {
  [name: string]: boolean;
}

export function isEnvelope(value: unknown): value is Envelope<unknown> {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    "data" in candidate &&
    "meta" in candidate &&
    typeof candidate.meta === "object"
  );
}

export function unwrap<T>(envelope: Envelope<T>): T {
  return envelope.data;
}
