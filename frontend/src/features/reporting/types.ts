export type ReportFormat = "markdown" | "html" | "json" | "print";

export type ReportProfile =
  | "standard"
  | "technical"
  | "compact"
  | "landscape"
  | "letter";

export type SeverityName = "info" | "low" | "medium" | "high" | "critical";

export type ValidationSeverity = "error" | "warning";

export interface ReportingHealth {
  ok: boolean;
  namespace: string;
  formats: string[];
  templates: string[];
  profiles: string[];
}

export interface TemplateSummary {
  key: string;
  name: string;
  description: string;
  default_title: string;
  classification: string;
  tags: string[];
  print_profile: string;
  glyph: string;
}

export interface ReportTemplate extends TemplateSummary {
  sections: ReportSection[];
}

export interface ProfileSummary {
  name: string;
  page_size: string;
  orientation: string;
  font_size: string;
  line_height: number;
  margin_top: string;
  margin_bottom: string;
  margin_left: string;
  margin_right: string;
  show_cover: boolean;
  show_toc: boolean;
  break_sections: boolean;
  [key: string]: unknown;
}

export interface FieldSchema {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export interface ConfigSchema {
  version: string;
  fields: FieldSchema[];
  formats: {
    formats: string[];
    extensions: Record<string, string>;
    mimes: Record<string, string>;
  };
}

export interface EvidenceRef {
  identifier: string;
  title: string;
  content: string;
  kind: string;
  source_id: number | null;
  source_path: string;
  source_updated_at: string;
  locator: string;
  excerpt: string;
  sensitive: boolean;
}

export interface Finding {
  identifier: string;
  title: string;
  summary: string;
  severity: SeverityName;
  status: string;
  category: string;
  tags: string[];
  evidence: EvidenceRef[];
  impact: string;
  recommendation: string;
  references: string[];
  confidence: number;
  cvss: string;
  cwe: string;
  affected: string;
}

export interface ReportSection {
  identifier: string;
  title: string;
  kind: string;
  body: string;
  summary: string;
  findings: Finding[];
  children: ReportSection[];
  order: number;
  level: number;
  include_toc: boolean;
  page_break_before: boolean;
  metadata: Record<string, string>;
}

export interface SeverityCounts {
  info: number;
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface InclusionRule {
  name: string;
  action: "include" | "exclude";
  tags: string[];
  severities: SeverityName[];
  statuses: string[];
  categories: string[];
  minimum_confidence: number;
  path_prefix: string;
  identifier: string;
}

export interface RedactionRule {
  name: string;
  pattern: string;
  replacement: string;
  enabled: boolean;
  priority: number;
  flags: string[];
  scope: "all" | "body" | "evidence" | "title";
}

export interface ReportConfig {
  title: string;
  template: string;
  client: string;
  author: string;
  classification: string;
  scope: string[];
  generated_at: string;
  introduction: string;
  conclusion: string;
  sections: ReportSection[];
  findings: Finding[];
  rules: InclusionRule[];
  redactions: RedactionRule[];
  tags: string[];
  statuses: string[];
  minimum_severity: SeverityName;
  include_empty_sections: boolean;
  include_evidence: boolean;
  include_appendices: boolean;
  page_size: string;
  orientation: string;
  print_profile: string;
  print_cover: boolean;
  print_toc: boolean;
  redact_sensitive: boolean;
  notes: string;
}

export interface ReportDocument {
  config: ReportConfig;
  sections: ReportSection[];
  findings: Finding[];
  finding_count: number;
  severity: SeverityCounts;
  title: string;
  template: string;
  generated_at: string;
  source_digest: string;
  warnings: string[];
}

export interface SeveritySummary extends SeverityCounts {
  counts: SeverityCounts;
  total: number;
  highest: SeverityName;
  weighted: number;
  risk_level: string;
  bar: string;
  percentages: Record<SeverityName, number>;
  findings?: Array<{
    identifier: string;
    severity: SeverityName;
    title: string;
  }>;
}

export interface PreviewSection {
  identifier: string;
  title: string;
  level: number;
  finding_count: number;
}

export interface ReportPreview {
  title: string;
  template: string;
  finding_count: number;
  severity: SeveritySummary;
  sections: PreviewSection[];
  warnings: string[];
  evidence: Record<string, number>;
}

export interface ValidationIssue {
  code: string;
  message: string;
  path: string;
  severity: ValidationSeverity;
}

export interface ValidationReport {
  valid: boolean;
  errors: number;
  warnings: number;
  issues: ValidationIssue[];
}

export interface RenderedReport {
  format: ReportFormat;
  content: string;
  filename: string;
  mime: string;
  manifest: Record<string, unknown>;
}

export interface SourceSnapshot {
  generated_at: string;
  notes: unknown[];
  [key: string]: unknown;
}

export interface SectionSummary {
  sections: ReportSection[];
  stats: Record<string, number>;
  outline: string[];
}

export interface RedactionPreviewSpan {
  rule: string;
  matched: string;
  replacement: string;
  before: string;
  after: string;
  start?: number;
  end?: number;
}

export interface RedactionResult {
  text: string;
  applied: string[];
  counts: Record<string, number>;
  preview: RedactionPreviewSpan[];
  rules: RedactionRule[];
}

export type ReportingRequest = Record<string, unknown>;
