/** Virtualized table primitive with fixed columns and bounded DOM rows. */

import { useMemo, useState } from "react";
import type { UIEvent } from "react";

import { SkeletonTable } from "./Skeletons";
import { computeWindow, sliceWindow } from "./virtual";
import type { ColumnSpec } from "./types";

export interface TableVirtualizerProps<T> {
  rows: readonly T[];
  columns: readonly ColumnSpec<T>[];
  rowKey: (row: T, index: number) => string;
  height?: number;
  rowHeight?: number;
  overscan?: number;
  loading?: boolean;
  className?: string;
}

export function TableVirtualizer<T>({
  rows,
  columns,
  rowKey,
  height = 420,
  rowHeight = 32,
  overscan = 4,
  loading = false,
  className = "",
}: TableVirtualizerProps<T>) {
  const [scrollTop, setScrollTop] = useState(0);
  const window = useMemo(
    () => computeWindow(rows.length, scrollTop, height, rowHeight, overscan),
    [rows.length, scrollTop, height, rowHeight, overscan],
  );
  const visible = useMemo(() => sliceWindow(rows, window), [rows, window]);
  const template = columns.map((column) => `${column.width}px`).join(" ");
  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  };

  if (loading) return <SkeletonTable rows={10} columns={columns.length} />;

  return (
    <div
      className={`perf-virtual perf-virtual--table ${className}`.trim()}
      style={{ height }}
      onScroll={onScroll}
      data-testid="table-virtualizer"
    >
      <div
        className="perf-table__head"
        style={{ gridTemplateColumns: template }}
      >
        {columns.map((column) => (
          <span key={column.key}>{column.title}</span>
        ))}
      </div>
      <div
        className="perf-virtual__viewport"
        style={{ height: height - rowHeight }}
      >
        <div
          className="perf-virtual__spacer"
          style={{ height: window.totalHeight }}
        >
          <div
            className="perf-virtual__slice"
            style={{ transform: `translateY(${window.offsetTop}px)` }}
          >
            {visible.map((row, index) => (
              <div
                className="perf-virtual__row perf-virtual__row--table"
                key={rowKey(row, window.start + index)}
                style={{ height: rowHeight, gridTemplateColumns: template }}
              >
                {columns.map((column) => (
                  <span key={column.key} title={column.render(row)}>
                    {column.render(row)}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
