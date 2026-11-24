/** Run history with selection, replay verdict and field-level diff. */

import type { DiffEntry, RunRecord } from "./types";

export interface RunHistoryProps {
  runs: RunRecord[];
  selectedId: string;
  replayOk: boolean | null;
  rollbackOk: boolean | null;
  differences: DiffEntry[];
  onSelect: (id: string) => void;
  onReplay: () => void;
  onRollback: () => void;
}

export function RunHistory({
  runs,
  selectedId,
  replayOk,
  rollbackOk,
  differences,
  onSelect,
  onReplay,
  onRollback,
}: RunHistoryProps) {
  return (
    <div className="automation-history" data-automation="run-history" data-density="compact">
      <ul className="automation-history__list">
        {runs.map((run) => (
          <li key={run.id} data-automation="run-row" data-selected={run.id === selectedId ? "true" : "false"}>
            <button type="button" onClick={() => onSelect(run.id)} aria-pressed={run.id === selectedId}>
              <code>{run.id.slice(0, 14)}</code>
              <span data-status={run.status}>{run.status}</span>
              <span>{new Date(run.started_at * 1000).toISOString().slice(0, 16)}</span>
            </button>
          </li>
        ))}
        {!runs.length && <li className="automation-history__empty">No runs recorded yet.</li>}
      </ul>
      <div className="automation-history__actions">
        <button type="button" data-automation="replay-run" onClick={onReplay} disabled={!selectedId}>
          Replay selected
        </button>
        <button type="button" data-automation="rollback-run" onClick={onRollback} disabled={!selectedId}>
          Roll back selected
        </button>
        {replayOk !== null && (
          <span data-automation="replay-verdict" data-ok={replayOk}>
            {replayOk ? "Replay deterministic" : "Replay differed"}
          </span>
        )}
        {rollbackOk !== null && (
          <span data-automation="rollback-verdict" data-ok={rollbackOk}>
            {rollbackOk ? "Rollback equivalent" : "Rollback mismatch"}
          </span>
        )}
      </div>
      <div className="automation-history__diff" data-automation="run-diff">
        <h4>Diff vs previous run</h4>
        {!differences.length && <p>No differences.</p>}
        {differences.length > 0 && (
          <dl>
            {differences.slice(0, 20).map((item, index) => (
              <div key={`${item.path}-${index}`} data-automation="diff-row">
                <dt>{item.path}</dt>
                <dd>
                  <del>{JSON.stringify(item.before)}</del> → <ins>{JSON.stringify(item.after)}</ins>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}
