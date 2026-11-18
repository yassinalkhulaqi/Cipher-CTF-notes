export type A11yDirection = "ltr" | "rtl" | "auto";
export type ResolvedDirection = "ltr" | "rtl";
export type WcagLevel = "A" | "AA" | "AAA";
export type Severity = "critical" | "serious" | "moderate" | "minor" | "info";
export type FocusMode = "global" | "editor" | "sidebar" | "dialog" | "reading";
export type Platform = "desktop" | "mac" | "web";
export type Politeness = "polite" | "assertive";

export interface ThemeOption {
  value: string;
  label: string;
  mode: string;
  description: string;
  accent: string;
}

export interface LocaleOption {
  value: string;
  label: string;
  native: string;
  direction: ResolvedDirection;
}

export interface ColorPairPayload {
  name: string;
  foreground: string;
  background: string;
  ratio: number;
  font_size: number;
  bold: boolean;
  large_text: boolean;
  required: number;
  passed: boolean;
  level: string;
}

export interface ContrastReportPayload {
  pairs: ColorPairPayload[];
  failures: string[];
  score: number;
  target: string;
  passed: boolean;
  suggestions: string[];
}

export interface AuditIssue {
  rule: string;
  severity: Severity;
  message: string;
  target: string;
  wcag: string;
  remediation: string;
  details?: Record<string, unknown>;
}

export interface AuditReportPayload {
  issues: AuditIssue[];
  checked_elements: number;
  passed_rules: string[];
  score: number;
  level: string;
  passed: boolean;
  summary: Record<string, unknown>;
}

export interface AriaReportPayload {
  issues: AuditIssue[];
  roles_seen: string[];
  accessible_names: Record<string, string>;
  checked: number;
  passed: boolean;
}

export interface FocusStep {
  order: number;
  target: string;
  tag: string;
  tab_index: number;
  description: string;
  hidden: boolean;
}

export interface FocusReportPayload {
  steps: FocusStep[];
  issues: AuditIssue[];
  focusable_count: number;
  positive_tabindex_count: number;
  has_skip_link: boolean;
  score: number;
  summary: Record<string, unknown>;
  simulation?: string[];
}

export interface ShortcutBinding {
  action: string;
  keys: string[];
  label: string;
  scope: string;
  description: string;
  enabled: boolean;
  sequence: number;
  binding: string;
}

export interface ShortcutReportPayload {
  shortcuts: ShortcutBinding[];
  conflicts: Array<Record<string, unknown>>;
  unknown_keys: Record<string, string[]>;
  valid: boolean;
  groups: Record<string, string[]>;
  suggestion?: string[];
  suggestion_error?: string;
}

export interface A11yPreferences {
  locale: string;
  theme: string;
  direction: A11yDirection;
  font_scale: number;
  reduce_motion: boolean;
  high_contrast: boolean;
  screen_reader_hints: boolean;
  focus_ring_boost: boolean;
  shortcuts: Record<string, string[]>;
  updated_at: string;
  revision: number;
}

export interface PreferenceRecordPayload {
  version: number;
  profile: string;
  source: string;
  signature: string;
  preferences: A11yPreferences;
}

export interface A11yHealth {
  ok: boolean;
  namespace: string;
  features: string[];
  locales: number;
  catalogs: number;
  themes: number;
  shortcuts: number;
  wcag_levels: string[];
}

export interface A11yDashboard {
  locale: string;
  direction: ResolvedDirection;
  audit: AuditReportPayload;
  focus: FocusReportPayload;
  aria: AriaReportPayload;
  contrast: ContrastReportPayload;
  preferences: A11yPreferences;
  shortcuts: ShortcutReportPayload;
  themes: ThemeOption[];
  catalogs: string[];
}

export interface Announcement {
  id: string;
  message: string;
  politeness: Politeness;
  timestamp: number;
}

export interface CatalogPayload {
  locale: string;
  description: string;
  count: number;
  keys: string[];
  messages: Record<string, string>;
}

export interface CssPayload {
  theme: string;
  css: string;
}

export interface ThemeDefinitionPayload {
  name: string;
  label: string;
  mode: string;
  tokens: Record<string, string>;
  description?: string;
  extends?: string;
  accent_hue?: number;
}

export interface ThemeDetailPayload {
  theme: string;
  summary: Record<string, unknown>;
  contrast: ContrastReportPayload;
  issue_summary: Record<string, unknown>;
  grid: string[];
  css: string;
}

export interface RtlPayload {
  locale: string;
  direction: ResolvedDirection;
  text: string;
  mirrored_text: string;
  warnings: string[];
}
