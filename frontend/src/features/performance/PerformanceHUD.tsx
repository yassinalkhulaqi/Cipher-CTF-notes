/** Performance HUD: frame time, index freshness, and budget status. */

import { useState } from "react";

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { SkeletonList } from "./Skeletons";
import { formatFrameStats } from "./frameMonitor";
import { freshnessLabel, freshnessTone, shouldRefresh } from "./freshness";
import type {
  BudgetView,
  FixtureSummary,
  FrameStats,
  IndexFreshness,
} from "./types";

export interface PerformanceHUDProps {
  frames: FrameStats;
  freshness: IndexFreshness;
  budgets: readonly BudgetView[];
  fixture: FixtureSummary;
  digest: string;
  wallMs: number;
  loading?: boolean;
  onDeferredRender?: () => void;
}

function toneForBudget(budget: BudgetView): "good" | "bad" {
  return budget.passed ? "good" : "bad";
}

export function PerformanceHUD({
  frames,
  freshness,
  budgets,
  fixture,
  digest,
  wallMs,
  loading = false,
  onDeferredRender,
}: PerformanceHUDProps) {
  const [deferred, setDeferred] = useState(false);
  if (loading) return <SkeletonList rows={6} label="Loading performance HUD" />;
  const failed = budgets.filter((budget) => !budget.passed).length;
  const stale = shouldRefresh(freshness);

  return (
    <V3Panel
      title="Performance HUD"
      subtitle={`fixture ${fixture.notes.toLocaleString()} notes · digest ${digest.slice(0, 10)}`}
      actions={
        <button
          type="button"
          className="perf-hud__defer"
          onClick={() => {
            setDeferred(true);
            onDeferredRender?.();
          }}
        >
          {deferred ? "Graph deferred" : "Render graph"}
        </button>
      }
    >
      <div className="perf-hud__stats">
        <V3Stat
          label="Frame avg"
          value={frames.average.toFixed(2)}
          hint="ms"
          tone={frames.tone}
        />
        <V3Stat
          label="Frame p95"
          value={frames.p95.toFixed(2)}
          hint="ms"
          tone={frames.tone}
        />
        <V3Stat
          label="Index age"
          value={freshness.lagSeconds.toFixed(1)}
          hint="seconds"
          tone={freshnessTone(freshness)}
        />
        <V3Stat
          label="Index gen"
          value={freshness.indexedGeneration}
          hint={`of ${freshness.generation}`}
          tone={stale ? "warn" : "good"}
        />
      </div>
      <p className="perf-hud__frames" title={formatFrameStats(frames)}>
        {formatFrameStats(frames)}
      </p>
      <div
        className="perf-hud__freshness"
        data-tone={freshnessTone(freshness)}
        data-stale={stale}
      >
        {freshnessLabel(freshness)}
      </div>
      <ul className="perf-hud__budgets">
        {budgets.map((budget) => (
          <li key={budget.name} data-tone={toneForBudget(budget)}>
            <span className="perf-hud__budget-name">{budget.name}</span>
            <span className="perf-hud__budget-value">
              {budget.measured.toFixed(2)} ms
            </span>
            <span className="perf-hud__budget-limit">
              / {budget.limit.toFixed(0)} ms
            </span>
            <span className="perf-hud__budget-bar" aria-hidden="true">
              <span
                style={{
                  width: `${Math.min(100, (budget.measured / budget.limit) * 100)}%`,
                }}
              />
            </span>
          </li>
        ))}
      </ul>
      <footer className="perf-hud__footer">
        {failed === 0 ? "All budgets passing" : `${failed} budget(s) failing`} ·
        harness {wallMs.toFixed(1)} ms
      </footer>
    </V3Panel>
  );
}
