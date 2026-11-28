/** Accessible skeleton states used while virtualized data is loading. */

import type { CSSProperties } from "react";

export interface SkeletonProps {
  rows?: number;
  width?: string;
  label?: string;
}

function shimmerStyle(width: string): CSSProperties {
  return { width };
}

export function SkeletonRow({
  width = "72%",
  label = "Loading row",
}: SkeletonProps) {
  return (
    <div className="perf-skeleton__row" role="presentation" aria-label={label}>
      <span className="perf-skeleton__bar perf-skeleton__bar--dot" />
      <span className="perf-skeleton__bar" style={shimmerStyle(width)} />
    </div>
  );
}

export function SkeletonList({
  rows = 8,
  label = "Loading items",
}: SkeletonProps) {
  return (
    <div className="perf-skeleton" aria-busy="true" aria-label={label}>
      {Array.from({ length: Math.max(0, rows) }, (_, index) => (
        <SkeletonRow
          key={index}
          width={`${52 + ((index * 13) % 40)}%`}
          label={`${label} ${index + 1}`}
        />
      ))}
    </div>
  );
}

export function SkeletonTree({ rows = 7 }: SkeletonProps) {
  return (
    <div
      className="perf-skeleton perf-skeleton--tree"
      aria-busy="true"
      aria-label="Loading tree"
    >
      {Array.from({ length: Math.max(0, rows) }, (_, index) => (
        <SkeletonRow
          key={index}
          width={`${38 + (index % 4) * 12}%`}
          label={`Loading tree node ${index + 1}`}
        />
      ))}
    </div>
  );
}

export function SkeletonTable({
  rows = 8,
  columns = 4,
}: SkeletonProps & { columns?: number }) {
  return (
    <div
      className="perf-skeleton perf-skeleton--table"
      aria-busy="true"
      aria-label="Loading table"
    >
      {Array.from({ length: Math.max(0, rows) }, (_, row) => (
        <div className="perf-skeleton__grid" key={row}>
          {Array.from({ length: Math.max(1, columns) }, (_, column) => (
            <span
              className="perf-skeleton__bar"
              key={column}
              style={shimmerStyle(`${62 + ((column * 7) % 30)}%`)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
