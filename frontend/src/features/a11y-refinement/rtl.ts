/** RTL layout metadata helpers for V3 panes. */

import { localeDirection, normalizeLocale } from "./catalogs";
import type { LayoutManifestView, PaneLayoutView } from "./types";

export const PANE_REGIONS: Record<string, string[]> = {
  "command-center": ["rail", "activity", "quick-actions", "metrics"],
  "finding-studio": ["list", "editor", "cvss", "remediation"],
  "evidence-lab": ["table", "preview", "hex", "custody"],
  "graph-workbench": ["toolbar", "canvas", "inspector", "legend"],
  "search-intelligence": ["query", "facets", "results", "cluster"],
  "playbook-automation": ["templates", "steps", "variables", "trace"],
  "report-designer": ["outline", "page", "theme", "appendix"],
  timeline: ["filters", "stream", "detail", "pagination"],
  sync: ["sources", "preview", "conflicts", "progress"],
  security: ["risks", "audit", "redaction", "keys"],
  performance: ["hud", "budgets", "fixtures", "plans"],
  "a11y-refinement": ["audit", "contrast", "keyboard", "preferences"],
};

export const MIRRORED_ICONS = [
  "chevron-left",
  "chevron-right",
  "arrow-left",
  "arrow-right",
  "back",
  "forward",
  "indent",
  "outdent",
  "sidebar-toggle",
  "panel-toggle",
];

export function resolveDirection(locale: string, override?: string): "ltr" | "rtl" {
  if (override === "ltr" || override === "rtl") return override;
  return localeDirection(locale) === "rtl" ? "rtl" : "ltr";
}

export function sidesFor(direction: "ltr" | "rtl"): Record<string, string> {
  return direction === "rtl"
    ? { start: "right", end: "left", top: "top", bottom: "bottom" }
    : { start: "left", end: "right", top: "top", bottom: "bottom" };
}

export function layoutFor(pane: string, locale: string, override?: string): PaneLayoutView {
  const direction = resolveDirection(locale, override);
  const regions = PANE_REGIONS[pane] ?? ["content"];
  return {
    pane,
    direction,
    css_class: `v3-rtl-${direction}`,
    sides: sidesFor(direction),
    mirror_icons: direction === "rtl" ? [...MIRRORED_ICONS] : [],
    ordered_regions: direction === "rtl" ? [...regions].reverse() : [...regions],
    warnings: [],
  };
}

export function cssVariables(locale: string, override?: string): Record<string, string> {
  const direction = resolveDirection(locale, override);
  return {
    "--v3-dir": direction,
    "--v3-inline-start": direction === "rtl" ? "right" : "left",
    "--v3-inline-end": direction === "rtl" ? "left" : "right",
    "--v3-text-align": direction === "rtl" ? "right" : "left",
    "--v3-transform": direction === "rtl" ? "scaleX(-1)" : "none",
    "--v3-panel-order": direction,
  };
}

export function layoutManifest(locale: string, override?: string): LayoutManifestView {
  const direction = resolveDirection(locale, override);
  const panes = Object.keys(PANE_REGIONS).sort().map((pane) => layoutFor(pane, locale, override));
  return {
    locale: normalizeLocale(locale),
    direction,
    rtl: direction === "rtl",
    css: cssVariables(locale, override),
    regions: direction === "rtl" ? [...Object.keys(PANE_REGIONS)].reverse() : Object.keys(PANE_REGIONS),
    panes,
    static_icons: ["search", "save", "settings", "close", "check"],
    mirrored_icons: direction === "rtl" ? [...MIRRORED_ICONS] : [],
    warnings: [],
  };
}

export function validateLayout(layout: PaneLayoutView): { valid: boolean; problems: string[] } {
  const problems: string[] = [];
  if (layout.ordered_regions.length === 0) problems.push("pane has no regions");
  if (layout.direction === "rtl" && layout.sides.start !== "right") problems.push("RTL start is not right");
  if (layout.direction === "ltr" && layout.sides.start !== "left") problems.push("LTR start is not left");
  if (layout.css_class !== `v3-rtl-${layout.direction}`) problems.push("unexpected direction class");
  return { valid: problems.length === 0, problems };
}

export function documentAttributes(locale: string, override?: string): Record<string, string> {
  return { lang: normalizeLocale(locale), dir: resolveDirection(locale, override) };
}

export function paneNames(): string[] {
  return Object.keys(PANE_REGIONS).sort();
}

export function warningForText(text: string, locale: string): string {
  const rtl = localeDirection(locale) === "rtl";
  const hasLatin = /[A-Za-z]/.test(text);
  const hasRtl = /[\u0590-\u06ff]/.test(text);
  if (rtl && hasLatin && hasRtl) return "isolate embedded Latin text";
  if (!rtl && hasRtl) return "isolate embedded RTL text";
  return "";
}
