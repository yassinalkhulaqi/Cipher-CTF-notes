import { duplicateConfidence, formatScore, shortRef } from "./logic";
import type { FindingDetail } from "./types";

export interface DuplicateSuggestionsProps {
  detail: FindingDetail;
  onMark: (canonical: string, note: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  busy?: boolean;
}

export function DuplicateSuggestions({
  detail,
  onMark,
  onRefresh,
  busy = false,
}: DuplicateSuggestionsProps) {
  const candidates = detail.duplicates.candidates;
  const fingerprint = detail.duplicates.fingerprint;

  return (
    <section className="duplicates" data-testid="duplicate-suggestions">
      <header className="duplicates__header">
        <h3>Duplicate suggestions</h3>
        <button type="button" className="duplicates__refresh" onClick={() => void onRefresh()} disabled={busy}>
          Refresh
        </button>
      </header>
      <p className="duplicates__fingerprint" title={fingerprint}>
        fingerprint: {fingerprint ? fingerprint.slice(0, 12) : "—"}
      </p>
      {candidates.length === 0 ? (
        <p className="duplicates__empty">No similar findings above the threshold.</p>
      ) : (
        <ul className="duplicates__list">
          {candidates.map((candidate) => {
            const ref = candidate.candidate_ref.ref;
            return (
              <li key={ref} data-tone={duplicateConfidence(candidate.score)} data-testid="duplicate-item">
                <div className="duplicates__item-head">
                  <span className="duplicates__ref">{shortRef(ref)}</span>
                  <strong>{formatScore(candidate.score)}</strong>
                  <span>{candidate.candidate_ref.label}</span>
                </div>
                <ul className="duplicates__reasons">
                  {candidate.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
                <button
                  type="button"
                  className="duplicates__link"
                  disabled={busy || detail.finding.duplicate_of !== ""}
                  aria-label={`Mark ${shortRef(ref)} as canonical duplicate`}
                  onClick={() => void onMark(ref, "Matched by studio duplicate detection")}
                >
                  Mark as duplicate
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
