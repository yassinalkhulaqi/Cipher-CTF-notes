import { memo } from "react";
import { diffCounts } from "../diff";
import { type BlockDocument, type DocumentDiff } from "../types";

export interface BlockDiffViewProps {
  diff: DocumentDiff;
  before?: BlockDocument;
  after?: BlockDocument;
  onSelectBlock?: (blockId: string) => void;
}

export const BlockDiffView = memo(function BlockDiffView({
  diff,
  before,
  after,
  onSelectBlock,
}: BlockDiffViewProps) {
  const counts = diffCounts(diff);
  return (
    <section className="block-diff" aria-label="Block changes">
      <header className="block-diff__summary">
        <span>+{counts.add}</span>
        <span>-{counts.remove}</span>
        <span>~{counts.replace}</span>
        <span>↕{counts.move}</span>
      </header>
      <ul className="block-diff__list">
        {diff.entries.map((entry, index) => (
          <li
            className={`block-diff__entry block-diff__entry--${entry.operation}`}
            key={`${entry.blockId}-${index}`}
          >
            <button
              type="button"
              onClick={() => onSelectBlock?.(entry.blockId)}
            >
              {entry.description}
            </button>
            {entry.block ? <code>{entry.block.type}</code> : null}
          </li>
        ))}
      </ul>
      {before && after ? (
        <footer className="block-diff__footer">
          revision {before.revision} → {after.revision}
        </footer>
      ) : null}
    </section>
  );
});

export function diffLabel(diff: DocumentDiff): string {
  const counts = diffCounts(diff);
  return `${counts.add} added, ${counts.remove} removed, ${counts.replace} replaced`;
}
