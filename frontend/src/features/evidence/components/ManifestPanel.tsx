import { Braces, Download, FileJson, Upload } from "lucide-react";
import { formatBytes, manifestEntryLabel, truncateMiddle } from "../format";
import type { EvidenceManifest, ManifestPreview } from "../types";

interface ManifestPanelProps {
  manifest: EvidenceManifest | null;
  preview: ManifestPreview | null;
  onExport: () => void;
  onPreview: () => void;
  onImport: () => void;
}

export function ManifestPanel({
  manifest,
  preview,
  onExport,
  onPreview,
  onImport,
}: ManifestPanelProps) {
  return (
    <section className="ev-manifest" aria-label="Manifest portability">
      <header>
        <div>
          <span className="ev-eyebrow">Portability</span>
          <h2>Manifest</h2>
        </div>
        <div className="ev-manifest__actions">
          <button type="button" className="ev-btn" onClick={onExport}>
            <Download size={14} aria-hidden="true" /> Export
          </button>
          <button type="button" className="ev-btn" onClick={onPreview}>
            <Braces size={14} aria-hidden="true" /> Preview import
          </button>
          <button
            type="button"
            className="ev-btn ev-btn--primary"
            disabled={!preview?.valid}
            onClick={onImport}
          >
            <Upload size={14} aria-hidden="true" /> Import
          </button>
        </div>
      </header>
      {manifest ? (
        <>
          <dl className="ev-manifest__summary">
            <div>
              <dt>Version</dt>
              <dd>{manifest.version}</dd>
            </div>
            <div>
              <dt>Records</dt>
              <dd>{manifest.records.length}</dd>
            </div>
            <div>
              <dt>Entries</dt>
              <dd>{manifest.entries.length}</dd>
            </div>
            <div>
              <dt>Custody</dt>
              <dd>{manifest.custody.length}</dd>
            </div>
            <div>
              <dt>Links</dt>
              <dd>{manifest.links.length}</dd>
            </div>
            <div>
              <dt>Checksum</dt>
              <dd>
                <code title={manifest.checksum}>
                  {truncateMiddle(manifest.checksum, 18)}
                </code>
              </dd>
            </div>
          </dl>
          <ul className="ev-manifest__entries">
            {manifest.entries.slice(0, 8).map((entry) => (
              <li key={entry.evidence_id}>
                <FileJson size={13} aria-hidden="true" />
                <span>{manifestEntryLabel(entry)}</span>
                <small>{formatBytes(entry.size_bytes)}</small>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="ev-note">No manifest exported for this session.</p>
      )}
      {preview ? (
        <div className="ev-manifest__preview">
          <strong>Import preview</strong>
          <span>
            {preview.valid ? "Valid" : "Invalid"} · create{" "}
            {preview.plan.create.length} · update {preview.plan.update.length} ·
            skip {preview.plan.skip.length}
          </span>
        </div>
      ) : null}
    </section>
  );
}
