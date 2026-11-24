/** Row model for the evidence comparison view. */

import type { BundleDeltaData, BundleDiffData } from "./types";
import { formatSignedBytes, maskHash, deltaTone } from "./format";

export interface CompareRow {
  key: string;
  kind: BundleDeltaData["kind"];
  tone: "good" | "warn" | "bad" | "neutral";
  leftHash: string;
  rightHash: string;
  leftSize: number;
  rightSize: number;
  sizeDelta: number;
  sizeLabel: string;
}

export function changedDeltas(diff: BundleDiffData | null): BundleDeltaData[] {
  return (diff?.deltas ?? []).filter((delta) => delta.kind !== "unchanged");
}

export function compareRows(diff: BundleDiffData | null): CompareRow[] {
  return (diff?.deltas ?? []).map((delta) => ({
    key: delta.key,
    kind: delta.kind,
    tone: deltaTone(delta.kind),
    leftHash: delta.left ? maskHash(delta.left.sha256, 6) : "-",
    rightHash: delta.right ? maskHash(delta.right.sha256, 6) : "-",
    leftSize: delta.left?.size_bytes ?? 0,
    rightSize: delta.right?.size_bytes ?? 0,
    sizeDelta: delta.size_delta,
    sizeLabel: formatSignedBytes(delta.size_delta),
  }));
}

export function sizeDeltaTotal(diff: BundleDiffData | null): number {
  return (diff?.deltas ?? []).reduce(
    (total, delta) => total + delta.size_delta,
    0,
  );
}

export function compareHeadline(diff: BundleDiffData | null): string {
  if (!diff) return "No comparison loaded";
  if (diff.identical) return "Bundles are identical";
  const counts = diff.counts;
  return `${counts.added ?? 0} added / ${counts.removed ?? 0} removed / ${counts.modified ?? 0} modified`;
}

export function fingerprintPair(diff: BundleDiffData | null): [string, string] {
  if (!diff) return ["-", "-"];
  return [
    maskHash(diff.fingerprint_left, 8),
    maskHash(diff.fingerprint_right, 8),
  ];
}

export function deltaForBundle(
  diff: BundleDiffData | null,
  key: string,
): BundleDeltaData | null {
  return diff?.deltas.find((delta) => delta.key === key) ?? null;
}

export function changedKeys(diff: BundleDiffData | null): string[] {
  return changedDeltas(diff).map((delta) => delta.key);
}
