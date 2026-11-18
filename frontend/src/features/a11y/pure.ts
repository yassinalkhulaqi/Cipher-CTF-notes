import {
  ANNOUNCEMENT_LIMIT,
  DEFAULT_A11Y_PREFERENCES,
  DIRECTION_LABEL,
  FOCUS_MODE_LABEL,
  FONT_SCALE_MAX,
  FONT_SCALE_MIN,
  KEY_ALIASES,
  MAC_KEY_LABELS,
  MAX_SUGGESTIONS,
  MODIFIER_ORDER,
  RTL_LANGUAGES,
  SEVERITY_LABEL,
  SEVERITY_RANK,
  WCAG_LEVELS,
} from "./config";
import type {
  A11yDirection,
  A11yPreferences,
  Announcement,
  AuditIssue,
  ColorPairPayload,
  FocusMode,
  FocusStep,
  Platform,
  ResolvedDirection,
  Severity,
  ShortcutBinding,
  ThemeOption,
} from "./types";

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function clampFontScale(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_A11Y_PREFERENCES.font_scale;
  return clamp(value, FONT_SCALE_MIN, FONT_SCALE_MAX);
}

export function normalizeThemeName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function normalizeLocaleTag(value: string): string {
  const parts = value.trim().replace(/_/g, "-").split("-").filter(Boolean);
  if (parts.length === 0) return DEFAULT_A11Y_PREFERENCES.locale;
  const language = parts[0].toLowerCase();
  const rest = parts
    .slice(1)
    .map((part) => (part.length === 2 ? part.toUpperCase() : part));
  return [language, ...rest].join("-");
}

export function languageOf(value: string): string {
  return normalizeLocaleTag(value).split("-")[0];
}

export function isRtlLocale(value: string): boolean {
  return RTL_LANGUAGES.includes(languageOf(value));
}

export function directionOfLocale(value: string): ResolvedDirection {
  return isRtlLocale(value) ? "rtl" : "ltr";
}

export function resolveDirection(
  direction: A11yDirection,
  locale: string,
): ResolvedDirection {
  if (direction === "ltr" || direction === "rtl") return direction;
  return directionOfLocale(locale);
}

export function formatFontScale(value: number): string {
  return `${Math.round(clampFontScale(value) * 100)}%`;
}

