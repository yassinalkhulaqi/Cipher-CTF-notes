/** Pure presentation helpers for the report designer. */

import type {
  FindingItem,
  LayoutSection,
  PaginationPlan,
  RedactionPreview,
  RenderFormat,
  Severity,
  ThemeSummary,
  TocEntry,
} from "./types";

export const ZOOM_LEVELS = [50, 75, 100, 125, 150] as const;
export const FORMAT_LABELS: Record<RenderFormat, string> = {
  html: "HTML",
  markdown: "Markdown",
  json: "JSON",
  print: "Print CSS",
};
const SEVERITY_RANK: Record<Severity, number> = {
  info: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};
const SEVERITY_LABEL: Record<Severity, string> = {
  info: "Informational",
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export function clampZoom(value: number): number {
  if (!Number.isFinite(value)) return 100;
  return ZOOM_LEVELS.reduce<number>(
    (best, level) =>
      Math.abs(level - value) < Math.abs(best - value) ? level : best,
    100,
  );
}

export function zoomStep(value: number, delta: number): number {
  const current = ZOOM_LEVELS.indexOf(
    clampZoom(value) as (typeof ZOOM_LEVELS)[number],
  );
  const next = Math.min(
    ZOOM_LEVELS.length - 1,
    Math.max(0, current + Math.sign(delta)),
  );
  return ZOOM_LEVELS[next];
}

export function zoomLabel(value: number): string {
  return `${clampZoom(value)}%`;
}

export function zoomScale(value: number): number {
  return clampZoom(value) / 100;
}

export function severityRank(value: Severity): number {
  return SEVERITY_RANK[value] ?? 0;
}

export function severityLabel(value: Severity): string {
  return SEVERITY_LABEL[value] ?? value;
}

export function severityClass(value: Severity): string {
  return `rd-sev-${value}`;
}

export function pageLabel(index: number, total: number): string {
  if (index < 1 || total < 1) return "Page —";
  return `Page ${index} of ${total}`;
}

export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function kindLabel(kind: string): string {
  return kind
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

export function truncate(text: string, max: number): string {
  if (max < 1) return "";
  return text.length <= max
    ? text
    : `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

export function parseList(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[,\n]/)
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  );
}

export function visibleSectionCount(sections: LayoutSection[]): number {
  return sections.reduce(
    (total, section) =>
      total + (section.visible ? 1 : 0) + visibleSectionCount(section.children),
    0,
  );
}

export function countFindings(findings: FindingItem[]): number {
  return findings.length;
}

export function countSectionFindings(sections: LayoutSection[]): number {
  return sections.reduce(
    (total, section) =>
      total + section.findings.length + countSectionFindings(section.children),
    0,
  );
}

export function tocLine(entry: TocEntry, totalPages: number): string {
  const indent = "  ".repeat(Math.max(0, entry.level - 1));
  return `${indent}${entry.title} — ${pageLabel(entry.page, totalPages)}`;
}

export function redactionSummary(preview: RedactionPreview): string {
  if (preview.total_matches === 0) return "No matches";
  const rules = preview.applied.join(", ");
  return `${preview.total_matches} match${preview.total_matches === 1 ? "" : "es"} · ${rules}`;
}

export function themeSwatch(theme: ThemeSummary | undefined): string {
  return theme ? "var(--v3-kind-report)" : "var(--v3-kind-default)";
}

export function sortedThemeKeys(themes: ThemeSummary[]): string[] {
  return themes.map((theme) => theme.key).sort((a, b) => a.localeCompare(b));
}

export function paginationStats(plan: PaginationPlan): {
  pages: number;
  items: number;
  fills: number;
} {
  const items = plan.pages.reduce(
    (total, page) => total + page.items.length,
    0,
  );
  const fills = plan.pages.length
    ? plan.pages.reduce((total, page) => total + page.used_lines, 0) /
      (plan.pages.length * Math.max(1, plan.lines_per_page))
    : 0;
  return {
    pages: plan.total_pages,
    items,
    fills: Math.round(fills * 100) / 100,
  };
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.keys(record)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = stableValue(record[key]);
        return acc;
      }, {});
  }
  return value;
}

export function designSignature(value: unknown): string {
  return JSON.stringify(stableValue(value));
}
