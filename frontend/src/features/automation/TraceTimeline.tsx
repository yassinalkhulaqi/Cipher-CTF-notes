/** Ordered dry-run trace timeline. */

import { timeline, traceSummary, traceVerdict } from "./trace";
import type { DryRunTrace } from "./types";
import { STEP_LABELS } from "./types";

export interface TraceTimelineProps {
  trace: DryRunTrace | null;
  title?: string;
}

export function TraceTimeline({ trace, title = "Dry-run trace" }: TraceTimelineProps) {
  if (!trace) {
    return <p className="automation-trace__empty" data-automation="trace-empty">Run a dry run to inspect every would-be mutation.</p>;
  }
  const items = timeline(trace);
  const summary = traceSummary(trace);
  const verdict = traceVerdict(trace);
  return (
    <div className="automation-trace" data-automation="trace-timeline" data-verdict={verdict}>
      <div className="automation-trace__summary" data-automation="trace-summary">
        <span>{title}</span>
        <span>steps {summary.steps}</span>
        <span>mutations {summary.mutations}</span>
        <span data-automation="trace-writes">writes {summary.writes}</span>
        <code>{trace.digest.slice(0, 12)}</code>
      </div>
      <ol className="automation-trace__list">
        {items.map((item) => (
          <li key={`${item.index}-${item.step_id}`} className="automation-trace__item" data-automation="trace-item" data-tone={item.tone}>
            <span className="automation-trace__index">{String(item.index + 1).padStart(2, "0")}</span>
            <div className="automation-trace__content">
              <strong>{item.title}</strong>
              <span className="automation-trace__kind">{STEP_LABELS[item.kind]}</span>
              <span className="automation-trace__message">{item.message}</span>
              {item.target && <code className="automation-trace__target">{item.target}</code>}
              {item.mutation && (
                <details data-automation="trace-mutation">
                  <summary>Inspect mutation</summary>
                  <pre>{JSON.stringify(item.mutation.payload, null, 2)}</pre>
                </details>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
