import type { ProgressView } from "../types";
import { canCancel, canResume, progressLabel, statusTone } from "../pure";

interface Props {
  progress: ProgressView | null;
  onCancel: () => void;
  onResume: () => void;
}

export function TransferProgress({ progress, onCancel, onResume }: Props) {
  const percent = progress?.percent ?? 0;
  return (
    <section className="portability-card portability-progress" aria-label="Transfer progress">
      <header className="portability-card__header">
        <div>
          <h3>Transfer progress</h3>
          <p className="portability-card__subtitle" aria-live="polite">
            {progressLabel(progress)}
          </p>
        </div>
        <span className="portability-badge" data-tone={statusTone(progress?.phase ?? "idle")}>
          {progress?.phase ?? "idle"}
        </span>
      </header>

      <div
        className="portability-progress__track"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="portability-progress__fill" style={{ width: `${percent}%` }} />
      </div>

      {progress && (
        <dl className="portability-progress__stats">
          <div>
            <dt>Bundle</dt>
            <dd>{progress.bundleId}</dd>
          </div>
          <div>
            <dt>Chunks received</dt>
            <dd>
              {progress.receivedChunks} / {progress.totalChunks}
            </dd>
          </div>
          <div>
            <dt>Outstanding</dt>
            <dd>{progress.missingChunks.length}</dd>
          </div>
        </dl>
      )}

      {progress?.missingChunks.length ? (
        <div className="portability-chunks" aria-label="Missing chunks">
          {progress.missingChunks.slice(0, 24).map((index) => (
            <span key={index} className="portability-chunk" data-state="missing">
              {index}
            </span>
          ))}
          {progress.missingChunks.length > 24 && (
            <span className="portability-chunk" data-state="more">
              +{progress.missingChunks.length - 24}
            </span>
          )}
        </div>
      ) : null}

      <footer className="portability-card__footer">
        <button
          type="button"
          className="portability-button portability-button--ghost"
          onClick={onCancel}
          disabled={!canCancel(progress)}
        >
          Cancel transfer
        </button>
        <button
          type="button"
          className="portability-button"
          onClick={onResume}
          disabled={!canResume(progress)}
        >
          Resume transfer
        </button>
      </footer>
    </section>
  );
}
