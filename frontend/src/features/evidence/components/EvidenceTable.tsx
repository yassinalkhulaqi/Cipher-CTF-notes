import { FileSearch } from "lucide-react";
import {
  formatBytes,
  formatTimestamp,
  kindLabel,
  maskHash,
  statusLabel,
} from "../format";
import type { EvidenceSummary, IntegrityReport } from "../types";
import { IntegrityBadge } from "./IntegrityBadge";

interface EvidenceTableProps {
  items: EvidenceSummary[];
  selectedId: string;
  integrity: Record<string, IntegrityReport>;
  onSelect: (id: string) => void;
}

export function EvidenceTable({
  items,
  selectedId,
  integrity,
  onSelect,
}: EvidenceTableProps) {
  if (items.length === 0) {
    return (
      <div className="ev-empty">
        <FileSearch size={22} aria-hidden="true" />
        <strong>No evidence matches these filters</strong>
        <span>Ingest a file or clear the filters to see the full vault.</span>
      </div>
    );
  }

  return (
    <div className="ev-table-wrap">
      <table className="ev-table">
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Kind</th>
            <th scope="col">Status</th>
            <th scope="col">Integrity</th>
            <th scope="col">Size</th>
            <th scope="col">SHA-256</th>
            <th scope="col">Captured</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              className={item.id === selectedId ? "is-selected" : ""}
              onClick={() => onSelect(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ")
                  onSelect(item.id);
              }}
              tabIndex={0}
              aria-selected={item.id === selectedId}
            >
              <td>
                <span className="ev-table__title">{item.title}</span>
                <span className="ev-table__filename">
                  {item.original_filename}
                </span>
                {item.tags.length > 0 ? (
                  <span className="ev-table__tags">
                    {item.tags.slice(0, 3).map((tag) => (
                      <span className="ev-tag" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </span>
                ) : null}
              </td>
              <td>{kindLabel(item.kind)}</td>
              <td>
                <span className={`ev-status ev-status--${item.status}`}>
                  {statusLabel(item.status)}
                </span>
              </td>
              <td>
                <IntegrityBadge report={integrity[item.id]} compact />
              </td>
              <td>{formatBytes(item.size_bytes)}</td>
              <td>
                <code title={item.sha256}>{maskHash(item.sha256)}</code>
              </td>
              <td>{formatTimestamp(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
