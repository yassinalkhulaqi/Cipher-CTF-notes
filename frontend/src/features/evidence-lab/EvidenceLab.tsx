/** Evidence lab workbench: ingest, inspect, navigate, compare. */

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import { EvidenceLabClient } from "./client";
import { ComparisonView } from "./components/ComparisonView";
import { CustodyTimeline } from "./components/CustodyTimeline";
import { HexViewer } from "./components/HexViewer";
import { IngestStrip } from "./components/IngestStrip";
import { StringsEntropyTabs } from "./components/StringsEntropyTabs";
import { parseOffset } from "./format";
import { createIngestItem, validateDrop } from "./ingestModel";
import { initialLabState, labReducer } from "./state";
import type { BundleEntryData, CustodyGraphData } from "./types";
import "./evidence-lab.css";

export interface EvidenceLabProps {
  api?: EvidenceLabClient;
  className?: string;
}

function entryFromReport(
  ref: string,
  panel: EvidenceReportDataLike,
): BundleEntryData {
  return {
    key: ref,
    sha256: panel.sha256,
    blake2b: panel.blake2b,
    size_bytes: panel.size_bytes,
    label: ref,
  };
}

type EvidenceReportDataLike = {
  sha256: string;
  blake2b: string;
  size_bytes: number;
};

