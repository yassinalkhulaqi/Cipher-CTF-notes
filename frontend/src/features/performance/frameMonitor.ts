/** Frame-time sampling and pure statistics for the performance HUD. */

import type { FrameStats, PerfTone } from "./types";

export const FRAME_BUDGET_MS = 16.7;

export function percentile(samples: readonly number[], fraction: number): number {
  if (!samples.length) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const position = clampFraction(fraction) * (sorted.length - 1);
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function clampFraction(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function summarizeFrames(samples: readonly number[], budget = FRAME_BUDGET_MS): FrameStats {
  if (!samples.length) {
    return { samples: 0, average: 0, p95: 0, worst: 0, tone: "neutral" };
  }
  const average = samples.reduce((total, value) => total + value, 0) / samples.length;
  const p95 = percentile(samples, 0.95);
  const worst = Math.max(...samples);
  return {
    samples: samples.length,
    average: round(average),
    p95: round(p95),
    worst: round(worst),
    tone: frameTone(p95, budget),
  };
}

export function frameTone(value: number, budget = FRAME_BUDGET_MS): PerfTone {
  if (value <= budget) return "good";
  if (value <= budget * 1.5) return "warn";
  return "bad";
}

export function round(value: number, places = 2): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

export class FrameMonitor {
  private readonly samples: number[] = [];
  private last: number | null = null;
  private readonly capacity: number;

  constructor(capacity = 120) {
    this.capacity = Math.max(2, Math.trunc(capacity));
  }

  record(timestamp: number): number | null {
    if (this.last === null) {
      this.last = timestamp;
      return null;
    }
    const delta = Math.max(0, timestamp - this.last);
    this.last = timestamp;
    this.samples.push(delta);
    if (this.samples.length > this.capacity) this.samples.shift();
    return delta;
  }

  sample(index: number): number | undefined {
    return this.samples[index];
  }

  values(): number[] {
    return [...this.samples];
  }

  stats(budget = FRAME_BUDGET_MS): FrameStats {
    return summarizeFrames(this.samples, budget);
  }

  reset(): void {
    this.samples.length = 0;
    this.last = null;
  }

  get size(): number {
    return this.samples.length;
  }
}

export function formatFrameStats(stats: FrameStats): string {
  return `avg ${stats.average.toFixed(2)}ms · p95 ${stats.p95.toFixed(2)}ms · worst ${stats.worst.toFixed(2)}ms`;
}
