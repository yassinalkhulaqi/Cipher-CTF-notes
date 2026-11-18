import { useA11yAnnouncer } from "../hooks/useA11yAnnouncer";
import { severityLabel } from "../pure";
import type { AuditReportPayload, ContrastReportPayload } from "../types";

export interface ScreenReaderHelperProps {
  audit: AuditReportPayload | null;
  contrast: ContrastReportPayload | null;
}

export function ScreenReaderHelper({
  audit,
  contrast,
}: ScreenReaderHelperProps) {
  const { announcements, announce, dismiss, clear } = useA11yAnnouncer();
  const summaryParts: string[] = [];
  if (audit) {
    summaryParts.push(
      `Audit score ${audit.score.toFixed(0)} with ${audit.issues.length} issues`,
    );
  }
  if (contrast) {
    summaryParts.push(`Contrast score ${contrast.score.toFixed(0)}`);
  }

  return (
    <section className="a11y-section" aria-labelledby="a11y-announcer-title">
      <h3 id="a11y-announcer-title">Screen reader helper</h3>
      <p className="a11y-muted">
        {summaryParts.length > 0
          ? summaryParts.join(". ")
          : "Run an audit to produce announcements."}
      </p>
      <div className="a11y-inline-controls">
        <button
          type="button"
          className="a11y-button"
          onClick={() =>
            announce(summaryParts.join(". ") || "No report available")
          }
        >
          Announce summary
        </button>
        <button type="button" className="a11y-button" onClick={clear}>
          Clear messages
        </button>
      </div>
      <div
        className="a11y-live-region"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {announcements.map((item) => (
          <div
            key={item.id}
            className="a11y-announcement"
            data-politeness={item.politeness}
          >
            <span>{severityLabel(item.politeness)}</span> {item.message}
            <button
              type="button"
              className="a11y-icon-button"
              aria-label="Dismiss announcement"
              onClick={() => dismiss(item.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
