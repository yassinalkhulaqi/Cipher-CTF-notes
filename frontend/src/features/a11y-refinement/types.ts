/** Wire types for the B12 accessibility refinement API. */

export type WcagLevel = "A" | "AA" | "AAA";
export type Severity = "info" | "minor" | "moderate" | "serious" | "critical";
export type Direction = "ltr" | "rtl" | "auto";
export type ResolvedDirection = "ltr" | "rtl";
export type MotionMode = "full" | "reduced" | "off";
export type FocusScope = "global" | "editor" | "sidebar" | "dialog" | "reading";

export interface RuleInfo {
  id: string;
  criterion: string;
  title: string;
  level: WcagLevel;
  scope: string;
  description: string;
  remediation: string;
  automated: boolean;
}

export interface SurfaceView {
  name: string;
  label: string;
  level: WcagLevel;
  locale: string;
  focus_obscured: string;
  focus_indicator_width: number;
  focus_indicator_contrast: number;
  target_size: number;
  drag_only: boolean;
  has_help: boolean;
  repeated_entry: boolean;
  auth_captcha: string;
  non_text_contrast: number;
  hover_content: boolean;
  keyboard_reachable: boolean;
  screen_reader_labels: boolean;
  tiles: string[];
}

export interface RuleFindingView {
  rule: string;
  criterion: string;
  severity: Severity;
  target: string;
  message: string;
  remediation: string;
  details: Record<string, unknown>;
}

export interface AuditRunView {
  surface: string;
  level: WcagLevel;
  findings: RuleFindingView[];
  passed_rules: string[];
  checked: number;
  score: number;
  passed: boolean;
}

export interface AuditSummaryView {
  surfaces: number;
  passed: number;
  failed: number;
  findings: number;
  by_severity: Record<string, number>;
  checked_rules: number;
  score: number;
  criteria: string[];
}

export interface ContrastPairView {
  name: string;
  foreground: string;
  background: string;
  ratio: number;
  required: number;
  passed: boolean;
  large_text: boolean;
  graphical: boolean;
  level: WcagLevel;
}

export interface ContrastFixView {
  name: string;
  before: number;
  after: number;
  required: number;
  foreground: string;
  background: string;
  direction: "foreground" | "background";
}

export interface ContrastReportView {
  pairs: ContrastPairView[];
  failures: ContrastPairView[];
  fixes: ContrastFixView[];
  suggestions: string[];
  level: WcagLevel;
  score: number;
  passed: boolean;
}

export interface ThemeContrastView {
  light: ContrastReportView;
  dark: ContrastReportView;
  equivalent: boolean;
  shared_failures: string[];
  score: number;
  passed: boolean;
}

export interface FormatResultView {
  locale: string;
  kind: string;
  text: string;
  direction: ResolvedDirection;
  bidi_isolated: boolean;
  fallback: string;
}

export interface LocaleOptionView {
  value: string;
  label: string;
  native_name: string;
  direction: ResolvedDirection;
  script: string;
}

export interface PaneLayoutView {
  pane: string;
  direction: ResolvedDirection;
  css_class: string;
  sides: Record<string, string>;
  mirror_icons: string[];
  ordered_regions: string[];
  warnings: string[];
}

export interface LayoutManifestView {
  locale: string;
  direction: ResolvedDirection;
  rtl: boolean;
  css: Record<string, string>;
  regions: string[];
  panes: PaneLayoutView[];
  static_icons: string[];
  mirrored_icons: string[];
  warnings: string[];
}

export interface KeyboardBindingView {
  action: string;
  keys: string[];
  label: string;
  group: string;
  scope: FocusScope;
  display: string;
  enabled: boolean;
  sequence: number;
  description: string;
}

export interface KeyboardMapView {
  locale: string;
  platform: string;
  bindings: KeyboardBindingView[];
  groups: Record<string, string[]>;
  conflicts: Record<string, unknown>[];
  coverage: Record<string, number>;
  complete: boolean;
}

export interface PreferenceSnapshotView {
  locale: string;
  theme: string;
  direction: Direction;
  font_scale: number;
  reduce_motion: boolean;
  high_contrast: boolean;
  screen_reader_hints: boolean;
  focus_ring_boost: boolean;
  shortcuts: Record<string, string[]>;
  updated_at: string;
  revision: number;
}

export interface UnifiedAppearanceView {
  theme: string;
  motion: MotionMode;
  density: "comfortable" | "compact";
  direction: Direction;
  font_scale: number;
  high_contrast: boolean;
  focus_ring_boost: boolean;
}

export interface PreferenceRecordView {
  profile: string;
  revision: number;
  source: string;
  checksum: string;
  tags: string[];
  preferences: PreferenceSnapshotView;
}

export interface SyncReportView {
  strategy: string;
  applied: boolean;
  record: PreferenceRecordView;
  changes: string[];
  conflicts: string[];
  warnings: string[];
}

export interface A11yDashboardView {
  locale: string;
  direction: ResolvedDirection;
  audit: AuditSummaryView;
  surfaces: string[];
  contrast: number;
  keyboard: { bindings: number; groups: string[]; complete: boolean };
  catalogs: Record<string, unknown>;
  preferences: {
    appearance: UnifiedAppearanceView;
    css: Record<string, string>;
  };
  motion: {
    mode: MotionMode;
    content_hidden: boolean;
    equivalent_focus_order: boolean;
  };
}
