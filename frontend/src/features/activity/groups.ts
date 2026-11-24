/** Client-side grouping and selection helpers for activity entries. */

import type {
  ActivityEntry,
  DateGroup,
  DigestPeriod,
  FilterChipData,
  JumpTarget,
  StreamResult,
} from "./types";

export function sortEntries(entries: ActivityEntry[]): ActivityEntry[] {
  return [...entries].sort((left, right) => right.sequence - left.sequence);
}

export function groupEntries(
  entries: ActivityEntry[],
  period: DigestPeriod = "daily",
): DateGroup[] {
  const buckets = new Map<string, ActivityEntry[]>();
  for (const entry of sortEntries(entries)) {
    const key = period === "weekly" ? entry.week_key || entry.date_key : entry.date_key;
    const bucket = buckets.get(key) ?? [];
    bucket.push(entry);
    buckets.set(key, bucket);
  }
  return Array.from(buckets.entries())
    .sort(([left], [right]) => right.localeCompare(left))
    .map(([key, bucket]) => ({
      key,
      label: bucket[0]?.iso_timestamp.slice(0, 10) ?? key,
      period,
      count: bucket.length,
      entries: bucket,
    }));
}

export function uniqueValues(entries: ActivityEntry[], key: "kind" | "actor" | "subject_ref"): string[] {
  return Array.from(new Set(entries.map((entry) => entry[key]).filter(Boolean))).sort();
}

export function jumpTargets(entries: ActivityEntry[]): JumpTarget[] {
  return entries.flatMap((entry) => (entry.jump?.resolvable ? [entry.jump] : []));
}

export function findEntry(entries: ActivityEntry[], sequence: number): ActivityEntry | undefined {
  return entries.find((entry) => entry.sequence === sequence);
}

function matchesChip(entry: ActivityEntry, chip: FilterChipData): boolean {
  const value = chip.value.toLowerCase();
  let matched = false;
  switch (chip.key) {
    case "kind":
      matched = entry.kind.toLowerCase() === value;
      break;
    case "actor":
      matched = entry.actor.toLowerCase() === value;
      break;
    case "subject":
      matched = entry.subject_ref.toLowerCase() === value;
      break;
    case "severity":
      matched = entry.severity.toLowerCase() === value;
      break;
    case "tag":
      matched = (entry.tags ?? []).some((tag) => tag.toLowerCase() === value);
      break;
    case "text":
      matched = JSON.stringify(entry).toLowerCase().includes(value);
      break;
    default:
      matched = true;
  }
  return chip.operator === "exclude" ? !matched : matched;
}

export function filterEntriesByChips(
  entries: ActivityEntry[],
  chips: FilterChipData[],
): ActivityEntry[] {
  if (!chips.length) return sortEntries(entries);
  return sortEntries(entries.filter((entry) => chips.every((chip) => matchesChip(entry, chip))));
}

export function mergeStreams(first: StreamResult, second: StreamResult): StreamResult {
  const entries = sortEntries([...first.entries, ...second.entries]);
  return {
    ...first,
    entries,
    total: Math.max(first.total, second.total),
    groups: groupEntries(entries),
    warnings: [...first.warnings, ...second.warnings],
  };
}

export function pageSlice(entries: ActivityEntry[], size: number, page: number): ActivityEntry[] {
  const safeSize = Math.max(1, size);
  const safePage = Math.max(1, page);
  return sortEntries(entries).slice((safePage - 1) * safeSize, safePage * safeSize);
}

export function countByKind(entries: ActivityEntry[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const entry of entries) counts[entry.kind] = (counts[entry.kind] ?? 0) + 1;
  return counts;
}
