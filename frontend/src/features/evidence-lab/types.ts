/** Wire types mirroring the Python evidence-lab API v3 contracts. */

export interface HexRowData {
  offset: number;
  offset_hex: string;
  cells: string[];
  ascii: string;
  selected: boolean;
}

export interface HexWindowData {
  start: number;
  length: number;
  end: number;
  bytes_per_row: number;
  total_bytes: number;
  truncated: boolean;
  selection_start: number | null;
  selection_end: number | null;
  rows: HexRowData[];
}

export interface StringHitData {
  offset: number;
  end: number;
  text: string;
  encoding: string;
  length: number;
  printable_ratio: number;
  kind: string;
}

export interface StringScanData {
  hits: StringHitData[];
  encoding: string;
  min_length: number;
  bytes_scanned: number;
  truncated: boolean;
  counts: Record<string, number>;
}

export interface EntropyBucketData {
  label: string;
  low: number;
  high: number;
  count: number;
}

export interface EntropyReportData {
  sample_bytes: number;
  total_bytes: number;
  entropy: number;
  normalized: number;
  classification: string;
  truncated: boolean;
  histogram: number[];
  buckets: EntropyBucketData[];
}

export interface MagicMatchData {
  media_type: string;
  description: string;
  category: string;
  extension: string;
  confidence: number;
  offset: number;
  signature_hex: string;
  source: string;
}

export interface FileClassData {
  matches: MagicMatchData[];
  primary: MagicMatchData | null;
  media_type: string;
  category: string;
  extension_hint: string;
  header_bytes: number;
}

export interface HashPanelData {
  sha256: string;
  blake2b: string;
  sha256_short: string;
  blake2b_short: string;
  size_bytes: number;
  computed_at: string;
  blake2b_size: number;
  combined_id: string;
}

export interface IntegrityBadgeData {
  state: "verified" | "unverified" | "mismatch" | "unknown";
  sha256_match: boolean;
  blake2b_match: boolean;
  size_match: boolean;
  ok: boolean;
  reasons: string[];
}

export interface ThumbnailData {
  ref: string;
  preview_kind: string;
  category: string;
  width: number;
  height: number;
  mime_type: string;
  source_sha256: string;
  generated_at: string;
  available: boolean;
  note: string;
}

export interface EvidenceReportData {
  ref: string;
  size_bytes: number;
  panel: HashPanelData;
  badge: IntegrityBadgeData;
  file_class: FileClassData;
  hex_window: HexWindowData | null;
  strings: StringScanData | null;
  entropy: EntropyReportData | null;
  thumbnail: ThumbnailData | null;
  warnings: string[];
}

export interface IngestRecordData {
  ref: string;
  filename: string;
  size_bytes: number;
  panel: HashPanelData;
  file_class: FileClassData;
  thumbnail: ThumbnailData;
  tags: string[];
  ingested_at: string;
  source: string;
}

export interface CustodyNodeData {
  kind: string;
  value: string;
  ref: string;
  label: string;
  action: string;
  timestamp: string;
  depth: number;
  terminal: boolean;
}

export interface CustodyEdgeData {
  source: string;
  target: string;
  kind: string;
  label: string;
  timestamp: string;
  sequence: number;
}

export interface CustodyEventData {
  date: string;
  sequence: number;
  action: string;
  actor: string;
  description: string;
  timestamp: string;
  hash: string;
  previous_hash: string;
  node: string;
}

export interface CustodyGroupData {
  date: string;
  events: CustodyEventData[];
}

export interface CustodyGraphData {
  root: string;
  nodes: CustodyNodeData[];
  edges: CustodyEdgeData[];
  timeline: CustodyGroupData[];
  problems: string[];
  cycle_free: boolean;
  verified: boolean;
  depth: number;
  summary: {
    root: string;
    nodes: number;
    edges: number;
    depth: number;
    actions: string[];
    actors: string[];
    verified: boolean;
  };
}

export interface BundleEntryData {
  key: string;
  sha256: string;
  blake2b: string;
  size_bytes: number;
  label: string;
}

export interface BundleDeltaData {
  key: string;
  kind: "added" | "removed" | "modified" | "unchanged";
  left: BundleEntryData | null;
  right: BundleEntryData | null;
  size_delta: number;
  hash_changed: boolean;
}

export interface BundleDiffData {
  left_id: string;
  right_id: string;
  deltas: BundleDeltaData[];
  counts: Record<string, number>;
  fingerprint_left: string;
  fingerprint_right: string;
  identical: boolean;
}

export interface RangeChunkData {
  start: number;
  end: number;
  length: number;
  total_size: number;
  truncated: boolean;
  content_range: string;
  preview_hex: string;
}

export interface LabManifest {
  capability: string;
  enabled: boolean;
  max_window_bytes: number;
  max_scan_bytes: number;
  max_preview_bytes: number;
  max_payload_bytes: number;
  entropy_sample_bytes: number;
  chunk_size: number;
  signatures: number;
  records: number;
  graphs: number;
  custody: Record<string, unknown>;
}

export type IngestPhase =
  | "queued"
  | "reading"
  | "inspecting"
  | "verified"
  | "mismatch"
  | "rejected";

export interface IngestItem {
  id: string;
  file: File;
  phase: IngestPhase;
  report: EvidenceReportData | null;
  message: string;
  progress: number;
}

export const STRING_KINDS = [
  "plain",
  "url",
  "email",
  "ipv4",
  "path",
  "hex",
  "base64",
] as const;

export type StringKind = (typeof STRING_KINDS)[number];
