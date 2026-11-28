/** Unified accessibility refinement dashboard panel. */

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { contrastTone, formatRatio } from "./contrast";
import { announcementFor, liveRegionProps } from "./ScreenReaderLabel";
import { findingTone } from "./wcag";
import type {
  A11yDashboardView,
  AuditRunView,
  ContrastReportView,
} from "./types";

export interface A11yRefinementPanelProps {
  dashboard: A11yDashboardView;
  runs?: AuditRunView[];
  contrast?: ContrastReportView;
  loading?: boolean;
}

export function A11yRefinementPanel({
  dashboard,
  runs = [],
  contrast,
  loading = false,
}: A11yRefinementPanelProps) {
  if (loading) {
    return (
      <V3Panel
        title="Accessibility refinement"
        subtitle="loading audit…"
        density="compact"
      >
        <div className="a11y-refine__skeleton" aria-hidden="true" />
        <span className="a11y-refine__sr-only">
          Loading accessibility audit
        </span>
      </V3Panel>
    );
  }

  const audit = dashboard.audit;
  const issues = runs.flatMap((run) => run.findings);
  const critical = issues.filter((item) => item.severity === "critical").length;
  const tone = contrast ? contrastTone(contrast.score) : "good";

  return (
    <V3Panel
      title="Accessibility refinement"
      subtitle={`${audit.surfaces} surfaces · ${audit.checked_rules} WCAG 2.2 checks`}
      actions={
        <span className="a11y-refine__badge" data-tone={tone}>
          {audit.failed === 0 ? "all passing" : `${audit.failed} need work`}
        </span>
      }
    >
      <p className="a11y-refine__sr-only" {...liveRegionProps()}>
        {announcementFor(audit.score, audit.findings, dashboard.locale)}
      </p>
      <div className="a11y-refine__stats">
        <V3Stat
          label="Audit score"
          value={audit.score.toFixed(1)}
          hint="/ 100"
          tone={audit.failed ? "warn" : "good"}
        />
        <V3Stat
          label="Findings"
          value={audit.findings}
          hint={`${critical} critical`}
          tone={critical ? "bad" : "neutral"}
        />
        <V3Stat
          label="Contrast"
          value={dashboard.contrast.toFixed(1)}
          hint="% pairs passing"
          tone={tone}
        />
        <V3Stat
          label="Keyboard"
          value={dashboard.keyboard.bindings}
          hint={`${dashboard.keyboard.groups.length} groups`}
          tone={dashboard.keyboard.complete ? "good" : "warn"}
        />
      </div>
      <ul className="a11y-refine__surface-grid" data-density="compact">
        {dashboard.surfaces.map((surface) => {
          const run = runs.find((item) => item.surface === surface);
          const worst = run?.findings[0];
          return (
            <li
              key={surface}
              data-surface={surface}
              data-passed={run?.passed ?? true}
            >
              <span className="a11y-refine__surface-name">{surface}</span>
              <span className="a11y-refine__surface-score">
                {run ? run.score.toFixed(0) : "—"}
              </span>
              {worst && (
                <span
                  className="a11y-refine__surface-issue"
                  data-tone={findingTone(worst.severity)}
                >
                  {worst.criterion}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {contrast && (
        <footer className="a11y-refine__contrast" data-passed={contrast.passed}>
          {contrast.failures.length
            ? `${contrast.failures.length} contrast pair(s) below threshold · ${formatRatio(
                contrast.failures[0].required,
              )} required`
            : "All contrast pairs pass"}
        </footer>
      )}
    </V3Panel>
  );
}
