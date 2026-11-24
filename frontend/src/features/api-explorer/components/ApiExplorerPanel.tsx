/** Request builder with explicit, visible write opt-in. */

import { useEffect, useMemo, useState } from "react";

import { createApiExplorerClient, type ApiExplorerClient } from "../client";
import {
  formatDuration,
  isWriteRoute,
  previewResponse,
  requestBody,
  responseTone,
} from "../pure";
import { useApiExplorerStore } from "../store";
import type { ConsoleEntry, RouteInfoLite } from "../types";

interface Props {
  client?: ApiExplorerClient;
}

function splitRoute(
  path: string,
): { namespace: string; action: string } | null {
  const parts = path.replace(/^\/api\/v3\//, "").split("/");
  if (parts.length !== 2) return null;
  return { namespace: parts[0], action: parts[1] };
}

export function ApiExplorerPanel({ client }: Props) {
  const explorer = useMemo(() => client ?? createApiExplorerClient(), [client]);
  const request = useApiExplorerStore((state) => state.request);
  const response = useApiExplorerStore((state) => state.response);
  const history = useApiExplorerStore((state) => state.history);
  const busy = useApiExplorerStore((state) => state.busy);
  const error = useApiExplorerStore((state) => state.error);
  const patchRequest = useApiExplorerStore((state) => state.patchRequest);
  const setResponse = useApiExplorerStore((state) => state.setResponse);
  const appendEntry = useApiExplorerStore((state) => state.appendEntry);
  const setBusy = useApiExplorerStore((state) => state.setBusy);
  const setError = useApiExplorerStore((state) => state.setError);
  const [routes, setRoutes] = useState<RouteInfoLite[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    let active = true;
    explorer
      .routes()
      .then((items) => {
        if (active) setRoutes(items);
      })
      .catch(() => {
        if (active) setRoutes([]);
      });
    return () => {
      active = false;
    };
  }, [explorer]);

  const writeRoute = isWriteRoute(request.namespace, request.action);
  const blockedByAck = writeRoute && request.allowWrite && !acknowledged;

  async function submit() {
    setBusy(true);
    setError(null);
    const started = Date.now();
    const parsedBody = requestBody(request);
    const result = await explorer.call(request);
    const entry: ConsoleEntry = {
      id: `${Date.now()}-${history.length + 1}`,
      sequence: history.length + 1,
      route: `/api/v3/${request.namespace}/${request.action}`,
      status: result.status,
      requestId: result.requestId,
      etag: result.etag,
      errorCode: result.errorCode,
      durationMs: Date.now() - started,
      timestamp: Date.now(),
      cached: result.status === 304,
      capability: request.capability,
      bodyKeys: parsedBody.ok ? Object.keys(parsedBody.value ?? {}) : [],
      responsePreview: previewResponse(result),
    };
    appendEntry(entry);
    setResponse(result);
    if (!result.ok) setError(result.errorMessage || result.errorCode);
    setBusy(false);
  }

  return (
    <section className="api-explorer-panel" aria-label="API request explorer">
      <header className="api-explorer-panel__header">
        <div>
          <h2>API Explorer</h2>
          <p>
            Local-only envelope calls. Reads are always allowed; writes need an
            explicit opt-in.
          </p>
        </div>
        <span className="api-explorer__mode" data-write={writeRoute}>
          {writeRoute ? "write route" : "read-only route"}
        </span>
      </header>

      <div className="api-explorer-panel__grid">
        <form
          className="api-explorer__form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label>
            Namespace
            <input
              value={request.namespace}
              onChange={(event) =>
                patchRequest({ namespace: event.target.value })
              }
              aria-label="Namespace"
            />
          </label>
          <label>
            Action
            <input
              value={request.action}
              onChange={(event) => patchRequest({ action: event.target.value })}
              aria-label="Action"
            />
          </label>
          <label className="api-explorer__wide">
            Request body (JSON)
            <textarea
              value={request.bodyText}
              onChange={(event) =>
                patchRequest({ bodyText: event.target.value })
              }
              rows={6}
              spellCheck={false}
              aria-label="Request body"
            />
          </label>
          <label>
            Capability
            <input
              value={request.capability}
              placeholder="extensions"
              onChange={(event) =>
                patchRequest({ capability: event.target.value })
              }
              aria-label="Capability"
            />
          </label>
          <label>
            If-None-Match
            <input
              value={request.etag}
              onChange={(event) => patchRequest({ etag: event.target.value })}
              aria-label="ETag"
            />
          </label>
          <label>
            Idempotency key
            <input
              value={request.idempotencyKey}
              onChange={(event) =>
                patchRequest({ idempotencyKey: event.target.value })
              }
              aria-label="Idempotency key"
            />
          </label>
          <label className="api-explorer__checkbox">
            <input
              type="checkbox"
              checked={request.allowWrite}
              onChange={(event) =>
                patchRequest({ allowWrite: event.target.checked })
              }
            />
            Allow writes for this request
          </label>
          {writeRoute && request.allowWrite && (
            <label className="api-explorer__checkbox api-explorer__warning">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              I understand this request mutates local state
            </label>
          )}
          <div className="api-explorer__actions">
            <button type="submit" disabled={busy || blockedByAck}>
              {busy ? "Sending…" : "Send request"}
            </button>
            <span className="api-explorer__hint">
              {blockedByAck ? "Confirm the write to continue" : "POST /api/v3"}
            </span>
          </div>
        </form>

        <div className="api-explorer__result">
          <div className="api-explorer__result-head">
            <strong>Response</strong>
            {response && (
              <span
                data-tone={responseTone(response)}
                className="api-explorer__pill"
              >
                {response.status}
              </span>
            )}
          </div>
          {response ? (
            <dl className="api-explorer__meta">
              <div>
                <dt>request id</dt>
                <dd>{response.requestId || "—"}</dd>
              </div>
              <div>
                <dt>etag</dt>
                <dd>{response.etag || "—"}</dd>
              </div>
              <div>
                <dt>duration</dt>
                <dd>{formatDuration(history.at(-1)?.durationMs ?? 0)}</dd>
              </div>
            </dl>
          ) : (
            <p className="api-explorer__empty">No request sent yet.</p>
          )}
          {error && <p className="api-explorer__error">{error}</p>}
          <pre className="api-explorer__code">
            {response ? previewResponse(response) : "{}"}
          </pre>
        </div>
      </div>

      <div className="api-explorer__routes">
        <h3>Available routes</h3>
        <div className="api-explorer__route-list">
          {routes.map((route) => {
            const parsed = splitRoute(route.path);
            return (
              <button
                type="button"
                key={route.path}
                className="api-explorer__route"
                disabled={!parsed}
                onClick={() => {
                  if (!parsed) return;
                  patchRequest(parsed);
                }}
              >
                <code>{route.path}</code>
                <small>{route.methods.join(", ")}</small>
              </button>
            );
          })}
          {routes.length === 0 && <p>Route manifest unavailable.</p>}
        </div>
      </div>
    </section>
  );
}
