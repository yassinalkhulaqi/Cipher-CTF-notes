/** Index-freshness helpers for the HUD and deferred reconciliation. */

import type { IndexFreshness, PerfTone } from "./types";

export function buildFreshness(
  generation: number,
  indexedGeneration: number,
  lastIndexedAt: number,
  observedAt: number,
): IndexFreshness {
  const lag = Math.max(0, observedAt - lastIndexedAt);
  const stale = indexedGeneration < generation || lag > 30;
  return {
    generation,
    indexedGeneration,
    lastIndexedAt,
    observedAt,
    lagSeconds: round(lag),
    stale,
  };
}

export function freshnessTone(freshness: IndexFreshness): PerfTone {
  if (freshness.stale) return "bad";
  if (freshness.lagSeconds > 5) return "warn";
  return "good";
}

export function freshnessLabel(freshness: IndexFreshness): string {
  if (freshness.indexedGeneration < freshness.generation) {
    return `${freshness.generation - freshness.indexedGeneration} generations behind`;
  }
  return `fresh · ${freshness.lagSeconds.toFixed(1)}s`;
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

export function shouldRefresh(freshness: IndexFreshness, maxLag = 10): boolean {
  return (
    freshness.indexedGeneration < freshness.generation ||
    freshness.lagSeconds > maxLag
  );
}
