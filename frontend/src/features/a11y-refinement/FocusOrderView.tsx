/** Focus-order view with explicit tab sequence and skip-link hint. */

import type { AuditRunView } from "./types";
import { findingTone } from "./wcag";
import { V3Panel } from "../../v3/components/V3Panel";

export interface FocusOrderViewProps {
  runs: AuditRunView[];
  focusOrder: string[];
  onStep?: (action: string) => void;
}

export function FocusOrderView({
  runs,
  focusOrder,
  onStep,
}: FocusOrderViewProps) {
  const blocked = runs.filter((run) => !run.passed);
  const focusIssues = runs.flatMap((run) =>
    run.findings.filter((item) => item.rule.startsWith("focus.")),
  );

  return (
    <V3Panel
      title="Focus order"
      subtitle={`${focusOrder.length} keyboard steps · ${focusIssues.length} focus findings`}
      density="compact"
    >
      <p className="a11y-refine__hint" id="a11y-refine-focus-hint">
        Start at the skip link, then follow the ordered panes. Every step is
        reachable with Tab.
      </p>
      <ol
        className="a11y-refine__focus-list"
        aria-describedby="a11y-refine-focus-hint"
        data-count={focusOrder.length}
      >
        {focusOrder.map((action, index) => (
          <li key={`${action}-${index}`} data-step={index + 1}>
            <button type="button" onClick={() => onStep?.(action)}>
              <span className="a11y-refine__step-index" aria-hidden="true">
                {index + 1}
              </span>
              <span>{action.replaceAll("_", " ")}</span>
            </button>
          </li>
        ))}
      </ol>
      {focusIssues.length > 0 && (
        <ul className="a11y-refine__issues" aria-label="Focus findings">
          {focusIssues.map((issue, index) => (
            <li
              key={`${issue.rule}-${index}`}
              data-tone={findingTone(issue.severity)}
            >
              <strong>{issue.criterion}</strong> {issue.message}
            </li>
          ))}
        </ul>
      )}
      {blocked.length > 0 && (
        <p className="a11y-refine__warning" role="status">
          {blocked.length} surface(s) still need keyboard remediation.
        </p>
      )}
    </V3Panel>
  );
}
