import { useState, type FormEvent } from "react";

import { RETEST_VERDICTS, proofIssueCount } from "./logic";
import type { FindingDetail, RetestVerdictValue } from "./types";

export interface RetestPanelProps {
  detail: FindingDetail;
  onRetest: (verdict: RetestVerdictValue, notes: string, proofRefs: string[]) => Promise<void>;
  onAddProof: (blockId: string, target: string, excerpt: string) => Promise<void>;
  busy?: boolean;
}

export function RetestPanel({ detail, onRetest, onAddProof, busy = false }: RetestPanelProps) {
  const [verdict, setVerdict] = useState<RetestVerdictValue>("pass");
  const [notes, setNotes] = useState("");
  const [proofTarget, setProofTarget] = useState("");
  const [proofExcerpt, setProofExcerpt] = useState("");
  const [error, setError] = useState("");
  const last = detail.finding.retests[detail.finding.retests.length - 1];
  const issues = proofIssueCount(detail.finding.proof_blocks);

  const submitRetest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const refs = detail.finding.proof_blocks.map((block) => `${block.ref.ref}:${block.block_id}`);
    try {
      await onRetest(verdict, notes, refs);
      setNotes("");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not record retest");
    }
  };

  const submitProof = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!proofTarget.trim()) return;
    try {
      await onAddProof(
        `proof-${detail.finding.proof_blocks.length + 1}`,
        proofTarget.trim(),
        proofExcerpt,
      );
      setProofTarget("");
      setProofExcerpt("");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not attach proof");
    }
  };

  return (
    <section className="retest" data-testid="retest-panel" data-verdict={last?.verdict ?? "none"}>
      <header className="retest__header">
        <h3>Retest panel</h3>
        <span className="retest__proof-count" data-tone={issues > 0 ? "bad" : "good"}>
          {detail.proof.verified}/{detail.proof.total} proof verified
        </span>
      </header>

      {last ? (
        <div className="retest__last" data-verdict={last.verdict}>
          <strong>{last.verdict}</strong>
          <span>by {last.tested_by}</span>
          {last.notes && <p>{last.notes}</p>}
        </div>
      ) : (
        <p className="retest__empty">No retest recorded yet.</p>
      )}

      <form className="retest__form" onSubmit={(event) => void submitRetest(event)}>
        <fieldset className="retest__verdicts">
          <legend>Verdict</legend>
          {RETEST_VERDICTS.map((option) => (
            <label key={option} data-selected={verdict === option}>
              <input
                type="radio"
                name="retest-verdict"
                value={option}
                checked={verdict === option}
                onChange={() => setVerdict(option)}
              />
              {option}
            </label>
          ))}
        </fieldset>
        <label htmlFor="retest-notes">Observations</label>
        <textarea
          id="retest-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={3}
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          Record retest
        </button>
      </form>

      <form className="retest__proof-form" onSubmit={(event) => void submitProof(event)}>
        <label htmlFor="proof-target">Link evidence, note, or section</label>
        <input
          id="proof-target"
          value={proofTarget}
          onChange={(event) => setProofTarget(event.target.value)}
          placeholder="evidence:capture-01"
          disabled={busy}
        />
        <label htmlFor="proof-excerpt">Excerpt</label>
        <textarea
          id="proof-excerpt"
          value={proofExcerpt}
          onChange={(event) => setProofExcerpt(event.target.value)}
          rows={2}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !proofTarget.trim()}>
          Attach proof block
        </button>
      </form>
      {error && <p className="retest__error" role="alert">{error}</p>}
    </section>
  );
}
