import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { V2Client, requestId } from "../../lib/apiClient";
import { AutosaveCoalescer, batchToPatch, nextTimerDelay } from "./autosave";
import { copyDocument } from "./blocks";
import { patchFromDiff } from "./diff";
import { patchToApi, documentFromApi } from "./api";
import {
  BLOCK_LIMITS,
  type AutosaveStatus,
  type BlockDocument,
  type BlockPatch,
} from "./types";

export interface BlockAutosaveOptions {
  client: V2Client;
  document: BlockDocument;
  enabled?: boolean;
  intervalMs?: number;
  onSaved?: (document: BlockDocument) => void;
  onError?: (error: unknown) => void;
}

export interface AutosaveController {
  status: AutosaveStatus;
  flush: () => Promise<number>;
  cancel: () => void;
}

export function useBlockAutosave(
  options: BlockAutosaveOptions,
): AutosaveController {
  const {
    client,
    document,
    enabled = true,
    intervalMs,
    onSaved,
    onError,
  } = options;
  const coalescer = useMemo(
    () =>
      new AutosaveCoalescer(
        intervalMs ?? BLOCK_LIMITS.autosaveIntervalMs,
        Math.max(
          intervalMs ?? BLOCK_LIMITS.autosaveIntervalMs,
          BLOCK_LIMITS.autosaveMaxWaitMs,
        ),
      ),
    [intervalMs],
  );
  const lastDocument = useRef<BlockDocument>(copyDocument(document));
  const [status, setStatus] = useState<AutosaveStatus>(() =>
    coalescer.status(),
  );
  const callbacks = useRef({ onSaved, onError });
  callbacks.current = { onSaved, onError };

  useEffect(() => {
    if (!enabled) return;
    const previous = lastDocument.current;
    if (previous.id !== document.id) {
      lastDocument.current = copyDocument(document);
      return;
    }
    const patch = patchFromDiff(previous, document);
    if (patch.entries.length === 0) return;
    coalescer.record(document, patch.entries, { label: "editor" });
    lastDocument.current = copyDocument(document);
    setStatus(coalescer.status());
  }, [coalescer, document, enabled]);

  const persist = useCallback(
    async (documentId: string): Promise<number> => {
      const saved = await client.call<unknown>(
        "blocks.flush",
        { id: documentId },
        {
          idempotencyKey: requestId("autosave"),
        },
      );
      const payload = saved as { saved?: unknown[] };
      const items = payload.saved ?? [];
      const latest = items.at(-1);
      if (latest) {
        const parsed = documentFromApi(latest);
        lastDocument.current = copyDocument(parsed);
        callbacks.current.onSaved?.(parsed);
      }
      setStatus(coalescer.status());
      return items.length;
    },
    [client, coalescer],
  );

  useEffect(() => {
    if (!enabled) return;
    const timer = window.setInterval(
      () => {
        const due = coalescer.flush();
        if (due.length === 0) {
          setStatus(coalescer.status());
          return;
        }
        void (async () => {
          try {
            for (const batch of due) {
              const patch: BlockPatch = batchToPatch(batch);
              await client.call(
                "blocks.autosave",
                { id: batch.documentId, patch: patchToApi(patch) },
                {
                  idempotencyKey: requestId("queue"),
                },
              );
              await persist(batch.documentId);
            }
          } catch (error) {
            callbacks.current.onError?.(error);
          }
        })();
      },
      Math.max(50, intervalMs ?? 800),
    );
    return () => window.clearInterval(timer);
  }, [client, coalescer, enabled, intervalMs, persist]);

  const flush = useCallback(async (): Promise<number> => {
    const batches = coalescer.flushAll();
    let count = 0;
    for (const batch of batches) {
      const patch: BlockPatch = batchToPatch(batch);
      await client.call(
        "blocks.autosave",
        { id: batch.documentId, patch: patchToApi(patch) },
        {
          idempotencyKey: requestId("queue"),
        },
      );
      count += await persist(batch.documentId);
    }
    setStatus(coalescer.status());
    return count;
  }, [client, coalescer, persist]);

  const cancel = useCallback(() => {
    coalescer.clear();
    lastDocument.current = copyDocument(document);
    setStatus(coalescer.status());
  }, [coalescer, document]);

  return { status, flush, cancel };
}

export function autosaveDelay(status: AutosaveStatus): number {
  return nextTimerDelay(status);
}
