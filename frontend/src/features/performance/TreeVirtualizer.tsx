/** Virtualized tree primitive with expand/collapse and skeleton states. */

import { useMemo, useState } from "react";
import type { UIEvent } from "react";

import { SkeletonTree } from "./Skeletons";
import { computeWindow, flattenTree, sliceWindow, toggleExpanded } from "./virtual";
import type { TreeSource } from "./types";

export interface TreeVirtualizerProps {
  roots: readonly TreeSource[];
  height?: number;
  rowHeight?: number;
  overscan?: number;
  loading?: boolean;
  selectedKey?: string;
  onSelect?: (key: string) => void;
  className?: string;
}

export function TreeVirtualizer({
  roots,
  height = 420,
  rowHeight = 30,
  overscan = 4,
  loading = false,
  selectedKey = "",
  onSelect,
  className = "",
}: TreeVirtualizerProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set<string>());
  const rows = useMemo(() => flattenTree(roots, expanded), [roots, expanded]);
  const window = useMemo(
    () => computeWindow(rows.length, scrollTop, height, rowHeight, overscan),
    [rows.length, scrollTop, height, rowHeight, overscan],
  );
  const visible = useMemo(() => sliceWindow(rows, window), [rows, window]);
  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  };

  if (loading) return <SkeletonTree rows={10} />;

  return (
    <div
      className={`perf-virtual perf-virtual--tree ${className}`.trim()}
      style={{ height }}
      onScroll={onScroll}
      data-testid="tree-virtualizer"
    >
      <div className="perf-virtual__spacer" style={{ height: window.totalHeight }}>
        <div className="perf-virtual__slice" style={{ transform: `translateY(${window.offsetTop}px)` }}>
          {visible.map((row) => (
            <button
              type="button"
              className="perf-virtual__row perf-virtual__row--tree"
              key={row.key}
              data-selected={row.key === selectedKey}
              data-kind={row.kind}
              style={{ height: rowHeight, paddingLeft: 8 + row.depth * 14 }}
              onClick={() => {
                if (row.hasChildren) setExpanded((current) => toggleExpanded(current, row.key));
                onSelect?.(row.key);
              }}
            >
              <span className="perf-virtual__twisty" aria-hidden="true">
                {row.hasChildren ? (row.expanded ? "▾" : "▸") : "·"}
              </span>
              <span className="perf-virtual__label">{row.label}</span>
              {row.count > 0 && <span className="perf-virtual__count">{row.count}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
