import type {
  A11yPreferences,
  FocusMode,
  Platform,
  ResolvedDirection,
  Severity,
} from "./types";

export const A11Y_NAMESPACE = "a11y";

export const A11Y_STORAGE_KEY = "redscribe.a11y.preferences.v2";

export const A11Y_ROUTES = {
  health: "a11y.health",
  audit: "a11y.audit",
  contrast: "a11y.contrast",
  contrastCheck: "a11y.contrast_check",
  focus: "a11y.focus",
  aria: "a11y.aria",
  ariaAttribute: "a11y.aria_attribute",
  roles: "a11y.roles",
  shortcuts: "a11y.shortcuts",
  shortcutFormat: "a11y.shortcut_format",
  locales: "a11y.locales",
  localeDetail: "a11y.locale_detail",
  catalog: "a11y.catalog",
  translate: "a11y.translate",
  coverage: "a11y.coverage",
  format: "a11y.format",
  rtl: "a11y.rtl",
  themes: "a11y.themes",
  themeDetail: "a11y.theme_detail",
  themeCreate: "a11y.theme_create",
  themeCss: "a11y.theme_css",
  themeCompare: "a11y.theme_compare",
  themeContrast: "a11y.theme_contrast",
  themeFixes: "a11y.theme_fixes",
  preferences: "a11y.preferences",
  preferencesDefaults: "a11y.preferences_defaults",
  preferencesSchema: "a11y.preferences_schema",
  preferencesValidate: "a11y.preferences_validate",
  preferencesUpdate: "a11y.preferences_update",
  preferencesReplace: "a11y.preferences_replace",
  preferencesReset: "a11y.preferences_reset",
  preferencesExport: "a11y.preferences_export",
  preferencesImport: "a11y.preferences_import",
  dashboard: "a11y.dashboard",
} as const;

export const WCAG_LEVELS: readonly string[] = ["A", "AA", "AAA"];

export const SEVERITY_RANK: Record<Severity, number> = {
  critical: 5,
  serious: 4,
  moderate: 3,
  minor: 2,
  info: 1,
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  serious: "Serious",
  moderate: "Moderate",
  minor: "Minor",
  info: "Info",
};

export const DIRECTION_LABEL: Record<ResolvedDirection, string> = {
  ltr: "Left to right",
  rtl: "Right to left",
};

export const MODE_LABEL: Record<string, string> = {
  light: "Light",
  dark: "Dark",
  "high-contrast": "High contrast",
};

export const FOCUS_MODE_LABEL: Record<FocusMode, string> = {
  global: "Global",
  editor: "Editor",
  sidebar: "Sidebar",
  dialog: "Dialog",
  reading: "Reading",
};

export const PLATFORM_LABEL: Record<Platform, string> = {
  desktop: "Desktop",
  mac: "macOS",
  web: "Web",
};

export const RTL_LANGUAGES: readonly string[] = [
  "ar",
  "fa",
  "he",
  "ps",
  "sd",
  "ur",
  "yi",
];

export const MODIFIER_ORDER: readonly string[] = [
  "ctrl",
  "alt",
  "shift",
  "meta",
];

export const KEY_ALIASES: Record<string, string> = {
  control: "ctrl",
  command: "meta",
  cmd: "meta",
  option: "alt",
  escape: "esc",
  esc: "esc",
  return: "enter",
  del: "delete",
  spacebar: "space",
  " ": "space",
  arrowup: "up",
  arrowdown: "down",
  arrowleft: "left",
  arrowright: "right",
};

export const MAC_KEY_LABELS: Record<string, string> = {
  ctrl: "^",
  alt: "⌥",
  shift: "⇧",
  meta: "⌘",
  enter: "↩",
  esc: "⎋",
  space: "␣",
  up: "↑",
  down: "↓",
  left: "←",
  right: "→",
};

export const DEFAULT_A11Y_PREFERENCES: A11yPreferences = {
  locale: "en",
  theme: "paper",
  direction: "auto",
  font_scale: 1,
  reduce_motion: false,
  high_contrast: false,
  screen_reader_hints: true,
  focus_ring_boost: false,
  shortcuts: {},
  updated_at: "1970-01-01T00:00:00Z",
  revision: 0,
};

export const FONT_SCALE_MIN = 0.75;
export const FONT_SCALE_MAX = 2;
export const ANNOUNCEMENT_LIMIT = 6;
export const MAX_SUGGESTIONS = 12;
