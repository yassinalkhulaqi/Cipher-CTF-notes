import type {
  EvidenceFilters,
  EvidenceKind,
  EvidenceStatus,
  EvidenceSummary,
  IntegrityReport,
  ManifestEntry,
} from "./types";

const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

export const DEFAULT_FILTERS: EvidenceFilters = {
  query: "",
  tag: "",
  hashPrefix: "",
  status: "",
  kind: "",
  sort: "created_at",
  direction: "desc",
};

export const STATUS_LABELS: Record<EvidenceStatus, string> = {
  discovered: "Discovered",
  acquired: "Acquired",
  analyzed: "Analyzed",
  verified: "Verified",
  sealed: "Sealed",
  archived: "Archived",
  disposed: "Disposed",
};

export const KIND_LABELS: Record<EvidenceKind, string> = {
  document: "Document",
  image: "Image",
  video: "Video",
  audio: "Audio",
  log: "Log",
  database: "Database",
  disk_image: "Disk image",
  archive: "Archive",
  email: "Email",
  other: "Other",
};

export const INTEGRITY_LABELS: Record<string, string> = {
  verified: "Verified",
  unverified: "Unverified",
  missing: "Missing",
  mismatch: "Mismatch",
  error: "Error",
};

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value === 0) return "0 B";
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < UNITS.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  const precision = amount < 10 && unit > 0 ? 1 : 0;
  const text = amount.toFixed(precision).replace(/\.0$/, "");
  return `${text} ${UNITS[unit]}`;
}

export function formatTimestamp(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatDate(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(date);
}

export function maskHash(value: string): string {
  if (value.length <= 16) return value;
  return `${value.slice(0, 8)}…${value.slice(-8)}`;
}

export function statusLabel(value: string): string {
  return STATUS_LABELS[value as EvidenceStatus] ?? value;
}

export function kindLabel(value: string): string {
  return KIND_LABELS[value as EvidenceKind] ?? value;
}

export function integrityLabel(value: string): string {
  return INTEGRITY_LABELS[value] ?? value;
}

export function integrityTone(report: IntegrityReport | undefined): string {
  if (!report) return "neutral";
  if (report.state === "verified") return "good";
  if (report.state === "missing" || report.state === "mismatch") return "bad";
  return "warn";
}

export function issueSummary(report: IntegrityReport | undefined): string {
  if (!report) return "Not checked";
  if (report.state === "verified") return "Digest and custody checks passed";
  const issues = report.issues;
  if (issues.length === 0) return "No additional details";
  return issues
    .map((issue) => (typeof issue === "string" ? issue : issue.message))
    .join(", ");
}

export function parseTags(value: string): string[] {
  return value
    .split(/[\s,;]+/)
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)
    .filter((tag, index, tags) => tags.indexOf(tag) === index)
    .slice(0, 32);
}

export function tagText(tags: readonly string[]): string {
  return tags.join(", ");
}

export function matchesFilters(
  item: EvidenceSummary,
  filters: EvidenceFilters,
): boolean {
  const query = filters.query.trim().toLowerCase();
  if (query) {
    const haystack = [
      item.title,
      item.original_filename,
      item.sha256,
      item.md5,
      ...item.tags,
    ]
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(query)) return false;
  }
  if (
    filters.tag &&
    !item.tags.some((tag) => tag.toLowerCase() === filters.tag.toLowerCase())
  ) {
    return false;
  }
  if (
    filters.hashPrefix &&
    !item.sha256.startsWith(filters.hashPrefix.toLowerCase())
  ) {
    return false;
  }
  if (filters.status && item.status !== filters.status) return false;
  if (filters.kind && item.kind !== filters.kind) return false;
  return true;
}

export function compareSummaries(
  left: EvidenceSummary,
  right: EvidenceSummary,
  filters: EvidenceFilters,
): number {
  const direction = filters.direction === "asc" ? 1 : -1;
  let result = 0;
  switch (filters.sort) {
    case "title":
      result = left.title.localeCompare(right.title);
      break;
    case "size_bytes":
      result = left.size_bytes - right.size_bytes;
      break;
    case "updated_at":
      result = left.updated_at.localeCompare(right.updated_at);
      break;
    default:
      result = left.created_at.localeCompare(right.created_at);
  }
  return result === 0 ? left.id.localeCompare(right.id) : result * direction;
}

export function filterSummaries(
  items: readonly EvidenceSummary[],
  filters: EvidenceFilters,
): EvidenceSummary[] {
  return items
    .filter((item) => matchesFilters(item, filters))
    .sort((a, b) => compareSummaries(a, b, filters));
}

export function allTags(items: readonly EvidenceSummary[]): string[] {
  const tags = new Set<string>();
  for (const item of items) for (const tag of item.tags) tags.add(tag);
  return [...tags].sort((a, b) => a.localeCompare(b));
}

export function manifestEntryLabel(entry: ManifestEntry): string {
  return entry.filename || entry.evidence_id;
}

export function truncateMiddle(value: string, max = 48): string {
  if (value.length <= max) return value;
  const half = Math.floor((max - 1) / 2);
  return `${value.slice(0, half)}…${value.slice(-half)}`;
}

export function countByStatus(
  items: readonly EvidenceSummary[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items)
    counts[item.status] = (counts[item.status] ?? 0) + 1;
  return counts;
}

export function totalBytes(items: readonly EvidenceSummary[]): number {
  return items.reduce((sum, item) => sum + item.size_bytes, 0);
}

export function isTerminalStatus(status: string): boolean {
  return status === "disposed" || status === "archived";
}

export function canVerify(status: string): boolean {
  return status !== "disposed";
}

export function canDelete(status: string): boolean {
  return status !== "disposed";
}

export function normalizeHexPrefix(value: string, length = 64): string {
  const clean = value
    .trim()
    .toLowerCase()
    .replace(/[^0-9a-f]/g, "");
  return clean.slice(0, length);
}

export function previewText(kind: string): string {
  const labels: Record<string, string> = {
    text: "Text preview",
    image: "Image preview",
    pdf: "PDF preview",
    video: "Video preview",
    audio: "Audio preview",
    icon: "No preview",
  };
  return labels[kind] ?? "Preview";
}
