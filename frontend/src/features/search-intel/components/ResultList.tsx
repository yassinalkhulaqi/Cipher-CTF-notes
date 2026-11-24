/** Ranked result list with highlighted fragments and pivot affordances. */

import { formatScore, kindLabel, severityTone } from "../format";
import { splitFragment } from "../highlight";
import type { RankedHitV2 } from "../types";

export interface ResultListProps {
  hits: RankedHitV2[];
  selectedRef?: string;
  onSelect?: (hit: RankedHitV2) => void;
}

export function ResultList({
  hits,
  selectedRef = "",
  onSelect,
}: ResultListProps) {
  if (!hits.length) {
    return <p className="si-results__empty">No entities matched this query.</p>;
  }
  return (
    <ol className="si-results" data-testid="search-results">
      {hits.map((hit) => {
        const doc = hit.document;
        const chunks = splitFragment(hit.fragment);
        return (
          <li data-ref={doc.ref} key={doc.ref}>
            <button
              aria-pressed={doc.ref === selectedRef}
              className="si-result v3-focusable"
              data-kind={doc.kind}
              data-selected={doc.ref === selectedRef}
              data-testid="search-result"
              onClick={() => onSelect?.(hit)}
              type="button"
            >
              <span className="si-result__head">
                <span className="si-result__kind">
                  {kindLabel(String(doc.kind))}
                </span>
                {doc.severity && (
                  <span
                    className="si-result__severity"
                    data-tone={severityTone(doc.severity)}
                  >
                    {doc.severity}
                  </span>
                )}
                <strong className="si-result__title">{doc.title}</strong>
                <span className="si-result__score">
                  {formatScore(hit.score)}
                </span>
              </span>
              <span className="si-result__fragment">
                {hit.fragment.prefix && <span aria-hidden="true">…</span>}
                {chunks.map((chunk, index) =>
                  chunk.match ? (
                    <mark data-testid="search-highlight" key={index}>
                      {chunk.text}
                    </mark>
                  ) : (
                    <span key={index}>{chunk.text}</span>
                  ),
                )}
                {hit.fragment.suffix && <span aria-hidden="true">…</span>}
              </span>
              <span className="si-result__meta">
                <code>{doc.ref}</code>
                {doc.tags.map((tag) => (
                  <span className="si-result__tag" key={tag}>
                    #{tag}
                  </span>
                ))}
                {doc.has_links && (
                  <span className="si-result__links">
                    {doc.link_degree} links
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
