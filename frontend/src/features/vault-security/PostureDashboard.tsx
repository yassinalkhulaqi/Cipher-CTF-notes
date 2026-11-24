/** Security posture dashboard with explicit locked states. */

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import {
  gapSummary,
  posturePercent,
  postureTone,
  severityTone,
  sortedChecks,
} from "./pure";
import type { PostureReport } from "./types";

export interface PostureDashboardProps {
  report: PostureReport;
  onRefresh: () => void;
  busy?: boolean;
}

export function PostureDashboard({
  report,
  onRefresh,
  busy = false,
}: PostureDashboardProps) {
  const tone = postureTone(report.level);
  const checks = sortedChecks(report);
  return (
    <V3Panel
      title="Security posture"
      subtitle={gapSummary(report)}
      kind="evidence"
      actions={
        <button type="button" onClick={onRefresh} disabled={busy}>
          Refresh score
        </button>
      }
    >
      <div className="vs-posture__headline" data-tone={tone}>
        <div
          className="vs-posture__gauge"
          aria-label={`Posture score ${report.score}`}
        >
          <strong>{posturePercent(report.score)}</strong>
          <span>/ 100</span>
        </div>
        <div className="vs-posture__summary">
          <span className="vs-posture__level">{report.level}</span>
          <span className="vs-posture__counts">
            {report.passed} of {report.total} checks pass
          </span>
          {report.warnings.map((warning) => (
            <span className="vs-posture__warning" key={warning}>
              {warning}
            </span>
          ))}
        </div>
      </div>
      <div className="vs-stats">
        <V3Stat label="Score" value={report.score} tone={tone} />
        <V3Stat label="Passed" value={report.passed} tone="good" />
        <V3Stat
          label="Gaps"
          value={report.gap_ids.length}
          tone={report.gap_ids.length ? "bad" : "neutral"}
        />
      </div>
      <ul className="vs-checks">
        {checks.map((check) => (
          <li
            className="vs-check"
            data-passed={check.passed}
            data-tone={severityTone(check.severity)}
            key={check.id}
          >
            <span className="vs-check__mark" aria-hidden="true">
              {check.passed ? "PASS" : "FIX"}
            </span>
            <div className="vs-check__body">
              <strong className="vs-check__label">{check.label}</strong>
              <span className="vs-check__detail">{check.detail}</span>
              {!check.passed && (
                <span className="vs-check__fix">{check.remediation}</span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {report.contains_secrets && (
        <p className="vs-locked">Posture data withheld: secret detected.</p>
      )}
    </V3Panel>
  );
}
