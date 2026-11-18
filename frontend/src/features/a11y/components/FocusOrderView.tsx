import { focusStepLabel, sortFocusSteps } from "../pure";
import type { FocusStep } from "../types";

export interface FocusOrderViewProps {
  steps: readonly FocusStep[];
}

export function FocusOrderView({ steps }: FocusOrderViewProps) {
  const ordered = sortFocusSteps(steps);
  const positive = ordered.filter((step) => step.tab_index > 0);
  return (
    <section className="a11y-section" aria-labelledby="a11y-focus-title">
      <h3 id="a11y-focus-title">Focus order</h3>
      <p>
        {ordered.length} focusable element{ordered.length === 1 ? "" : "s"} ·{" "}
        {positive.length} positive tabindex
      </p>
      {ordered.length === 0 ? (
        <p className="a11y-empty">
          No focusable elements were found in the panel.
        </p>
      ) : (
        <ol className="a11y-focus-list">
          {ordered.map((step) => (
            <li key={`${step.order}-${step.target}`} data-hidden={step.hidden}>
              {focusStepLabel(step)}
              <span className="a11y-muted">
                {" "}
                ({step.tag}, tabindex {step.tab_index})
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
