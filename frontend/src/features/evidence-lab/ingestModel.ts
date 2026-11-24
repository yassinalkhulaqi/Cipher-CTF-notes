/** Validation and queue model for the drag-and-drop ingest strip. */

import type {
  EvidenceReportData,
  IngestItem,
  IngestPhase,
  IntegrityBadgeData,
} from "./types";
import { formatBytes } from "./format";

export const DEFAULT_MAX_INGEST_BYTES = 512 * 1024 * 1024;

export const INGEST_EXTENSIONS = [
  "png",
  "jpg",
  "jpeg",
  "gif",
  "pdf",
  "zip",
  "gz",
  "xz",
  "7z",
  "elf",
  "bin",
  "exe",
  "txt",
  "log",
  "json",
  "csv",
  "db",
  "sqlite",
  "pcap",
] as const;

export interface IngestFileLike {
  name: string;
  size: number;
  type?: string;
}

export interface RejectedDrop {
  file: IngestFileLike;
  reason: string;
}

export interface DropValidation {
  accepted: IngestFileLike[];
  rejected: RejectedDrop[];
}

export function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index < 0 ? "" : name.slice(index + 1).toLowerCase();
}

export function validateDrop(
  files: readonly IngestFileLike[],
  maxBytes = DEFAULT_MAX_INGEST_BYTES,
  acceptedExtensions: readonly string[] = INGEST_EXTENSIONS,
): DropValidation {
  const accepted: IngestFileLike[] = [];
  const rejected: RejectedDrop[] = [];
  for (const file of files) {
    if (!file.name || file.name.trim() === "") {
      rejected.push({ file, reason: "Missing filename" });
      continue;
    }
    if (file.size <= 0) {
      rejected.push({ file, reason: "Empty file" });
      continue;
    }
    if (file.size > maxBytes) {
      rejected.push({ file, reason: `Exceeds ${formatBytes(maxBytes)} limit` });
      continue;
    }
    const extension = extensionOf(file.name);
    if (extension && !acceptedExtensions.includes(extension)) {
      rejected.push({ file, reason: `Unsupported .${extension}` });
      continue;
    }
    accepted.push(file);
  }
  return { accepted, rejected };
}

export function createIngestItem(file: File, index: number): IngestItem {
  return {
    id: `ingest-${index}-${file.name}-${file.size}`,
    file,
    phase: "queued",
    report: null,
    message: "Queued",
    progress: 0,
  };
}

export function updateIngestItem(
  items: readonly IngestItem[],
  id: string,
  patch: Partial<IngestItem>,
): IngestItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export function dedupeIngest(
  items: readonly IngestItem[],
  incoming: readonly IngestItem[],
): IngestItem[] {
  const seen = new Set(items.map((item) => item.id));
  return [...items, ...incoming.filter((item) => !seen.has(item.id))];
}

export function ingestCounts(
  items: readonly IngestItem[],
): Record<IngestPhase, number> {
  const counts: Record<IngestPhase, number> = {
    queued: 0,
    reading: 0,
    inspecting: 0,
    verified: 0,
    mismatch: 0,
    rejected: 0,
  };
  for (const item of items) counts[item.phase] += 1;
  return counts;
}

export function isTerminal(phase: IngestPhase): boolean {
  return phase === "verified" || phase === "mismatch" || phase === "rejected";
}

export function phaseTone(
  phase: IngestPhase,
): "good" | "warn" | "bad" | "neutral" {
  if (phase === "verified") return "good";
  if (phase === "mismatch" || phase === "rejected") return "bad";
  if (phase === "reading" || phase === "inspecting") return "warn";
  return "neutral";
}

export function badgeFromReport(
  report: EvidenceReportData | null,
): IntegrityBadgeData | null {
  return report?.badge ?? null;
}

export function ingestProgressLabel(item: IngestItem): string {
  if (item.phase === "queued") return "Queued";
  if (item.phase === "reading")
    return `Reading ${Math.round(item.progress * 100)}%`;
  if (item.phase === "inspecting") return "Hashing & classifying";
  if (item.phase === "verified") return "Integrity verified";
  if (item.phase === "mismatch") return item.message || "Integrity mismatch";
  return item.message || "Rejected";
}

export function totalIngestBytes(items: readonly IngestItem[]): number {
  return items.reduce((total, item) => total + item.file.size, 0);
}
