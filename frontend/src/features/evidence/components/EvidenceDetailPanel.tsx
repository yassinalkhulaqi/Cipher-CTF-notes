import {
  BadgeCheck,
  FileWarning,
  Fingerprint,
  Link2,
  ShieldCheck,
  Timer,
} from "lucide-react";
import {
  formatBytes,
  formatTimestamp,
  integrityLabel,
  issueSummary,
  kindLabel,
  maskHash,
  statusLabel,
} from "../format";
import type { EvidenceDetail } from "../types";
import { IntegrityBadge } from "./IntegrityBadge";

interface EvidenceDetailPanelProps {
  detail: EvidenceDetail;
  onVerify: () => void;
  onVerifyCustody: () => void;
  onRefreshLinks: () => void;
  onExport: () => void;
}

export function EvidenceDetailPanel({
  detail,
  onVerify,
  onVerifyCustody,
  onRefreshLinks,
  onExport,
}: EvidenceDetailPanelProps) {
  const { record, integrity, custody, provenance, links, retention } = detail;
  return (
    <aside className="ev-detail" aria-label="Evidence details">
      <header className="ev-detail__header">
        <div>
          <span className="ev-eyebrow">{kindLabel(record.kind)}</span>
          <h2>{record.title}</h2>
          <p>{record.description || "No description recorded."}</p>
        </div>
        <span className={`ev-status ev-status--${record.status}`}>
          {statusLabel(record.status)}
        </span>
      </header>

      <section className="ev-detail__section">
        <h3>
          <Fingerprint size={15} aria-hidden="true" /> Digests
        </h3>
        <dl className="ev-definitions">
          <div>
            <dt>SHA-256</dt>
            <dd>
              <code title={record.digests.sha256}>{record.digests.sha256}</code>
            </dd>
          </div>
          <div>
            <dt>MD5</dt>
            <dd>
              <code title={record.digests.md5}>{record.digests.md5}</code>
            </dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{formatBytes(record.digests.size_bytes)}</dd>
          </div>
          <div>
            <dt>MIME</dt>
            <dd>{record.mime.mime_type}</dd>
          </div>
        </dl>
      </section>

      <section className="ev-detail__section">
        <h3>
          <ShieldCheck size={15} aria-hidden="true" /> Integrity
        </h3>
        <div className="ev-detail__integrity">
          <IntegrityBadge report={integrity} />
          <button type="button" className="ev-btn" onClick={onVerify}>
            <BadgeCheck size={14} aria-hidden="true" /> Verify now
          </button>
        </div>
        <p className="ev-note">{issueSummary(integrity)}</p>
        <p className="ev-meta">
          State: {integrityLabel(integrity.state)} · Checked{" "}
          {formatTimestamp(integrity.checked_at)}
        </p>
      </section>

      <section className="ev-detail__section">
        <h3>
          <Link2 size={15} aria-hidden="true" /> Provenance
        </h3>
        <dl className="ev-definitions">
          <div>
            <dt>Operator</dt>
            <dd>{String(provenance.summary.operator ?? "—")}</dd>
          </div>
          <div>
            <dt>Method</dt>
            <dd>{String(provenance.summary.method ?? "—")}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{String(provenance.summary.source_path ?? "—")}</dd>
          </div>
          <div>
            <dt>Case</dt>
            <dd>{String(provenance.summary.case_reference ?? "—")}</dd>
          </div>
        </dl>
        {provenance.missing_fields.length > 0 ? (
          <p className="ev-note ev-note--warn">
            Missing: {provenance.missing_fields.join(", ")}
          </p>
        ) : null}
      </section>

      <section className="ev-detail__section">
        <h3>
          <ShieldCheck size={15} aria-hidden="true" /> Custody
        </h3>
        <div className="ev-detail__integrity">
          <span
            className={`ev-badge ${custody.valid ? "ev-badge--good" : "ev-badge--bad"}`}
          >
            {custody.valid ? "Chain valid" : "Chain invalid"}
          </span>
          <button type="button" className="ev-btn" onClick={onVerifyCustody}>
            Re-verify chain
          </button>
        </div>
        <ol className="ev-timeline">
          {custody.events.slice(-6).map((event) => (
            <li key={event.id}>
              <strong>{event.action}</strong>
              <span>
                {event.actor} · {formatTimestamp(event.timestamp)}
              </span>
              <small title={event.event_hash}>
                {maskHash(event.event_hash)}
              </small>
            </li>
          ))}
        </ol>
      </section>

      <section className="ev-detail__section">
        <h3>
          <Link2 size={15} aria-hidden="true" /> Findings
        </h3>
        <div className="ev-detail__integrity">
          <span className="ev-badge ev-badge--neutral">
            {links.summary.total ?? 0} links
          </span>
          <button type="button" className="ev-btn" onClick={onRefreshLinks}>
            Refresh
          </button>
        </div>
        {links.links.length === 0 ? (
          <p className="ev-note">No findings linked to this item.</p>
        ) : (
          <ul className="ev-links">
            {links.links.map((link) => (
              <li key={link.id}>
                <strong>{link.finding_title || link.finding_id}</strong>
                <span>
                  {link.link_type} · {Math.round(link.strength * 100)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="ev-detail__section">
        <h3>
          <Timer size={15} aria-hidden="true" /> Retention
        </h3>
        {retention.policy ? (
          <dl className="ev-definitions">
            <div>
              <dt>Basis</dt>
              <dd>{retention.policy.basis}</dd>
            </div>
            <div>
              <dt>Retain</dt>
              <dd>{retention.policy.retain_days} days</dd>
            </div>
            <div>
              <dt>Legal hold</dt>
              <dd>{retention.policy.legal_hold ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Decision</dt>
              <dd>{retention.decision?.action ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="ev-note">No retention policy set.</p>
        )}
      </section>

      <footer className="ev-detail__footer">
        <button
          type="button"
          className="ev-btn ev-btn--primary"
          onClick={onExport}
        >
          Export manifest
        </button>
        <span className="ev-meta">
          <FileWarning size={13} aria-hidden="true" /> Read-only audit view
        </span>
      </footer>
    </aside>
  );
}
