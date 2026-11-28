/** Virtualized list primitive for large activity and result streams. */

import { useMemo, useState } from "react";
import type { UIEvent } from "react";

import { SkeletonList } from "./Skeletons";
import { computeWindow, ratioLoaded, sliceWindow } from "./virtual";

export interface ListVirtualizerProps<T> {
  items: readonly T[];
  renderItem: (item: T, index: number) => string;
  itemKey: (item: T, index: number) => string;
  height?: number;
  rowHeight?: number;
  overscan?: number;
  loading?: boolean;
  showRatio?: boolean;
}

export function ListVirtualizer<T>({
  items,
  renderItem,
  itemKey,
  height = 360,
  rowHeight = 28,
  overscan = 5,
  loading = false,
  showRatio = true,
}: ListVirtualizerProps<T>) {
  const [scrollTop, setScrollTop] = useState(0);
  const window = useMemo(
    () => computeWindow(items.length, scrollTop, height, rowHeight, overscan),
    [items.length, scrollTop, height, rowHeight, overscan],
  );
  const visible = useMemo(() => sliceWindow(items, window), [items, window]);
  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  };
  if (loading) return <SkeletonList rows={12} />;
  const ratio = ratioLoaded(window.rendered, items.length);

  return (
    <div
      className="perf-virtual perf-virtual--list"
      data-testid="list-virtualizer"
    >
      {showRatio && (
        <div
          className="perf-virtual__ratio"
          aria-label={`Rendering ${Math.round(ratio * 100)}% of rows`}
        >
          {window.rendered} / {items.length} rows in DOM
        </div>
      )}
      <div
        className="perf-virtual__viewport"
        style={{ height }}
        onScroll={onScroll}
      >
        <div
          className="perf-virtual__spacer"
          style={{ height: window.totalHeight }}
        >
          <div
            className="perf-virtual__slice"
            style={{ transform: `translateY(${window.offsetTop}px)` }}
          >
            {visible.map((item, index) => (
              <div
                className="perf-virtual__row perf-virtual__row--list"
                key={itemKey(item, window.start + index)}
                style={{ height: rowHeight }}
              >
                {renderItem(item, window.start + index)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
