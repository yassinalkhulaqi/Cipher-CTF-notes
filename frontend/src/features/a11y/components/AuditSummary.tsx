import { severityLabel } from "../pure";
import { sortIssues } from "../pure";
import { useA11yAnnouncer } from "../hooks/useA11yAnnouncer";
import type { AuditReportPayload } from "../types";

export interface AuditSummaryProps {
  report: AuditReportPayload | null;
}

export function AuditSummary({ report }: AuditSummaryProps) {
  const { announce } = useA11yAnnouncer();
  if (!report) {
    return <p className="a11y-empty">No audit has been run yet.</p>;
  }
  const issues = sortIssues(report.issues);
  return (
    <section className="a11y-audit" aria-labelledby="a11y-audit-title">
      <h3 id="a11y-audit-title">Audit summary</h3>
      <p>
        Score {report.score.toFixed(0)} · {issues.length} issue
        {issues.length === 1 ? "" : "s"} ·{" "}
        {report.passed ? "Passed" : "Needs attention"}
      </p>
      {issues.length === 0 ? (
        <p className="a11y-empty">No accessibility issues were detected.</p>
      ) : (
        <ul className="a11y-issue-list">
          {issues.map((issue, index) => (
            <li key={`${issue.rule}-${issue.target}-${index}`}>
              <strong>{severityLabel(issue.severity)}</strong> · {issue.message}
              <span className="a11y-muted"> ({issue.wcag || "—"})</span>
              <p className="a11y-muted">{issue.remediation}</p>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        className="a11y-button"
        onClick={() =>
          announce(`Audit score ${report.score.toFixed(0)}`, "polite")
        }
      >
        Announce score
      </button>
    </section>
  );
}
