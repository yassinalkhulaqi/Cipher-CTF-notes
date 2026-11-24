import type { ChangeView, DryRunView, VectorView } from "../types";
import {
  actionTone,
  changesByAction,
  summarizeDryRun,
  vectorRelationLabel,
  vectorSummary,
  vectorTone,
} from "../pure";

interface Props {
  report: DryRunView | null;
  vector: VectorView | null;
  onConfirm: () => void;
  onBack: () => void;
}

function ChangeRow({ change }: { change: ChangeView }) {
  return (
    <tr className="portability-change">
      <td>
        <span
          className="portability-badge"
          data-tone={actionTone(change.action)}
        >
          {change.action}
        </span>
      </td>
      <td className="portability-change__ref">{change.ref}</td>
      <td>{change.title}</td>
      <td>{change.fields.join(", ") || "—"}</td>
    </tr>
  );
}

export function DryRunPreviewPanel({
  report,
  vector,
  onConfirm,
  onBack,
}: Props) {
  const actions = changesByAction(report);
  return (
    <section
      className="portability-card portability-preview"
      aria-label="Dry-run preview"
    >
      <header className="portability-card__header">
        <div>
          <h3>Dry-run preview</h3>
          <p className="portability-card__subtitle">
            {summarizeDryRun(report)}
          </p>
        </div>
        <span
          className="portability-badge"
          data-tone={report?.valid ? "good" : "warn"}
        >
          {report?.valid ? "Safe to apply" : "Needs decisions"}
        </span>
      </header>

      <div className="portability-preview__stats">
        {Object.entries(actions).map(([action, count]) => (
          <div key={action} className="portability-stat">
            <span>{action}</span>
            <strong>{count}</strong>
          </div>
        ))}
        <div className="portability-stat">
          <span>conflicts</span>
          <strong>{report?.conflicts.length ?? 0}</strong>
        </div>
      </div>

      {vector && (
        <div
          className="portability-vector"
          data-tone={vectorTone(vector.relation)}
        >
          <strong>{vectorRelationLabel(vector.relation)}</strong>
          <span>{vectorSummary(vector)}</span>
        </div>
      )}

      {report?.warnings.length ? (
        <ul className="portability-warnings">
          {report.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div className="portability-table-wrap">
        <table className="portability-table">
          <thead>
            <tr>
              <th>Action</th>
              <th>Reference</th>
              <th>Title</th>
              <th>Fields</th>
            </tr>
          </thead>
          <tbody>
            {(report?.changes ?? []).map((change) => (
              <ChangeRow
                key={`${change.action}-${change.ref}`}
                change={change}
              />
            ))}
          </tbody>
        </table>
        {!report?.changes.length && (
          <p className="portability-empty">No preview changes yet.</p>
        )}
      </div>

      <footer className="portability-card__footer">
        <button
          type="button"
          className="portability-button portability-button--ghost"
          onClick={onBack}
        >
          Back
        </button>
        <button
          type="button"
          className="portability-button"
          onClick={onConfirm}
          disabled={!report?.valid}
        >
          Confirm import
        </button>
      </footer>
    </section>
  );
}
