import { mergeEntries } from "./diff";
import {
  BLOCK_LIMITS,
  type AutosaveBatch,
  type AutosaveStatus,
  type BlockDocument,
  type BlockPatch,
  type PatchEntry,
} from "./types";

interface Bucket {
  documentId: string;
  baseRevision: number;
  entries: PatchEntry[];
  firstAtMs: number;
  lastAtMs: number;
  mergedFrom: number;
  token: string;
  label: string;
}

function toBatch(bucket: Bucket): AutosaveBatch {
  return {
    documentId: bucket.documentId,
    baseRevision: bucket.baseRevision,
    entries: mergeEntries(bucket.entries),
    mergedFrom: bucket.mergedFrom,
    firstAtMs: bucket.firstAtMs,
    lastAtMs: bucket.lastAtMs,
    token: bucket.token,
    label: bucket.label,
  };
}

export class AutosaveCoalescer {
  private readonly buckets = new Map<string, Bucket>();
  readonly intervalMs: number;
  readonly maxWaitMs: number;
  private readonly clock: () => number;

  constructor(
    intervalMs: number = BLOCK_LIMITS.autosaveIntervalMs,
    maxWaitMs: number = BLOCK_LIMITS.autosaveMaxWaitMs,
    clock: () => number = () => Date.now(),
  ) {
    this.intervalMs = Math.max(0, Math.floor(intervalMs));
    this.maxWaitMs = Math.max(this.intervalMs, Math.floor(maxWaitMs));
    this.clock = clock;
  }

  record(
    document: BlockDocument,
    entries: PatchEntry[],
    options: { token?: string; label?: string } = {},
  ): AutosaveBatch | null {
    if (entries.length === 0) return null;
    const current = this.clock();
    let bucket = this.buckets.get(document.id);
    if (!bucket) {
      bucket = {
        documentId: document.id,
        baseRevision: document.revision,
        entries: [],
        firstAtMs: current,
        lastAtMs: current,
        mergedFrom: 1,
        token: options.token ?? "",
        label: options.label ?? "",
      };
      this.buckets.set(document.id, bucket);
    } else if (bucket.baseRevision !== document.revision) {
      bucket.baseRevision = document.revision;
      bucket.entries = [];
      bucket.firstAtMs = current;
      bucket.mergedFrom = 1;
    }
    bucket.entries.push(...entries);
    bucket.lastAtMs = current;
    bucket.token = options.token || bucket.token;
    bucket.label = options.label || bucket.label;
    if (current - bucket.firstAtMs >= this.maxWaitMs)
      return this.flushDocument(document.id);
    return null;
  }

  recordPatch(
    document: BlockDocument,
    patch: BlockPatch,
  ): AutosaveBatch | null {
    return this.record(document, patch.entries, {
      token: "",
      label: patch.label,
    });
  }

  get pending(): AutosaveBatch[] {
    return Array.from(this.buckets.values())
      .sort((a, b) => a.firstAtMs - b.firstAtMs)
      .map(toBatch);
  }

  hasPending(documentId?: string): boolean {
    return documentId ? this.buckets.has(documentId) : this.buckets.size > 0;
  }

  due(atMs = this.clock()): AutosaveBatch[] {
    return this.pending.filter(
      (batch) =>
        atMs - batch.lastAtMs >= this.intervalMs ||
        atMs - batch.firstAtMs >= this.maxWaitMs,
    );
  }

  flush(atMs = this.clock()): AutosaveBatch[] {
    const due = this.due(atMs);
    for (const batch of due) this.buckets.delete(batch.documentId);
    return due;
  }

  flushAll(): AutosaveBatch[] {
    const batches = this.pending;
    this.buckets.clear();
    return batches;
  }

  flushDocument(documentId: string): AutosaveBatch | null {
    const bucket = this.buckets.get(documentId);
    if (!bucket) return null;
    this.buckets.delete(documentId);
    return toBatch(bucket);
  }

  acknowledge(documentId: string, revision: number): boolean {
    const bucket = this.buckets.get(documentId);
    if (!bucket || bucket.baseRevision > revision) return false;
    this.buckets.delete(documentId);
    return true;
  }

  cancel(documentId: string): boolean {
    return this.buckets.delete(documentId);
  }

  clear(): void {
    this.buckets.clear();
  }

  status(atMs = this.clock()): AutosaveStatus {
    const batches = this.pending;
    let nextFlushMs = 0;
    if (batches.length > 0) {
      const delays = batches
        .map((batch) => this.intervalMs - (atMs - batch.lastAtMs))
        .filter((delay) => delay > 0);
      nextFlushMs = delays.length > 0 ? Math.min(...delays) : 0;
    }
    return {
      pending: batches.length,
      documentIds: batches.map((batch) => batch.documentId),
      operations: batches.reduce((sum, batch) => sum + batch.entries.length, 0),
      mergedEdits: batches.reduce((sum, batch) => sum + batch.mergedFrom, 0),
      nextFlushMs: Math.round(nextFlushMs),
      intervalMs: this.intervalMs,
      maxWaitMs: this.maxWaitMs,
    };
  }
}

export function batchToPatch(batch: AutosaveBatch): BlockPatch {
  return {
    documentId: batch.documentId,
    baseRevision: batch.baseRevision,
    entries: batch.entries,
    label: batch.label,
  };
}

export function nextTimerDelay(status: AutosaveStatus): number {
  return status.pending === 0
    ? 0
    : Math.max(1, Math.min(60000, status.nextFlushMs + 1));
}

export function coalesceBatches(batches: AutosaveBatch[]): AutosaveBatch[] {
  const merged = new Map<string, Bucket>();
  for (const batch of batches) {
    const existing = merged.get(batch.documentId);
    if (!existing) {
      merged.set(batch.documentId, {
        documentId: batch.documentId,
        baseRevision: batch.baseRevision,
        entries: [...batch.entries],
        firstAtMs: batch.firstAtMs,
        lastAtMs: batch.lastAtMs,
        mergedFrom: batch.mergedFrom,
        token: batch.token,
        label: batch.label,
      });
      continue;
    }
    existing.entries.push(...batch.entries);
    existing.firstAtMs = Math.min(existing.firstAtMs, batch.firstAtMs);
    existing.lastAtMs = Math.max(existing.lastAtMs, batch.lastAtMs);
    existing.mergedFrom += batch.mergedFrom;
    existing.token = batch.token || existing.token;
    existing.label = batch.label || existing.label;
  }
  return Array.from(merged.values())
    .sort((a, b) => a.firstAtMs - b.firstAtMs)
    .map(toBatch);
}
