/** Contrast automation helpers for the refined V3 surfaces. */

import { contrastRatio, suggestedForeground } from "../../a11y/contrast";
import type { ContrastFixView, ContrastPairView, ContrastReportView, WcagLevel } from "./types";

const LIGHT = "#ffffff";
const DARK = "#000000";

export function requiredRatio(
  level: WcagLevel,
  options: { graphical?: boolean; largeText?: boolean } = {},
): number {
  const graphical = options.graphical ?? false;
  const largeText = options.largeText ?? false;
  if (graphical) return 3;
  if (largeText) return level === "AAA" ? 4.5 : 3;
  return level === "AAA" ? 7 : 4.5;
}

export function isLargeText(fontSize: number, bold = false): boolean {
  return fontSize >= 24 || (bold && fontSize >= 18.66);
}

export function evaluatePair(input: {
  name: string;
  foreground: string;
  background: string;
  font_size?: number;
  bold?: boolean;
  graphical?: boolean;
  level?: WcagLevel;
}): ContrastPairView {
  const fontSize = input.font_size ?? 16;
  const bold = input.bold ?? false;
  const graphical = input.graphical ?? false;
  const level = input.level ?? "AA";
  const largeText = isLargeText(fontSize, bold);
  const ratio = contrastRatio(input.foreground, input.background);
  const required = requiredRatio(level, { graphical, largeText });
  return {
    name: input.name,
    foreground: input.foreground,
    background: input.background,
    ratio: Math.round(ratio * 1000) / 1000,
    required,
    passed: ratio >= required,
    large_text: largeText,
    graphical,
    level,
  };
}

export function suggestFix(pair: ContrastPairView): ContrastFixView {
  const candidate = suggestedForeground(pair.background);
  const blackRatio = contrastRatio(DARK, pair.background);
  const whiteRatio = contrastRatio(LIGHT, pair.background);
  const foreground =
    contrastRatio(candidate, pair.background) >= pair.required
      ? candidate
      : blackRatio >= whiteRatio
        ? DARK
        : LIGHT;
  const after = contrastRatio(foreground, pair.background);
  return {
    name: pair.name,
    before: pair.ratio,
    after: Math.round(after * 1000) / 1000,
    required: pair.required,
    foreground,
    background: pair.background,
    direction: "foreground",
  };
}

export function buildContrastReport(pairs: ContrastPairView[], repair = true): ContrastReportView {
  const failures = pairs.filter((pair) => !pair.passed);
  const fixes = repair ? failures.map(suggestFix) : [];
  const score = pairs.length ? ((pairs.length - failures.length) / pairs.length) * 100 : 100;
  return {
    pairs,
    failures,
    fixes,
    suggestions: fixes.map(
      (fix) => `${fix.name}: set foreground to ${fix.foreground} (${fix.after}:1)`,
    ),
    level: pairs[0]?.level ?? "AA",
    score: Math.round(score * 10) / 10,
    passed: failures.length === 0,
  };
}

export function contrastTone(score: number): "good" | "warn" | "bad" {
  if (score === 100) return "good";
  if (score >= 70) return "warn";
  return "bad";
}

export function formatRatio(value: number): string {
  return `${value.toFixed(2)}:1`;
}

export function pairLabel(pair: ContrastPairView): string {
  return `${pair.name} · ${formatRatio(pair.ratio)} / ${formatRatio(pair.required)}`;
}

export function failureNames(report: ContrastReportView): string[] {
  return report.failures.map((pair) => pair.name);
}

export function applyFixToPairs(
  pairs: ContrastPairView[],
  fix: ContrastFixView,
): ContrastPairView[] {
  return pairs.map((pair) =>
    pair.name === fix.name ? { ...pair, foreground: fix.foreground, ratio: fix.after, passed: fix.after >= fix.required } : pair,
  );
}

export function applyAllFixes(report: ContrastReportView): ContrastReportView {
  const pairs = report.fixes.reduce(applyFixToPairs, report.pairs);
  return buildContrastReport(pairs, false);
}

export function mergeThemeReports(
  light: ContrastReportView,
  dark: ContrastReportView,
): { equivalent: boolean; shared: string[]; score: number; passed: boolean } {
  const lightNames = new Set(failureNames(light));
  const darkNames = new Set(failureNames(dark));
  const shared = [...lightNames].filter((name) => darkNames.has(name)).sort();
  return {
    equivalent: lightNames.size === darkNames.size && shared.length === lightNames.size,
    shared,
    score: Math.round(((light.score + dark.score) / 2) * 10) / 10,
    passed: light.passed && dark.passed,
  };
}
