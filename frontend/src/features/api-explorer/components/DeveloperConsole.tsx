/** Request/response history with filtering and detail inspection. */

import { useMemo, useState } from "react";

import { filterEntries, formatDuration } from "../pure";
import { useApiExplorerStore } from "../store";

export function DeveloperConsole() {
  const history = useApiExplorerStore((state) => state.history);
  const clearHistory = useApiExplorerStore((state) => state.clearHistory);
  const [query, setQuery] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const entries = useMemo(
    () => filterEntries(history, query, errorsOnly),
    [history, query, errorsOnly],
  );
  const detail =
    selected === null ? null : history.find((item) => item.id === selected);

  return (
    <section
      className="api-explorer-panel developer-console"
      aria-label="Developer console"
    >
      <header className="api-explorer-panel__header">
        <div>
          <h2>Developer Console</h2>
          <p>
            {history.length} request(s) recorded · body values are never
            retained
          </p>
        </div>
        <button
          type="button"
          onClick={clearHistory}
          disabled={history.length === 0}
        >
          Clear history
        </button>
      </header>

      <div className="developer-console__filters">
        <label>
          Filter
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="route, code, request id"
            aria-label="Console filter"
          />
        </label>
        <label className="api-explorer__checkbox">
          <input
            type="checkbox"
            checked={errorsOnly}
            onChange={(event) => setErrorsOnly(event.target.checked)}
          />
          Errors only
        </label>
      </div>

      <div className="developer-console__grid">
        <ul className="developer-console__list">
          {entries.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                data-selected={entry.id === selected}
                onClick={() => setSelected(entry.id)}
                className="developer-console__entry"
              >
                <span
                  className="developer-console__status"
                  data-error={Boolean(entry.errorCode)}
                >
                  {entry.status}
                </span>
                <code>{entry.route}</code>
                <small>{formatDuration(entry.durationMs)}</small>
                {entry.cached && <small>cached</small>}
                {entry.errorCode && (
                  <small className="developer-console__code">
                    {entry.errorCode}
                  </small>
                )}
              </button>
            </li>
          ))}
          {entries.length === 0 && (
            <li className="developer-console__empty">No matching requests.</li>
          )}
        </ul>

        <aside className="developer-console__detail">
          {detail ? (
            <>
              <h3>{detail.route}</h3>
              <dl className="api-explorer__meta">
                <div>
                  <dt>sequence</dt>
                  <dd>{detail.sequence}</dd>
                </div>
                <div>
                  <dt>request id</dt>
                  <dd>{detail.requestId || "—"}</dd>
                </div>
                <div>
                  <dt>etag</dt>
                  <dd>{detail.etag || "—"}</dd>
                </div>
                <div>
                  <dt>capability</dt>
                  <dd>{detail.capability || "—"}</dd>
                </div>
                <div>
                  <dt>body keys</dt>
                  <dd>{detail.bodyKeys.join(", ") || "—"}</dd>
                </div>
              </dl>
              <pre className="api-explorer__code">{detail.responsePreview}</pre>
            </>
          ) : (
            <p>Select a request to inspect its response summary.</p>
          )}
        </aside>
      </div>
    </section>
  );
}
