import { conflictTone, resolutionLabel, shortChecksum } from "./format";
import {
  applyBulkResolution,
  applyConflictResolution,
  recommendResolution,
  resolutionMap,
  unresolvedConflicts,
} from "./helpers";
import type { ConflictRecord, ConflictResolution } from "./types";

interface ConflictResolverProps {
  conflicts: ConflictRecord[];
  query?: string;
  onChange: (conflicts: ConflictRecord[]) => void;
  onResolveAll?: (resolution: ConflictResolution) => void;
}

const CHOICES: ConflictResolution[] = [
  "keep_local",
  "keep_remote",
  "merged",
  "skip",
];

export function ConflictResolver(props: ConflictResolverProps) {
  const { conflicts, query = "", onChange, onResolveAll } = props;
  const filtered = conflicts.filter((item) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return `${item.path} ${item.title} ${item.kind}`
      .toLowerCase()
      .includes(needle);
  });
  const unresolved = unresolvedConflicts(conflicts).length;

  function setOne(key: string, resolution: ConflictResolution) {
    onChange(applyConflictResolution(conflicts, key, resolution));
  }

  function setAll(resolution: ConflictResolution) {
    if (onResolveAll) onResolveAll(resolution);
    else onChange(applyBulkResolution(conflicts, resolution));
  }

  return (
    <section className="sync-conflicts">
      <header className="sync-conflicts-header">
        <div>
          <h3>Conflict resolver</h3>
          <p>
            {unresolved} unresolved of {conflicts.length}
          </p>
        </div>
        <div className="sync-conflicts-actions">
          <button type="button" onClick={() => setAll("keep_remote")}>
            Keep remote
          </button>
          <button type="button" onClick={() => setAll("keep_local")}>
            Keep local
          </button>
          <button
            type="button"
            onClick={() =>
              onChange(
                conflicts.map((conflict) => ({
                  ...conflict,
                  resolution: recommendResolution(conflict),
                })),
              )
            }
          >
            Apply suggestions
          </button>
        </div>
      </header>
      {filtered.length === 0 ? (
        <p className="sync-empty">No conflicts match the current filter.</p>
      ) : (
        <ul className="sync-conflict-list">
          {filtered.map((conflict) => (
            <li key={conflict.key} className="sync-conflict-item">
              <div className="sync-conflict-meta">
                <span
                  className={`sync-badge tone-${conflictTone(conflict.kind)}`}
                >
                  {conflict.kind.replaceAll("_", " ")}
                </span>
                <strong>
                  {conflict.title || conflict.path || conflict.key}
                </strong>
                <span className="sync-conflict-path">
                  {conflict.path || "—"}
                </span>
              </div>
              <dl className="sync-conflict-details">
                <div>
                  <dt>Local</dt>
                  <dd>
                    {shortChecksum(conflict.local_checksum)} ·{" "}
                    {conflict.local_updated_at || "—"}
                  </dd>
                </div>
                <div>
                  <dt>Remote</dt>
                  <dd>
                    {shortChecksum(conflict.remote_checksum)} ·{" "}
                    {conflict.remote_updated_at || "—"}
                  </dd>
                </div>
                <div>
                  <dt>Suggested</dt>
                  <dd>
                    {resolutionLabel(
                      conflict.suggested || recommendResolution(conflict),
                    )}
                  </dd>
                </div>
              </dl>
              <label className="sync-conflict-choice">
                <span>Resolution</span>
                <select
                  value={
                    conflict.resolution === "unresolved"
                      ? ""
                      : conflict.resolution
                  }
                  onChange={(event) =>
                    setOne(
                      conflict.key,
                      (event.target.value ||
                        "unresolved") as ConflictResolution,
                    )
                  }
                >
                  <option value="">Unresolved</option>
                  {CHOICES.map((choice) => (
                    <option key={choice} value={choice}>
                      {resolutionLabel(choice)}
                    </option>
                  ))}
                </select>
              </label>
            </li>
          ))}
        </ul>
      )}
      <footer className="sync-conflicts-footer">
        <code>{JSON.stringify(resolutionMap(conflicts))}</code>
      </footer>
    </section>
  );
}

export function ConflictSummary(props: { conflicts: ConflictRecord[] }) {
  const { conflicts } = props;
  const unresolved = unresolvedConflicts(conflicts).length;
  return (
    <div className="sync-conflict-summary">
      <strong>{conflicts.length}</strong> conflicts ·{" "}
      <strong>{unresolved}</strong> unresolved
    </div>
  );
}
