/** Wire types for the v4 evidence lab feature slice. */

import type { PageMetaV4, V4Envelope } from "../../v4-kernel/types-v4";

export type { PageMetaV4, V4Envelope };

export type HashAlgorithmV4 = "sha256" | "sha1" | "md5";
export type StringEncodingV4 = "ascii" | "utf-8" | "utf-16le";
export type CustodyActionV4 =
  | "acquired"
  | "transferred"
  | "analyzed"
  | "verified"
  | "exported"
  | "sealed";

export interface EvidenceRecordV4 {
  id: string;
  name: string;
  size: number;
  sha256: string;
  acquired_at: string;
  tags: string[];
}

export interface HexCellV4 {
  offset: number;
  hex: string;
  ascii: string;
}

export interface HexRowV4 {
  offset: number;
  cells: HexCellV4[];
  ascii: string;
}

export interface StringHitV4 {
  offset: number;
  value: string;
  encoding: StringEncodingV4;
}

export interface HashVerificationV4 {
  algorithm: HashAlgorithmV4;
  expected: string;
  actual: string;
  matches: boolean;
}

export interface CustodyEntryV4 {
  actor: string;
  action: CustodyActionV4;
  timestamp: string;
  from_hash: string;
  to_hash: string;
}

export interface InspectionSummaryV4 {
  rows: number;
  cells: number;
  strings: number;
  verifications: number;
  custody_entries: number;
  all_verified: boolean;
}

export interface InspectionResultV4 {
  evidence_id: string;
  hex_rows: HexRowV4[];
  strings: StringHitV4[];
  verifications: HashVerificationV4[];
  custody: CustodyEntryV4[];
  generated_at: string;
  notes: string[];
  summary?: InspectionSummaryV4;
}

export interface ChainVerificationV4 {
  valid: boolean;
  length: number;
  broken_index: number;
  issues: string[];
}

export interface EvidenceListDataV4 {
  items: EvidenceRecordV4[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
  not_modified: boolean;
}

export interface EvidenceCreateDataV4 {
  evidence: EvidenceRecordV4;
  verification?: HashVerificationV4;
}

export interface CustodyDataV4 {
  evidence_id: string;
  entries: CustodyEntryV4[];
  verification: ChainVerificationV4;
}

export interface ManifestDataV4 {
  schema: string;
  generated_at: string;
  stats: Record<string, string | number>;
  records: EvidenceRecordV4[];
  tag_index: Record<string, string[]>;
  hash_index: Record<string, string[]>;
  cached_inspections: string[];
}

export interface EvidenceCreateInputV4 {
  id?: string;
  name: string;
  size: number;
  sha256?: string;
  acquired_at?: string;
  tags?: string[];
  bytes_hex?: string;
}

export type EvidenceEnvelopeV4<T> = V4Envelope<T>;
