/** Drag-and-drop ingest strip with per-item integrity badges. */

import {
  badgeFromReport,
  ingestProgressLabel,
  phaseTone,
  totalIngestBytes,
} from "../ingestModel";
import { badgeLabel, badgeTone, formatBytes, maskHash } from "../format";
import type { IngestItem } from "../types";

export interface IngestStripProps {
  items: readonly IngestItem[];
  dragging: boolean;
  onFiles: (files: File[]) => void;
  onDrag: (active: boolean) => void;
  onRemove: (id: string) => void;
}

export function IngestStrip({
  items,
  dragging,
  onFiles,
  onDrag,
  onRemove,
}: IngestStripProps) {
  return (
    <div className="elf-ingest" data-testid="ingest-strip">
      <div
        className="elf-ingest__drop"
        data-testid="ingest-dropzone"
        data-dragging={dragging}
        onDragEnter={(event) => {
          event.preventDefault();
          onDrag(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          onDrag(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          onDrag(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          onDrag(false);
          onFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <strong>{dragging ? "Release to ingest" : "Drop evidence here"}</strong>
        <span>Hashes verified locally · no uploads</span>
        <label className="elf-button elf-button--small">
          Choose files
          <input
            type="file"
            multiple
            className="elf-visually-hidden"
            data-testid="ingest-file-input"
            aria-label="Choose evidence files"
            onChange={(event) => {
              onFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </label>
      </div>
      <div className="elf-ingest__strip" data-testid="ingest-items">
        {items.map((item) => {
          const badge = badgeFromReport(item.report);
          return (
            <article
              key={item.id}
              className="elf-ingest__item"
              data-testid="ingest-item"
              data-phase={item.phase}
              data-tone={phaseTone(item.phase)}
            >
              <header>
                <span className="elf-ingest__name" title={item.file.name}>
                  {item.file.name}
                </span>
                <button
                  type="button"
                  className="elf-ingest__remove"
                  aria-label={`Remove ${item.file.name}`}
                  data-testid="ingest-remove"
                  onClick={() => onRemove(item.id)}
                >
                  ×
                </button>
              </header>
              <div className="elf-ingest__meta">
                {formatBytes(item.file.size)} · {ingestProgressLabel(item)}
              </div>
              <div
                className="elf-ingest__badge"
                data-testid="integrity-badge"
                data-tone={
                  badgeTone(badge) !== "neutral"
                    ? badgeTone(badge)
                    : phaseTone(item.phase)
                }
              >
                {badge
                  ? badgeLabel(badge)
                  : phaseTone(item.phase).toUpperCase()}
              </div>
              {item.report && (
                <code className="elf-ingest__hash">
                  {maskHash(item.report.panel.sha256, 6)}
                </code>
              )}
              {item.phase === "reading" && (
                <div className="elf-ingest__progress">
                  <div
                    style={{ width: `${Math.round(item.progress * 100)}%` }}
                  />
                </div>
              )}
            </article>
          );
        })}
        {items.length === 0 && (
          <p className="elf-empty" data-testid="ingest-empty">
            No files ingested yet.
          </p>
        )}
      </div>
      <footer className="elf-ingest__footer">
        <span>{items.length} item(s)</span>
        <span>{formatBytes(totalIngestBytes(items))} total</span>
      </footer>
    </div>
  );
}