export function formatRatio(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}:1`;
}

export function severityRank(value: string): number {
  return SEVERITY_RANK[value as Severity] ?? 0;
}

export function severityLabel(value: string): string {
  return SEVERITY_LABEL[value as Severity] ?? value;
}

export function directionLabel(value: ResolvedDirection): string {
  return DIRECTION_LABEL[value];
}

export function focusModeLabel(value: string): string {
  return FOCUS_MODE_LABEL[value as FocusMode] ?? value;
}

export function sortIssues(issues: readonly AuditIssue[]): AuditIssue[] {
  return [...issues].sort(
    (first, second) =>
      severityRank(second.severity) - severityRank(first.severity) ||
      first.rule.localeCompare(second.rule) ||
      first.target.localeCompare(second.target),
  );
}

export function summarizeIssues(
  issues: readonly AuditIssue[],
): Record<Severity, number> {
  const result: Record<Severity, number> = {
    critical: 0,
    serious: 0,
    moderate: 0,
    minor: 0,
    info: 0,
  };
  for (const issue of issues) {
    const severity =
      issue.severity in result ? (issue.severity as Severity) : "info";
    result[severity] += 1;
  }
  return result;
}

export function issuePenalty(issues: readonly AuditIssue[]): number {
  return issues.reduce(
    (total, issue) => total + severityRank(issue.severity) * 2,
    0,
  );
}

export function contrastGrade(score: number): string {
  if (score >= 95) return "A";
  if (score >= 85) return "B";
  if (score >= 70) return "C";
  if (score >= 50) return "D";
  return "F";
}

export function contrastStatus(
  pair: Pick<ColorPairPayload, "passed" | "required" | "ratio">,
  level = "AA",
): "pass" | "fail" | "unknown" {
  if (!WCAG_LEVELS.includes(level)) return "unknown";
  if (pair.passed && pair.ratio >= pair.required) return "pass";
  return "fail";
}

export function normalizeKey(value: string): string {
  const key = value.trim().toLowerCase();
  return KEY_ALIASES[key] ?? key;
}

export function parseBinding(value: string | readonly string[]): string[] {
  const parts =
    typeof value === "string"
      ? value
          .trim()
          .split(/\s*\+\s*|\s+/)
          .filter(Boolean)
      : [...value];
  const normalized: string[] = [];
  for (const part of parts) {
    const key = normalizeKey(part);
    if (key && !normalized.includes(key)) normalized.push(key);
  }
  const modifiers = MODIFIER_ORDER.filter((key) => normalized.includes(key));
  const keys = normalized.filter((key) => !MODIFIER_ORDER.includes(key));
  return [...modifiers, ...keys];
}

export function normalizeBinding(value: string | readonly string[]): string {
  return parseBinding(value).join("+");
}

export function formatBinding(
  value: string | readonly string[],
  platform: Platform,
): string {
  const keys = parseBinding(value);
  if (keys.length === 0) return "—";
  if (platform === "mac") {
    return keys
      .map((key) => MAC_KEY_LABELS[key] ?? key.toUpperCase())
      .join("+");
  }
  return keys
    .map((key) => {
      const label = MAC_KEY_LABELS[key];
      if (label && key.length > 1)
        return key.charAt(0).toUpperCase() + key.slice(1);
      if (key.length === 1) return key.toUpperCase();
      return key.charAt(0).toUpperCase() + key.slice(1);
    })
    .join("+");
}

export function bindingId(value: string | readonly string[]): string {
  return normalizeBinding(value);
}

export function shortcutId(shortcut: ShortcutBinding): string {
  return `${shortcut.scope}::${shortcut.action}`;
}

export function findBindingConflicts(
  shortcuts: readonly ShortcutBinding[],
): Array<{ first: string; second: string; binding: string }> {
  const conflicts: Array<{ first: string; second: string; binding: string }> =
    [];
  for (let firstIndex = 0; firstIndex < shortcuts.length; firstIndex += 1) {
    const first = shortcuts[firstIndex];
    for (
      let secondIndex = firstIndex + 1;
      secondIndex < shortcuts.length;
      secondIndex += 1
    ) {
      const second = shortcuts[secondIndex];
      const overlap =
        first.scope === "global" ||
        second.scope === "global" ||
        first.scope === second.scope;
      if (!overlap) continue;
      if (bindingId(first.keys) !== bindingId(second.keys)) continue;
      conflicts.push({
        first: shortcutId(first),
        second: shortcutId(second),
        binding: bindingId(first.keys),
      });
    }
  }
  return conflicts;
}

export function groupShortcuts(
  shortcuts: readonly ShortcutBinding[],
): Record<string, ShortcutBinding[]> {
  const groups: Record<string, ShortcutBinding[]> = {};
  for (const shortcut of shortcuts) {
    const group = shortcut.scope || "global";
    if (!groups[group]) groups[group] = [];
    groups[group].push(shortcut);
  }
  for (const [key, items] of Object.entries(groups)) {
    groups[key] = [...items].sort((first, second) =>
      first.label.localeCompare(second.label),
    );
  }
  return groups;
}

export function filterShortcuts(
  shortcuts: readonly ShortcutBinding[],
  query: string,
): ShortcutBinding[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...shortcuts];
  return shortcuts.filter(
    (shortcut) =>
      shortcut.label.toLowerCase().includes(needle) ||
      shortcut.action.toLowerCase().includes(needle) ||
      shortcut.description.toLowerCase().includes(needle) ||
      bindingId(shortcut.keys).includes(needle),
  );
}

export function sortThemes(themes: readonly ThemeOption[]): ThemeOption[] {
  return [...themes].sort((first, second) =>
    first.label.localeCompare(second.label),
  );
}

export function matchLocale(
  requested: string,
  available: readonly string[],
): string {
  const normalized = normalizeLocaleTag(requested);
  if (available.includes(normalized)) return normalized;
  const language = languageOf(normalized);
  const languageMatch = available.find((item) => languageOf(item) === language);
  return languageMatch ?? available[0] ?? "en";
}

export function cssVarName(token: string): string {
  return `--a11y-${token
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")}`;
}

export function sanitizeCssValue(value: string): string {
  return value.trim().replace(/[;{}]/g, "");
}

export function themeToCss(
  theme: Pick<ThemeDefinitionPayloadLike, "tokens">,
  selector = ":root",
): string {
  const lines = Object.entries(theme.tokens)
    .sort(([first], [second]) => first.localeCompare(second))
    .map(
      ([token, value]) => `  ${cssVarName(token)}: ${sanitizeCssValue(value)};`,
    );
  return `${selector} {\n${lines.join("\n")}\n}`;
}

