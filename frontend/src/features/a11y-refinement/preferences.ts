/** Unified theme/motion control and preference synchronization helpers. */

import type {
  Direction,
  MotionMode,
  PreferenceRecordView,
  PreferenceSnapshotView,
  SyncReportView,
  UnifiedAppearanceView,
} from "./types";

export const MOTION_DURATIONS: Record<MotionMode, Record<string, string>> = {
  full: { fast: "120ms", normal: "220ms", slow: "360ms" },
  reduced: { fast: "1ms", normal: "1ms", slow: "1ms" },
  off: { fast: "0ms", normal: "0ms", slow: "0ms" },
};

export const DEFAULT_APPEARANCE: UnifiedAppearanceView = {
  theme: "graphite",
  motion: "full",
  density: "comfortable",
  direction: "auto",
  font_scale: 1,
  high_contrast: false,
  focus_ring_boost: false,
};

export function clampScale(value: number): number {
  return Math.min(1.75, Math.max(0.75, Math.round(value * 100) / 100));
}

export function motionEquivalence(mode: MotionMode): {
  mode: MotionMode;
  durations: Record<string, string>;
  contentHidden: boolean;
  focusOrderPreserved: boolean;
} {
  return {
    mode,
    durations: { ...MOTION_DURATIONS[mode] },
    contentHidden: false,
    focusOrderPreserved: true,
  };
}

export function appearanceFromSnapshot(
  snapshot: PreferenceSnapshotView,
): UnifiedAppearanceView {
  const marker = snapshot.shortcuts["v3.motion_mode"] ?? [];
  const motion: MotionMode = marker.includes("off")
    ? "off"
    : snapshot.reduce_motion
      ? "reduced"
      : "full";
  return {
    theme: snapshot.theme,
    motion,
    density: snapshot.focus_ring_boost ? "compact" : "comfortable",
    direction: snapshot.direction,
    font_scale: clampScale(snapshot.font_scale),
    high_contrast: snapshot.high_contrast,
    focus_ring_boost: snapshot.focus_ring_boost,
  };
}

export function snapshotWithAppearance(
  snapshot: PreferenceSnapshotView,
  appearance: UnifiedAppearanceView,
): PreferenceSnapshotView {
  const shortcuts = { ...snapshot.shortcuts };
  if (appearance.motion === "off") shortcuts["v3.motion_mode"] = ["off"];
  else delete shortcuts["v3.motion_mode"];
  return {
    ...snapshot,
    theme: appearance.theme,
    direction: appearance.direction,
    font_scale: clampScale(appearance.font_scale),
    reduce_motion: appearance.motion !== "full",
    high_contrast: appearance.high_contrast,
    focus_ring_boost: appearance.focus_ring_boost,
    shortcuts,
    revision: snapshot.revision + 1,
  };
}

export function appearanceCss(
  appearance: UnifiedAppearanceView,
): Record<string, string> {
  const durations = MOTION_DURATIONS[appearance.motion];
  return {
    "--v3-theme": appearance.theme,
    "--v3-density": appearance.density,
    "--v3-direction": appearance.direction,
    "--v3-font-scale": appearance.font_scale.toFixed(2),
    "--v3-motion-fast": durations.fast,
    "--v3-motion-normal": durations.normal,
    "--v3-motion-slow": durations.slow,
    "--v3-focus-boost": appearance.focus_ring_boost ? "1" : "0",
    "--v3-contrast": appearance.high_contrast ? "high" : "normal",
  };
}

export function checksum(snapshot: PreferenceSnapshotView): string {
  const fields = [
    snapshot.locale,
    snapshot.theme,
    snapshot.direction,
    String(snapshot.font_scale),
    String(snapshot.reduce_motion),
    String(snapshot.high_contrast),
    String(snapshot.screen_reader_hints),
    String(snapshot.focus_ring_boost),
    JSON.stringify(
      Object.entries(snapshot.shortcuts).sort(([a], [b]) => a.localeCompare(b)),
    ),
  ];
  let hash = 2166136261;
  for (const char of fields.join("|")) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export interface FieldChange {
  field: string;
  local: unknown;
  remote: unknown;
}

export function preferenceDiff(
  local: PreferenceSnapshotView,
  remote: PreferenceSnapshotView,
): FieldChange[] {
  const fields: (keyof PreferenceSnapshotView)[] = [
    "locale",
    "theme",
    "direction",
    "font_scale",
    "reduce_motion",
    "high_contrast",
    "screen_reader_hints",
    "focus_ring_boost",
    "shortcuts",
  ];
  return fields
    .filter(
      (field) => JSON.stringify(local[field]) !== JSON.stringify(remote[field]),
    )
    .map((field) => ({ field, local: local[field], remote: remote[field] }));
}

export function syncTone(report: SyncReportView): "good" | "warn" | "bad" {
  if (!report.applied) return "bad";
  if (report.conflicts.length || report.warnings.length) return "warn";
  return "good";
}

export function syncSummary(report: SyncReportView): string {
  const parts = [
    `${report.strategy}`,
    `${report.changes.length} changed`,
    `${report.conflicts.length} conflicts`,
    `revision ${report.record.revision}`,
  ];
  return parts.join(" · ");
}

export function directionPreference(
  snapshot: PreferenceSnapshotView,
  locale: string,
): Direction {
  if (snapshot.direction !== "auto") return snapshot.direction;
  return ["ar", "he", "fa", "ur"].includes(locale.split("-")[0])
    ? "rtl"
    : "ltr";
}

export function recordLabel(record: PreferenceRecordView): string {
  return `${record.profile} · r${record.revision} · ${record.source}`;
}