export function EvidenceLab({
  api: suppliedApi,
  className = "",
}: EvidenceLabProps) {
  const [state, dispatch] = useReducer(labReducer, undefined, initialLabState);
  const api = useMemo(
    () => suppliedApi ?? new EvidenceLabClient(),
    [suppliedApi],
  );
  const sources = useRef<Map<string, Uint8Array>>(new Map());
  const ingestCounter = useRef(0);
  const report = state.report;
  const selectedRef = report?.ref ?? "";

  useEffect(() => {
    let active = true;
    api
      .manifest()
      .then((manifest) => {
        if (active) dispatch({ type: "manifest", manifest });
      })
      .catch((error: unknown) => {
        if (active) {
          dispatch({
            type: "failed",
            message:
              error instanceof Error
                ? error.message
                : "Unable to load lab manifest",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [api]);

  const navigate = useCallback(
    async (offset: number) => {
      const bytes = sources.current.get(selectedRef);
      if (!bytes) return;
      dispatch({ type: "loading" });
      try {
        const window = await api.hex(
          selectedRef,
          bytes,
          offset,
          Math.max(256, state.bytesPerRow * 32),
          state.bytesPerRow,
        );
        dispatch({ type: "window", window });
        dispatch({ type: "offset-input", value: offset.toString(16) });
      } catch (error) {
        dispatch({
          type: "failed",
          message:
            error instanceof Error ? error.message : "Unable to read range",
        });
      }
    },
    [api, selectedRef, sources, state.bytesPerRow],
  );

  const handleFiles = useCallback(
    async (files: File[]) => {
      const validation = validateDrop(files, state.manifest?.max_payload_bytes);
      for (const rejected of validation.rejected) {
        dispatch({
          type: "notice",
          tone: "bad",
          message: `${rejected.file.name}: ${rejected.reason}`,
        });
      }
      const items = validation.accepted.map((file) => {
        ingestCounter.current += 1;
        return createIngestItem(file as File, ingestCounter.current);
      });
      dispatch({ type: "queue", items });
      for (const item of items) {
        try {
          dispatch({
            type: "ingest-patch",
            id: item.id,
            patch: { phase: "reading", progress: 0.1 },
          });
          const bytes = new Uint8Array(await item.file.arrayBuffer());
          dispatch({
            type: "ingest-patch",
            id: item.id,
            patch: { phase: "inspecting", progress: 0.5 },
          });
          const ref = `evidence:${item.file.name}`;
          sources.current.set(ref, bytes);
          const inspected = await api.inspect(item.file.name, bytes, {
            filename: item.file.name,
            hexLength: Math.max(256, state.bytesPerRow * 32),
            bytesPerRow: state.bytesPerRow,
          });
          dispatch({ type: "report", report: inspected });
          dispatch({
            type: "ingest-patch",
            id: item.id,
            patch: {
              phase: inspected.badge.ok ? "verified" : "mismatch",
              progress: 1,
              report: inspected,
              message: inspected.badge.reasons.join(", "),
            },
          });
          const steps = [
            {
              evidence_id: item.file.name,
              action: "acquired",
              actor: "local",
              timestamp: inspected.panel.computed_at,
              sequence: 1,
            },
            {
              evidence_id: item.file.name,
              action: inspected.badge.ok ? "verified" : "mismatch",
              actor: "evidence-lab",
              timestamp: inspected.panel.computed_at,
              sequence: 2,
            },
          ];
          const graph: CustodyGraphData = await api.custody(
            item.file.name,
            steps,
          );
          dispatch({ type: "graph", graph });
        } catch (error) {
          dispatch({
            type: "ingest-patch",
            id: item.id,
            patch: {
              phase: "rejected",
              message:
                error instanceof Error ? error.message : "Inspection failed",
            },
          });
        }
      }
    },
    [api, state.bytesPerRow, state.manifest?.max_payload_bytes],
  );

  const compareIngested = useCallback(async () => {
    const reports = state.ingest
      .filter((item) => item.report !== null)
      .slice(0, 2)
      .map((item) => item.report!);
    if (reports.length < 2) {
      dispatch({
        type: "notice",
        tone: "warn",
        message: "Ingest at least two evidence items to compare bundles.",
      });
      return;
    }
    try {
      const left = [entryFromReport(reports[0].ref, reports[0].panel)];
      const right = [entryFromReport(reports[1].ref, reports[1].panel)];
      const diff = await api.compare(left, right);
      dispatch({ type: "diff", diff });
    } catch (error) {
      dispatch({
        type: "failed",
        message: error instanceof Error ? error.message : "Comparison failed",
      });
    }
  }, [api, state.ingest]);

  const submitOffset = useCallback(
    (value: string) => {
      const parsed = parseOffset(value);
      if (parsed !== null) void navigate(parsed);
    },
    [navigate],
  );

  return (
    <section
      className={`elf-lab ${className}`.trim()}
      data-testid="evidence-lab"
      data-density="compact"
    >
      <header className="elf-lab__header">
        <div>
          <h2>Evidence Lab</h2>
          <p>
            {state.manifest
              ? `${state.manifest.signatures} signatures · ${state.manifest.records} records · chunk ${state.manifest.chunk_size}`
              : "Loading lab capabilities..."}
          </p>
        </div>
        <button
          type="button"
          className="elf-button"
          data-testid="compare-ingested"
          onClick={() => void compareIngested()}
        >
          Compare ingested
        </button>
      </header>

      {state.error && (
        <div
          className="elf-notice"
          data-tone="bad"
          role="alert"
          data-testid="lab-error"
        >
          {state.error}
        </div>
      )}
      {state.notices.map((notice) => (
        <div
          key={notice.id}
          className="elf-notice"
          data-tone={notice.tone}
          data-testid="lab-notice"
        >
          {notice.message}
        </div>
      ))}

      <IngestStrip
        items={state.ingest}
        dragging={state.dragging}
        onFiles={(files) => void handleFiles(files)}
        onDrag={(active) => dispatch({ type: "drag", active })}
        onRemove={(id) =>
          dispatch({
            type: "ingest-patch",
            id,
            patch: { phase: "rejected", message: "Removed by user" },
          })
        }
      />

      <div className="elf-lab__body">
        <div className="elf-lab__primary">
          <StringsEntropyTabs
            tab={state.tab}
            report={report}
            query={state.stringQuery}
            kind={state.stringKind}
            onTab={(tab) => dispatch({ type: "tab", tab })}
            onQuery={(query) => dispatch({ type: "string-query", query })}
            onKind={(kind) => dispatch({ type: "string-kind", kind })}
            onHitClick={(offset) => void navigate(offset)}
          />
          {state.tab === "hex" && (
            <HexViewer
              window={state.window}
              offsetInput={state.offsetInput}
              bytesPerRow={state.bytesPerRow}
              loading={state.loading}
              onNavigate={(offset) => void navigate(offset)}
              onOffsetInput={(value) =>
                dispatch({ type: "offset-input", value })
              }
              onBytesPerRow={(value) =>
                dispatch({ type: "bytes-per-row", value })
              }
              onAnchor={(offset) => dispatch({ type: "anchor", offset })}
              onHead={(offset) => dispatch({ type: "head", offset })}
            />
          )}
        </div>
        <aside className="elf-lab__secondary">
          <CustodyTimeline graph={state.graph} />
          <ComparisonView diff={state.diff} />
        </aside>
      </div>
      <footer className="elf-lab__footer">
        <span>Offset: {state.offsetInput}</span>
        <button
          type="button"
          className="elf-button elf-button--small"
          onClick={() => submitOffset(state.offsetInput)}
          data-testid="footer-goto"
        >
          Jump to offset
        </button>
      </footer>
    </section>
  );
}

export default EvidenceLab;
