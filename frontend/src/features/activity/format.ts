/** Formatting helpers for activity entries, digests, and retrospectives. */

import { severityRank, severityTone } from "./filters";
import type {
  ActivityEntry,
  DensityMode,
  Digest,
  DigestPeriod,
  FacetCounts,
  RetrospectiveSummary,
} from "./types";

export const DENSITY_OPTIONS: DensityMode[] = [
  "compact",
  "comfortable",
  "detailed",
];
export const PERIOD_OPTIONS: DigestPeriod[] = ["daily", "weekly"];

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Math.max(0, Math.round(value)).toLocaleString("en-US");
}

export function truncate(value: string, length: number): string {
  if (length < 1) return "";
  const text = value.replace(/\s+/g, " ").trim();
  return text.length <= length
    ? text
    : `${text.slice(0, Math.max(0, length - 1))}…`;
}

export function shortRef(ref: string): string {
  const separator = ref.lastIndexOf(":");
  return separator >= 0 ? ref.slice(separator + 1) : ref;
}

export function relativeTime(timestamp: number, now: number): string {
  const delta = Math.max(0, Math.floor(now - timestamp));
  if (delta < MINUTE) return "just now";
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)}m ago`;
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h ago`;
  if (delta < 7 * DAY) return `${Math.floor(delta / DAY)}d ago`;
  return new Date(timestamp * 1000).toISOString().slice(0, 10);
}

export function dayKeyFromTimestamp(timestamp: number): string {
  return new Date(timestamp * 1000).toISOString().slice(0, 10);
}

export function formatDayLabel(dateKey: string, now: number): string {
  const today = dayKeyFromTimestamp(now);
  const yesterday = dayKeyFromTimestamp(now - DAY);
  if (dateKey === today) return "Today";
  if (dateKey === yesterday) return "Yesterday";
  return dateKey;
}

export function formatClock(timestamp: number): string {
  return new Date(timestamp * 1000).toISOString().slice(11, 16);
}

export function densityLabel(density: DensityMode): string {
  return density.charAt(0).toUpperCase() + density.slice(1);
}

export function periodLabel(period: DigestPeriod): string {
  return period === "daily" ? "Daily digest" : "Weekly digest";
}

export function entryTone(entry: ActivityEntry): string {
  return severityTone(entry.severity);
}

export function entryMeta(
  entry: ActivityEntry,
  density: DensityMode,
  now: number = entry.timestamp,
): string {
  const actor = `by ${entry.actor}`;
  if (density === "compact") return actor;
  const subject = entry.subject_ref ? ` · ${shortRef(entry.subject_ref)}` : "";
  return `${actor}${subject} · ${relativeTime(entry.timestamp, now)}`;
}

export function redactionNote(entry: ActivityEntry): string {
  if (!entry.redactions.length) return "";
  return `${entry.redactions.length} field${entry.redactions.length === 1 ? "" : "s"} redacted`;
}

export function digestCardData(digest: Digest): {
  title: string;
  subtitle: string;
  count: string;
  highlights: ActivityEntry[];
} {
  const kinds = Object.keys(digest.counts).sort(
    (left, right) =>
      digest.counts[right] - digest.counts[left] || left.localeCompare(right),
  );
  return {
    title: digest.label,
    subtitle: kinds.slice(0, 3).join(" · "),
    count: formatCount(digest.entry_count),
    highlights: digest.highlights,
  };
}

export function summarizeFacets(facets: FacetCounts): string {
  const kinds = Object.keys(facets.kinds).length;
  const actors = Object.keys(facets.actors).length;
  return `${formatCount(kinds)} kinds · ${formatCount(actors)} actors`;
}

export function rankedLabel(value: { value: string; count: number }): string {
  return `${value.value} (${formatCount(value.count)})`;
}

export function retrospectiveTiles(summary: RetrospectiveSummary): Array<{
  label: string;
  value: string;
}> {
  return [
    { label: "Events", value: formatCount(summary.total_events) },
    { label: "Active days", value: formatCount(summary.active_days) },
    { label: "Longest streak", value: formatCount(summary.longest_streak) },
    { label: "Busiest day", value: summary.busiest_day?.date_key ?? "—" },
  ];
}

export function severitySummary(facets: FacetCounts): string {
  return Object.keys(facets.severities)
    .sort((left, right) => severityRank(right) - severityRank(left))
    .map((key) => `${key}: ${formatCount(facets.severities[key])}`)
    .join(" · ");
}
