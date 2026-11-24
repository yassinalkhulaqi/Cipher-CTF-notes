/** Iconography and label consistency audit. */

import { V3Panel } from "../../../v3/components/V3Panel";
import { ICON_LABELS, KIND_LABELS } from "../config";
import { kindColorToken, labelConsistencyIssues } from "../pure";

export interface IconographyAuditProps {
  icons?: typeof ICON_LABELS;
}

export function IconographyAudit({ icons = ICON_LABELS }: IconographyAuditProps) {
  const issues = labelConsistencyIssues(icons, KIND_LABELS);
  return (
    <V3Panel
      title="Icons and labels"
      subtitle="One stable label and icon per entity kind"
      kind="extension"
      density="compact"
    >
      <div
        className="release-icons"
        data-surface="iconography-label-audit"
        aria-label="Iconography and label audit"
      >
        <div className="release-icons__header" data-role="icon-audit-header">
          <p data-role="issue-count" data-issues={issues.length}>
            {issues.length === 0 ? "All labels consistent" : `${issues.length} inconsistencies`}
          </p>
          <button
            aria-label="Re-check icon and label consistency"
            className="release-v3-focusable"
            data-action="recheck-icons"
            type="button"
          >
            Re-check
          </button>
        </div>
        <ul className="release-icons__grid" data-role="icon-grid">
          {icons.map((entry) => (
            <li
              className="release-icons__item"
              data-icon={entry.icon}
              data-kind={entry.kind}
              key={entry.kind}
            >
              <span
                aria-hidden="true"
                className="release-icons__glyph"
                style={{ color: kindColorToken(entry.kind) }}
              >
                {entry.icon}
              </span>
              <span aria-label={`${entry.label} entity kind`}>{entry.label}</span>
            </li>
          ))}
        </ul>
        {issues.length > 0 && (
          <ul className="release-icons__issues" data-role="label-issues" aria-live="polite">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
      </div>
    </V3Panel>
  );
}
