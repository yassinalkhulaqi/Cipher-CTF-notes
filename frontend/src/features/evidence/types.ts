export type EvidenceStatus =
  | "discovered"
  | "acquired"
  | "analyzed"
  | "verified"
  | "sealed"
  | "archived"
  | "disposed";

export type EvidenceKind =
  | "document"
  | "image"
  | "video"
  | "audio"
  | "log"
  | "database"
  | "disk_image"
  | "archive"
  | "email"
  | "other";

export type IntegrityState =
  | "verified"
  | "unverified"
  | "missing"
  | "mismatch"
  | "error";

export type CustodyAction =
  | "created"
  | "acquired"
  | "transferred"
  | "analyzed"
  | "verified"
  | "sealed"
  | "released"
  | "destroyed"
  | "imported";

export type LinkType =
  | "supports"
  | "refutes"
  | "derived_from"
  | "related_to"
  | "contains"
  | "duplicate_of";

export interface EvidenceDigests {
  sha256: string;
  md5: string;
  size_bytes: number;
  computed_at: string;
}

export interface EvidenceMime {
  mime_type: string;
  source: string;
  confidence: number;
  extension: string;
  category: string;
}

export interface EvidenceThumbnail {
  available: boolean;
  preview_kind: string;
  width: number;
  height: number;
  page_count: number;
  duration_seconds: number;
  source_sha256: string;
  generated_at: string;
  note: string;
}

export interface AcquisitionProvenance {
  evidence_id: string;
  method: string;
  tool: string;
  tool_version: string;
  operator: string;
  source_path: string;
  source_description: string;
  acquired_at: string;
  case_reference: string;
  witness: string;
  image_number: number;
  notes: string;
}

export interface EvidenceRecord {
  id: string;
  title: string;
  description: string;
  kind: EvidenceKind;
  status: EvidenceStatus;
  original_filename: string;
  stored_path: string;
  mime: EvidenceMime;
  digests: EvidenceDigests;
  thumbnail: EvidenceThumbnail;
  provenance: AcquisitionProvenance;
  tags: string[];
  note_id: number | null;
  created_at: string;
  updated_at: string;
  acquired_at: string;
  custom_fields: Record<string, unknown>;
}

export interface EvidenceSummary {
  id: string;
  title: string;
  kind: EvidenceKind;
  status: EvidenceStatus;
  original_filename: string;
  mime_type: string;
  sha256: string;
  md5: string;
  size_bytes: number;
  tags: string[];
  note_id: number | null;
  preview_kind: string;
  has_thumbnail: boolean;
  created_at: string;
  updated_at: string;
}

export interface IntegrityIssue {
  code: string;
  severity: string;
  message: string;
  field?: string;
}

export interface IntegrityReport {
  evidence_id: string;
  state: IntegrityState;
  digest_match: boolean;
  md5_match: boolean;
  custody_valid: boolean;
  manifest_match: boolean | null;
  checked_at: string;
  issues: IntegrityIssue[] | string[];
}

export interface CustodyEvent {
  id: number;
  evidence_id: string;
  action: CustodyAction;
  actor: string;
  timestamp: string;
  description: string;
  location: string;
  reference: string;
  previous_hash: string;
  event_hash: string;
  metadata: Record<string, unknown>;
}

export interface CustodyTimelineEntry {
  date: string;
  events: CustodyEvent[];
}

export interface CustodyView {
  events: CustodyEvent[];
  timeline: CustodyTimelineEntry[];
  summary: {
    count: number;
    actors: string[];
    first?: string;
    last?: string;
    [key: string]: unknown;
  };
  valid: boolean;
  problems: string[];
}

export interface FindingLink {
  id: number;
  evidence_id: string;
  finding_id: string;
  finding_title: string;
  link_type: LinkType;
  strength: number;
  created_at: string;
  created_by: string;
  note: string;
}

export interface LinksView {
  links: FindingLink[];
  groups: Record<string, FindingLink[]>;
  summary: Record<string, number>;
}

export interface RetentionPolicy {
  evidence_id: string;
  basis: string;
  retain_days: number;
  retain_until: string;
  legal_hold: boolean;
  review_at: string;
  disposition: string;
  updated_at: string;
  reason: string;
}

export interface RetentionDecision {
  evidence_id: string;
  action: string;
  due_at: string;
  days_remaining: number;
  reason: string;
  [key: string]: unknown;
}

export interface RetentionView {
  evidence_id: string;
  policy: RetentionPolicy | null;
  decision: RetentionDecision | null;
}

export interface ManifestEntry {
  evidence_id: string;
  filename: string;
  sha256: string;
  md5: string;
  size_bytes: number;
  stored_path: string;
  kind: EvidenceKind;
  status: EvidenceStatus;
}

export interface EvidenceManifest {
  format: string;
  version: number;
  generated_at: string;
  generator: string;
  case_reference: string;
  records: EvidenceRecord[];
  entries: ManifestEntry[];
  custody: CustodyEvent[];
  links: FindingLink[];
  retention: RetentionPolicy[];
  checksum: string;
}

export interface ImportPlan {
  create: string[];
  update: string[];
  skip: string[];
  conflicts: string[];
  warnings: string[];
  [key: string]: unknown;
}

export interface ManifestPreview {
  manifest: EvidenceManifest;
  valid: boolean;
  problems: string[];
  plan: ImportPlan;
}

export interface ManifestImportResult {
  plan: ImportPlan;
  created: string[];
  updated: string[];
  skipped: string[];
  warnings: string[];
  checksum: string;
  imported_at: string;
}

export interface EvidenceStats {
  total: number;
  by_status: Record<string, number>;
  by_kind: Record<string, number>;
  total_bytes: number;
  verified: number;
  alerts: number;
  custody_events: number;
  links: number;
  legal_holds: number;
}

export interface EvidenceDetail {
  record: EvidenceRecord;
  integrity: IntegrityReport;
  custody: CustodyView;
  provenance: {
    summary: Record<string, unknown>;
    checklist: Array<{
      field: string;
      label: string;
      filled: boolean;
      value: unknown;
    }>;
    missing_fields: string[];
    timeline: Array<Record<string, unknown>>;
  };
  links: LinksView;
  retention: RetentionView;
}

export interface EvidenceFilters {
  query: string;
  tag: string;
  hashPrefix: string;
  status: EvidenceStatus | "";
  kind: EvidenceKind | "";
  sort: "created_at" | "updated_at" | "title" | "size_bytes";
  direction: "asc" | "desc";
}

export interface EvidenceUpload {
  file: File;
  title?: string;
  description?: string;
  tags?: string[];
  operator?: string;
  caseReference?: string;
}
