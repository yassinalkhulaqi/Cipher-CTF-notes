import { contrastGrade, contrastStatus, formatRatio } from "../pure";
import type { ContrastReportPayload } from "../types";

export interface ContrastReportViewProps {
  report: ContrastReportPayload | null;
}

export function ContrastReportView({ report }: ContrastReportViewProps) {
  if (!report) {
    return <p className="a11y-empty">No contrast report is available.</p>;
  }
  const grade = contrastGrade(report.score);
  return (
    <section className="a11y-contrast" aria-labelledby="a11y-contrast-title">
      <h3 id="a11y-contrast-title">Color contrast</h3>
      <p>
        Score {report.score.toFixed(0)} · Grade {grade} · Target {report.target}
      </p>
      {report.pairs.length === 0 ? (
        <p className="a11y-empty">No color pairs were checked.</p>
      ) : (
        <div className="a11y-table-wrap">
          <table className="a11y-table">
            <thead>
              <tr>
                <th scope="col">Pair</th>
                <th scope="col">Ratio</th>
                <th scope="col">Required</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {report.pairs.map((pair, index) => (
                <tr key={`${pair.name}-${index}`}>
                  <td>
                    {pair.name || `${pair.foreground} on ${pair.background}`}
                  </td>
                  <td>{formatRatio(pair.ratio)}</td>
                  <td>{formatRatio(pair.required)}</td>
                  <td>
                    <span
                      className={`a11y-status a11y-status-${contrastStatus(pair, report.target)}`}
                    >
                      {contrastStatus(pair, report.target)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report.failures.length > 0 && (
        <ul className="a11y-issue-list">
          {report.failures.map((failure, index) => (
            <li key={`${failure}-${index}`}>{failure}</li>
          ))}
        </ul>
      )}
      {report.suggestions.length > 0 && (
        <ul className="a11y-suggestions">
          {report.suggestions.map((suggestion, index) => (
            <li key={`${suggestion}-${index}`}>{suggestion}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