export function paletteFromTheme(
  theme: Pick<ThemeDefinitionPayloadLike, "tokens">,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(theme.tokens).map(([token, value]) => [
      token,
      sanitizeCssValue(value),
    ]),
  );
}

interface ThemeDefinitionPayloadLike {
  name: string;
  label: string;
  mode: string;
  tokens: Record<string, string>;
  description?: string;
  extends?: string;
  accent_hue?: number;
}

export function mergePreferences(
  current: A11yPreferences,
  patch: Partial<A11yPreferences>,
  timestamp = new Date().toISOString(),
): A11yPreferences {
  const next: A11yPreferences = {
    locale: patch.locale ? normalizeLocaleTag(patch.locale) : current.locale,
    theme: patch.theme ? normalizeThemeName(patch.theme) : current.theme,
    direction: patch.direction ?? current.direction,
    font_scale:
      patch.font_scale === undefined
        ? current.font_scale
        : clampFontScale(patch.font_scale),
    reduce_motion: patch.reduce_motion ?? current.reduce_motion,
    high_contrast: patch.high_contrast ?? current.high_contrast,
    screen_reader_hints:
      patch.screen_reader_hints ?? current.screen_reader_hints,
    focus_ring_boost: patch.focus_ring_boost ?? current.focus_ring_boost,
    shortcuts: patch.shortcuts
      ? Object.fromEntries(
          Object.entries(patch.shortcuts).map(([action, keys]) => [
            action,
            parseBinding(keys),
          ]),
        )
      : { ...current.shortcuts },
    updated_at: timestamp,
    revision: current.revision + 1,
  };
  return next;
}

export function preferenceSignature(preferences: A11yPreferences): string {
  const source = [
    preferences.locale,
    preferences.theme,
    preferences.direction,
    preferences.font_scale.toFixed(3),
    String(preferences.reduce_motion),
    String(preferences.high_contrast),
    String(preferences.screen_reader_hints),
    String(preferences.focus_ring_boost),
    Object.entries(preferences.shortcuts)
      .sort(([first], [second]) => first.localeCompare(second))
      .map(([action, keys]) => `${action}=${bindingId(keys)}`)
      .join(","),
  ].join("|");
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash = Math.imul(hash ^ source.charCodeAt(index), 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function focusStepLabel(step: FocusStep): string {
  const detail = step.description || step.target || step.tag;
  return `${step.order}. ${detail}${step.hidden ? " (hidden)" : ""}`;
}

export function sortFocusSteps(steps: readonly FocusStep[]): FocusStep[] {
  return [...steps].sort(
    (first, second) =>
      first.tab_index - second.tab_index || first.order - second.order,
  );
}

export function truncateText(value: string, maximum: number): string {
  if (value.length <= maximum) return value;
  if (maximum <= 1) return value.slice(0, maximum);
  return `${value.slice(0, maximum - 1)}…`;
}

export function trimAnnouncements(
  announcements: readonly Announcement[],
): Announcement[] {
  return [...announcements].slice(-ANNOUNCEMENT_LIMIT);
}

export function createAnnouncement(
  message: string,
  politeness: Announcement["politeness"] = "polite",
  id: string = `a11y-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
): Announcement {
  return { id, message, politeness, timestamp: Date.now() };
}

export function normalizeSuggestions(values: readonly string[]): string[] {
  const unique = [
    ...new Set(values.map((value) => value.trim()).filter(Boolean)),
  ];
  return unique
    .sort((first, second) => first.localeCompare(second))
    .slice(0, MAX_SUGGESTIONS);
}

export function mirrorPunctuation(value: string): string {
  const mirrored: Record<string, string> = {
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
    "<": ">",
    ">": "<",
  };
  return [...value]
    .map((character) => mirrored[character] ?? character)
    .join("");
}

export function isolateBidiText(
  value: string,
  direction: ResolvedDirection,
): string {
  if (direction !== "rtl") return value;
  return `\u2068${value}\u2069`;
}

export function bidiWarnings(value: string): string[] {
  const warnings: string[] = [];
  const opens = (value.match(/[([{<]/g) ?? []).length;
  const closes = (value.match(/[\])>}]/g) ?? []).length;
  if (opens !== closes) warnings.push("Unbalanced brackets");
  if (/\d/.test(value) && /[\p{L}]/u.test(value))
    warnings.push("Mixed digits and letters");
  return warnings;
}

export function reverseTextRuns(value: string): string {
  return value.split(/\s+/).reverse().join(" ");
}
