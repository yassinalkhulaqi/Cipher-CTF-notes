import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { createRoot } from "react-dom/client";
import { EvidenceVaultApi } from "./client";
import { EvidenceDetailPanel } from "./components/EvidenceDetailPanel";
import { EvidenceTable } from "./components/EvidenceTable";
import { IngestPanel } from "./components/IngestPanel";
import { ManifestPanel } from "./components/ManifestPanel";
import {
  KIND_LABELS,
  STATUS_LABELS,
  formatBytes,
  normalizeHexPrefix,
  totalBytes,
} from "./format";
import {
  evidenceReducer,
  hasActiveFilters,
  initialEvidenceState,
  selectIntegrity,
  selectSelected,
  selectVisible,
  summaryFromRecord,
} from "./state";
import type { EvidenceStatus, EvidenceUpload, ManifestPreview } from "./types";
import "./evidence.css";

export interface EvidenceVaultProps {
  api?: EvidenceVaultApi;
  className?: string;
}

export function EvidenceVault({
  api: suppliedApi,
  className = "",
}: EvidenceVaultProps) {
  const [state, dispatch] = useReducer(
    evidenceReducer,
    undefined,
    initialEvidenceState,
  );
  const [preview, setPreview] = useState<ManifestPreview | null>(null);
  const api = useMemo(
    () => suppliedApi ?? new EvidenceVaultApi(),
    [suppliedApi],
  );
  const visible = useMemo(() => selectVisible(state), [state]);

  const refresh = useCallback(async () => {
    dispatch({ type: "loading" });
    try {
      const [items, stats] = await Promise.all([api.list(), api.stats()]);
      dispatch({ type: "loaded", items, stats });
    } catch (error) {
      dispatch({
        type: "failed",
        message:
          error instanceof Error
            ? error.message
            : "Unable to load evidence vault",
      });
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadDetail = useCallback(
    async (id: string) => {
      if (!id) return;
      try {
        const detail = await api.detail(id);
        dispatch({ type: "detail", detail });
        dispatch({ type: "integrity", id, report: detail.integrity });
        dispatch({ type: "custody", custody: detail.custody });
      } catch (error) {
        dispatch({
          type: "notice",
          tone: "bad",
          message:
            error instanceof Error
              ? error.message
              : "Unable to load evidence detail",
        });
      }
    },
    [api],
  );

  const select = useCallback(
    (id: string) => {
      dispatch({ type: "select", id });
      void loadDetail(id);
    },
    [loadDetail],
  );

  const upload = useCallback(
    async (uploaded: EvidenceUpload) => {
      try {
        const record = await api.ingestUpload(uploaded);
        dispatch({ type: "upsert", item: summaryFromRecord(record) });
        dispatch({
          type: "notice",
          tone: "good",
          message: `Ingested ${record.original_filename} · ${record.id}`,
        });
        await loadDetail(record.id);
        const stats = await api.stats();
        dispatch({ type: "stats", stats });
      } catch (error) {
        dispatch({
          type: "notice",
          tone: "bad",
          message: error instanceof Error ? error.message : "Ingest failed",
        });
      }
    },
    [api, loadDetail],
  );

  const verifySelected = useCallback(async () => {
    if (!state.selectedId) return;
    try {
      const report = await api.verify(state.selectedId);
      dispatch({ type: "integrity", id: state.selectedId, report });
      dispatch({
        type: "notice",
        tone: report.state === "verified" ? "good" : "warn",
        message: `Integrity: ${report.state}`,
      });
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message: error instanceof Error ? error.message : "Verification failed",
      });
    }
  }, [api, state.selectedId]);

  const verifyAll = useCallback(async () => {
    try {
      const result = await api.verifyAll();
      for (const report of result.reports) {
        dispatch({ type: "integrity", id: report.evidence_id, report });
      }
      dispatch({
        type: "notice",
        tone: "info",
        message: `Verified ${result.reports.length} evidence items`,
      });
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message: error instanceof Error ? error.message : "Verification failed",
      });
    }
  }, [api]);

  const verifyCustody = useCallback(async () => {
    if (!state.selectedId) return;
    try {
      const result = await api.verifyCustody(state.selectedId);
      dispatch({
        type: "notice",
        tone: result.valid ? "good" : "bad",
        message: result.valid
          ? "Custody chain is valid"
          : "Custody chain has problems",
      });
      await loadDetail(state.selectedId);
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message:
          error instanceof Error
            ? error.message
            : "Custody verification failed",
      });
    }
  }, [api, loadDetail, state.selectedId]);

  const exportManifest = useCallback(async () => {
    try {
      const manifest = await api.exportManifest();
      dispatch({ type: "manifest", manifest });
      setPreview(null);
      dispatch({
        type: "notice",
        tone: "good",
        message: `Manifest exported · ${manifest.checksum.slice(0, 12)}`,
      });
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message:
          error instanceof Error ? error.message : "Manifest export failed",
      });
    }
  }, [api]);

  const previewImport = useCallback(async () => {
    try {
      const manifest = state.manifest ?? (await api.exportManifest());
      if (!state.manifest) dispatch({ type: "manifest", manifest });
      const result = await api.previewImport(manifest);
      setPreview(result);
      dispatch({
        type: "notice",
        tone: result.valid ? "info" : "warn",
        message: result.valid
          ? "Import preview is valid"
          : "Import preview has problems",
      });
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message:
          error instanceof Error ? error.message : "Import preview failed",
      });
    }
  }, [api, state.manifest]);

  const importManifest = useCallback(async () => {
    if (!state.manifest || !preview?.valid) return;
    try {
      const result = await api.importManifest(state.manifest);
      setPreview(null);
      dispatch({
        type: "notice",
        tone: "good",
        message: `Imported ${result.created.length} evidence items`,
      });
      await refresh();
    } catch (error) {
      dispatch({
        type: "notice",
        tone: "bad",
        message:
          error instanceof Error ? error.message : "Manifest import failed",
      });
    }
  }, [api, preview?.valid, refresh, state.manifest]);

  const changeStatus = useCallback(
    async (status: EvidenceStatus) => {
      if (!state.selectedId) return;
      try {
        const record = await api.setStatus(state.selectedId, status);
        dispatch({ type: "status", id: record.id, status: record.status });
        await loadDetail(record.id);
      } catch (error) {
        dispatch({
          type: "notice",
          tone: "bad",
          message:
            error instanceof Error ? error.message : "Status change failed",
        });
      }
    },
    [api, loadDetail, state.selectedId],
  );

  const selected = selectSelected(state);
  const integrity = state.selectedId ? selectIntegrity(state) : undefined;

  return (
    <div
      className={`evidence-vault ${state.dragging ? "is-dragging" : ""} ${className}`.trim()}
    >
      <header className="ev-header">
        <div>
          <span className="ev-eyebrow">V2 evidence vault</span>
          <h1>Evidence</h1>
          <p>
            Capture, hash, and audit every artifact in one chain of custody.
          </p>
        </div>
        <div className="ev-header__metrics">
          <div>
            <strong>{state.stats?.total ?? state.items.length}</strong>
            <span>Items</span>
          </div>
          <div>
            <strong>{formatBytes(totalBytes(state.items))}</strong>
            <span>Captured</span>
          </div>
          <div>
            <strong>{state.stats?.verified ?? 0}</strong>
            <span>Verified</span>
          </div>
          <div>
            <strong>{state.stats?.alerts ?? 0}</strong>
            <span>Alerts</span>
          </div>
        </div>
      </header>

      <div className="ev-toolbar">
        <label className="ev-search">
          <Search size={15} aria-hidden="true" />
          <input
            value={state.filters.query}
            onChange={(event) =>
              dispatch({
                type: "set-filter",
                key: "query",
                value: event.target.value,
              })
            }
            placeholder="Search titles, filenames, hashes, tags…"
          />
        </label>
        <label>
          <span>Status</span>
          <select
            value={state.filters.status}
            onChange={(event) =>
              dispatch({
                type: "set-filter",
                key: "status",
                value: event.target.value,
              })
            }
          >
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Kind</span>
          <select
            value={state.filters.kind}
            onChange={(event) =>
              dispatch({
                type: "set-filter",
                key: "kind",
                value: event.target.value,
              })
            }
          >
            <option value="">All</option>
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Tag</span>
          <input
            value={state.filters.tag}
            onChange={(event) =>
              dispatch({
                type: "set-filter",
                key: "tag",
                value: event.target.value,
              })
            }
            placeholder="any"
          />
        </label>
        <label>
          <span>Hash</span>
          <input
            value={state.filters.hashPrefix}
            onChange={(event) =>
              dispatch({
                type: "set-filter",
                key: "hashPrefix",
                value: normalizeHexPrefix(event.target.value),
              })
            }
            placeholder="sha256 prefix"
          />
        </label>
        <button
          type="button"
          className="ev-btn"
          onClick={() => dispatch({ type: "reset-filters" })}
          disabled={!hasActiveFilters(state.filters)}
        >
          Clear
        </button>
        <button type="button" className="ev-btn" onClick={() => void refresh()}>
          <RefreshCw size={14} aria-hidden="true" /> Refresh
        </button>
        <button
          type="button"
          className="ev-btn"
          onClick={() => void verifyAll()}
        >
          <ShieldCheck size={14} aria-hidden="true" /> Verify all
        </button>
      </div>

      <IngestPanel
        busy={state.loading}
        onUpload={(uploaded) => void upload(uploaded)}
        onDrag={(active) => dispatch({ type: "drag", active })}
      />

      {state.error ? (
        <div className="ev-alert ev-alert--bad" role="alert">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>{state.error}</span>
          <button
            type="button"
            onClick={() => dispatch({ type: "cleared-error" })}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {state.notices.length > 0 ? (
        <div className="ev-notices" aria-live="polite">
          {state.notices.map((notice) => (
            <div
              className={`ev-alert ev-alert--${notice.tone}`}
              key={notice.id}
            >
              {notice.tone === "good" ? (
                <CheckCircle2 size={15} aria-hidden="true" />
              ) : (
                <AlertTriangle size={15} aria-hidden="true" />
              )}
              <span>{notice.message}</span>
              <button
                type="button"
                onClick={() =>
                  dispatch({ type: "dismiss-notice", id: notice.id })
                }
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <div className="ev-body">
        <main className="ev-main">
          <div className="ev-main__bar">
            <strong>
              {visible.length} of {state.items.length} items
            </strong>
            {selected ? (
              <label>
                <span>Status</span>
                <select
                  value={selected.status}
                  onChange={(event) =>
                    void changeStatus(event.target.value as EvidenceStatus)
                  }
                >
                  {Object.keys(STATUS_LABELS).map((status) => (
                    <option key={status} value={status}>
                      {STATUS_LABELS[status as EvidenceStatus]}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          <EvidenceTable
            items={visible}
            selectedId={state.selectedId}
            integrity={state.integrity}
            onSelect={select}
          />
          <ManifestPanel
            manifest={state.manifest}
            preview={preview}
            onExport={() => void exportManifest()}
            onPreview={() => void previewImport()}
            onImport={() => void importManifest()}
          />
        </main>
        {state.detail ? (
          <EvidenceDetailPanel
            detail={state.detail}
            onVerify={() => void verifySelected()}
            onVerifyCustody={() => void verifyCustody()}
            onRefreshLinks={() => void loadDetail(state.selectedId)}
            onExport={() => void exportManifest()}
          />
        ) : (
          <aside className="ev-detail ev-detail--empty">
            <ShieldCheck size={28} aria-hidden="true" />
            <strong>Select an evidence item</strong>
            <p>
              Integrity, provenance, custody, and retention details appear here.
            </p>
            {integrity ? <span>Last state: {integrity.state}</span> : null}
          </aside>
        )}
      </div>
    </div>
  );
}

export function mountEvidenceVault(
  container: HTMLElement,
  options: { api?: EvidenceVaultApi } = {},
): () => void {
  const root = createRoot(container);
  root.render(<EvidenceVault api={options.api} />);
  return () => root.unmount();
}
