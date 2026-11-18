import { memo, useMemo, useState } from "react";
import { buildSearchIndex } from "../search";
import { type BlockDocument, type SearchHit } from "../types";

export interface BlockSearchPanelProps {
  documents: BlockDocument[];
  onSelect?: (hit: SearchHit) => void;
}

export const BlockSearchPanel = memo(function BlockSearchPanel({
  documents,
  onSelect,
}: BlockSearchPanelProps) {
  const [query, setQuery] = useState("");
  const index = useMemo(() => buildSearchIndex(documents), [documents]);
  const hits = useMemo(
    () => (query.trim() ? index.search(query, { limit: 30 }) : []),
    [index, query],
  );
  return (
    <section className="block-search" aria-label="Block search">
      <input
        aria-label="Search blocks"
        className="block-search__input"
        placeholder="Search blocks…"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="block-search__meta">
        {index.size} blocks · {index.vocabulary().length} terms
      </div>
      <ul className="block-search__results">
        {hits.map((hit) => (
          <li key={`${hit.documentId}:${hit.blockId}`}>
            <button type="button" onClick={() => onSelect?.(hit)}>
              <span className="block-search__type">{hit.blockType}</span>
              <span className="block-search__snippet">{hit.snippet}</span>
              <span className="block-search__score">{hit.score}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
});

export function emptySearchMessage(query: string, hits: SearchHit[]): string {
  if (!query.trim()) return "Type to search blocks";
  return hits.length === 0 ? "No matching blocks" : `${hits.length} results`;
}
