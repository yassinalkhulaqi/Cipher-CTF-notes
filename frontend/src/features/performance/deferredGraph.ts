/** Deferred graph rendering primitives: chunk tasks and yield between frames. */

import type { DeferredChunk, DeferredTask } from "./types";

export function planChunks<T>(
  tasks: readonly DeferredTask<T>[],
  maxCost = 12,
): DeferredChunk<T>[] {
  const chunks: DeferredChunk<T>[] = [];
  let bucket: DeferredTask<T>[] = [];
  let cost = 0;
  let index = 0;
  const flush = () => {
    if (!bucket.length) return;
    chunks.push({ index, tasks: bucket, cost: round(cost) });
    index += 1;
    bucket = [];
    cost = 0;
  };
  for (const task of tasks) {
    if (bucket.length && cost + task.cost > maxCost) flush();
    bucket.push(task);
    cost += Math.max(0, task.cost);
  }
  flush();
  return chunks;
}

function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export function shouldDefer(taskCount: number, threshold = 120): boolean {
  return Math.max(0, taskCount) > Math.max(1, threshold);
}

export function projectTask<T>(task: DeferredTask<T>): string {
  return `${task.id}:${task.label}:${round(task.cost)}`;
}

export class DeferredQueue<T> {
  private readonly tasks: DeferredTask<T>[] = [];
  private cursor = 0;

  constructor(private readonly chunkCost = 12) {}

  enqueue(task: DeferredTask<T>): void {
    this.tasks.push(task);
  }

  enqueueAll(tasks: readonly DeferredTask<T>[]): void {
    this.tasks.push(...tasks);
  }

  get remaining(): number {
    return Math.max(0, this.tasks.length - this.cursor);
  }

  get done(): boolean {
    return this.remaining === 0;
  }

  take(): DeferredChunk<T> | null {
    if (this.done) return null;
    const remaining = this.tasks.slice(this.cursor);
    const chunks = planChunks(remaining, this.chunkCost);
    const first = chunks[0];
    this.cursor += first.tasks.length;
    return first;
  }

  drain(): DeferredChunk<T>[] {
    const chunks: DeferredChunk<T>[] = [];
    while (!this.done) {
      const chunk = this.take();
      if (chunk) chunks.push(chunk);
    }
    return chunks;
  }

  reset(): void {
    this.tasks.length = 0;
    this.cursor = 0;
  }
}

export function scheduleDeferred(callback: () => void, delay = 0): () => void {
  const handle = setTimeout(callback, Math.max(0, delay));
  return () => clearTimeout(handle);
}

export function graphNodeTask(
  id: string,
  cost = 1.1,
): DeferredTask<{ id: string }> {
  return { id, label: id, cost, payload: { id } };
}
