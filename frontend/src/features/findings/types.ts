/** Wire types for the findings V3 feature. */

import type { EntityRef } from "../../v3/types";

export type FindingState =
  | "draft"
  | "confirmed"
  | "remediated"
  | "retested"
  | "closed";

export type SeverityBand = "none" | "low" | "medium" | "high" | "critical";

export type TaskStatusValue = "todo" | "in_progress" | "done" | "skipped";

export type RetestVerdictValue = "pass" | "fail" | "partial";

export type ProofRoleValue = "supporting" | "contradicting" | "context";

export interface RemediationTaskWire {
  task_id: string;
  title: string;
  detail: string;
  owner: string;
  status: TaskStatusValue;
  due_at: number;
  completed_at: number;
  proof_refs: string[];
}

export interface RetestWire {
  retest_id: string;
  verdict: RetestVerdictValue;
  tested_by: string;
  timestamp: number;
  notes: string;
  proof_refs: string[];
  follow_up: string;
}

export interface ProofBlockWire {
  block_id: string;
  ref: EntityRef;
  role: ProofRoleValue;
  excerpt: string;
  content_hash: string;
  captured_at: number;
  label: string;
  verified: boolean;
  metadata: Record<string, unknown>;
}

export interface TransitionWire {
  action: string;
  source: FindingState;
  target: FindingState;
  actor: string;
  timestamp: number;
  note: string;
  retest_id: string;
}

export interface MappingWire {
  cwes: string[];
  cves: string[];
  owasp: string[];
  capec: string[];
  mitre_attack: string[];
  notes: string;
}

export interface FindingWire {
  ref: string;
  title: string;
  summary: string;
  state: FindingState;
  vector: string;
  score: number;
  severity: SeverityBand;
  owner: string;
  target_ref: EntityRef | null;
  mappings: MappingWire;
  proof_blocks: ProofBlockWire[];
  remediation: RemediationTaskWire[];
  retests: RetestWire[];
  history: TransitionWire[];
  duplicate_of: string;
  tags: string[];
  created_at: number;
  updated_at: number;
  version: number;
  is_open: boolean;
  remediation_progress: number;
  metadata: Record<string, unknown>;
}

export interface ScorePreview {
  vector: string;
  base: number;
  threat: number;
  environmental: number;
  final: number;
  nomenclature: string;
  macro_vector: string;
  severity: SeverityBand;
  metrics: Record<string, { code: string; label: string; effective: string }>;
  missing_base: string[];
  supplemental: Record<string, string>;
}

export interface LifecycleInfo {
  state: FindingState;
  actions: string[];
  transitions: number;
  reopens: number;
  last_transition: TransitionWire | null;
  checklist_complete: boolean;
}

export interface RemediationInfo {
  total: number;
  done: number;
  skipped: number;
  percent: number;
  complete: boolean;
  next_task: string;
  tasks: RemediationTaskWire[];
  owner: string;
  target_date: string;
  notes: string;
}

export interface ProofInfo {
  total: number;
  verified: number;
  supporting: number;
  contradicting: number;
  context: number;
  targets: string[];
  issues: Array<{ block_id: string; code: string; detail: string }>;
  integrity: boolean;
}

export interface DuplicateInfo {
  source: string;
  fingerprint: string;
  count: number;
  best: {
    candidate_ref: EntityRef;
    score: number;
    reasons: string[];
    threshold: number;
    confirmed: boolean;
  } | null;
  candidates: Array<{
    candidate_ref: EntityRef;
    score: number;
    reasons: string[];
    threshold: number;
    confirmed: boolean;
  }>;
}

export interface FindingDetail {
  finding: FindingWire;
  lifecycle: LifecycleInfo;
  remediation: RemediationInfo;
  proof: ProofInfo;
  mappings: {
    cwes: string[];
    cves: string[];
    owasp: string[];
    mitre_attack: string[];
    known_count: number;
    unknown: string[];
    mitigations: string[];
    resolutions: Array<{ cwe_id: string; known: boolean }>;
  };
  duplicates: DuplicateInfo;
  score: ScorePreview | null;
}

export interface PageInfo {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface FindingList {
  items: FindingWire[];
  next_cursor: string;
  etag: string;
  page: PageInfo;
  filter_hash: string;
  not_modified?: boolean;
}

export interface StudioSummary {
  total: number;
  by_state: Record<string, number>;
  by_severity: Record<string, number>;
  open: number;
  duplicates: number;
  proof_issues: number;
  incomplete_checklists: number;
  events: number;
}

export interface CweEntry {
  cwe_id: string;
  name: string;
  category: string;
  description: string;
  owasp: string[];
  capec: string[];
  mitigations: string[];
  references: string[];
}
