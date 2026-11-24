/** Wire types mirrored from the V3 reports namespace. */

export type RenderFormat = "html" | "markdown" | "json" | "print";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type FindingStatus =
  | "open"
  | "confirmed"
  | "mitigated"
  | "accepted"
  | "closed";
export type SectionKind =
  | "cover"
  | "toc"
  | "executive_summary"
  | "text"
  | "findings"
  | "evidence"
  | "recommendations"
  | "appendix"
  | "divider";

export interface ThemeTokens {
  ink: string;
  muted: string;
  accent: string;
  rule: string;
  surface: string;
  cover_background: string;
  cover_ink: string;
  body_font: string;
  heading_font: string;
  mono_font: string;
  base_size_pt: number;
  heading_size_pt: number;
  line_height: number;
  space_unit_pt: number;
  border_radius_pt: number;
  page_size: "a4" | "letter";
  orientation: "portrait" | "landscape";
  margin_mm: number;
  lines_per_page: number;
  chars_per_line: number;
  show_header: boolean;
  show_footer: boolean;
  show_watermark: boolean;
  toc_leaders: boolean;
}

export interface ThemeDescriptor {
  key: string;
  name: string;
  description: string;
  glyph: string;
  builtin: boolean;
  tokens: ThemeTokens;
}

export interface ThemeSummary {
  key: string;
  name: string;
  description: string;
  glyph: string;
  page_size: string;
  orientation: string;
}

export interface EvidenceItem {
  ref: string;
  label: string;
  title: string;
  content: string;
  excerpt: string;
  kind: string;
  locator: string;
  sensitive: boolean;
}

export interface FindingItem {
  ref: string;
  label: string;
  title: string;
  summary: string;
  severity: Severity;
  status: FindingStatus;
  category: string;
  tags: string[];
  confidence: number;
  impact: string;
  recommendation: string;
  evidence: EvidenceItem[];
  references: string[];
  identifier: string;
}

export interface LayoutSection {
  key: string;
  title: string;
  kind: SectionKind;
  level: number;
  order: number;
  visible: boolean;
  body: string;
  summary: string;
  findings: FindingItem[];
  children: LayoutSection[];
  page_break_before: boolean;
  include_toc: boolean;
  metadata: Record<string, string>;
  anchor: string;
}

export interface SelectionRule {
  name: string;
  action: "include" | "exclude";
  severities: Severity[];
  statuses: string[];
  tags: string[];
  categories: string[];
  minimum_confidence: number;
  identifier: string;
}

export interface RedactionRule {
  name: string;
  pattern: string;
  replacement: string;
  enabled: boolean;
  priority: number;
  scope: "all" | "body" | "title" | "evidence";
}

export interface DesignSpec {
  key: string;
  title: string;
  subtitle: string;
  client: string;
  author: string;
  classification: string;
  generated_at: string;
  theme: string;
  sections: LayoutSection[];
  findings: FindingItem[];
  rules: SelectionRule[];
  redactions: RedactionRule[];
  minimum_severity: Severity;
  statuses: string[];
  tags: string[];
  require_evidence: boolean;
  include_sensitive_evidence: boolean;
  formats: RenderFormat[];
  options: Record<string, boolean>;
}

export interface TocEntry {
  title: string;
  anchor: string;
  page: number;
  level: number;
  kind: string;
}

export interface PageItem {
  section_key: string;
  title: string;
  anchor: string;
  kind: string;
  lines: number;
  offset: number;
  continued: boolean;
  page_index: number;
  finding_keys: string[];
}

export interface PagePlan {
  index: number;
  anchor: string;
  items: PageItem[];
  used_lines: number;
  capacity: number;
  forced_break: boolean;
}

export interface PaginationPlan {
  document_key: string;
  theme: string;
  total_pages: number;
  lines_per_page: number;
  pages: PagePlan[];
  anchors: Record<string, number>;
  finding_pages: Record<string, number>;
}

export interface RedactionSpan {
  rule: string;
  start: number;
  end: number;
  matched: string;
  replacement: string;
  before: string;
  after: string;
  section_key: string;
  field: string;
}

export interface RedactionPreview {
  text: string;
  spans: RedactionSpan[];
  applied: string[];
  counts: Record<string, number>;
  total_matches: number;
  is_complete: boolean;
}

export interface FindingDecision {
  key: string;
  ref: string;
  title: string;
  included: boolean;
  rule: string;
  reason: string;
}

export interface RenderOutput {
  format: RenderFormat;
  mime: string;
  filename: string;
  bytes: number;
  digest: string;
  content?: string;
}

export interface DesignResult {
  spec: DesignSpec;
  document: Record<string, unknown>;
  selection: {
    included: FindingItem[];
    excluded: FindingItem[];
    decisions: FindingDecision[];
    total: number;
    inclusion_rate: number;
  };
  theme: ThemeDescriptor;
  pagination: PaginationPlan;
  toc: TocEntry[];
  redaction_preview: RedactionPreview;
  outputs: RenderOutput[];
  manifest: Record<string, unknown>;
}

export interface PreviewResult {
  design_digest: string;
  redaction: RedactionPreview;
  pagination: {
    total_pages: number;
    lines_per_page: number;
    anchors: Record<string, number>;
  };
  toc: TocEntry[];
  selection: {
    included: string[];
    excluded: string[];
    decisions: FindingDecision[];
  };
}

export interface ReportsHealth {
  status: string;
  capability: string;
  enabled: boolean;
  formats: RenderFormat[];
  themes: number;
}

export interface ValidationResult {
  valid: boolean;
  issues: { code: string; message: string }[];
  rules: { total: number; includes: number; excludes: number; names: string[] };
  design_digest: string;
}
