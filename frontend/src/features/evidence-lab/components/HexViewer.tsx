/** Virtualized hex viewer with offset navigation and byte selection. */

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { formatBytes, formatOffset, groupCells } from "../format";
import {
  DEFAULT_ROW_HEIGHT,
  navigateOffset,
  scrollToRow,
  visibleRows,
} from "../hexModel";
import type { HexWindowData } from "../types";

export interface HexViewerProps {
  window: HexWindowData | null;
  offsetInput: string;
  bytesPerRow: number;
  loading: boolean;
  onNavigate: (offset: number) => void;
  onOffsetInput: (value: string) => void;
  onBytesPerRow: (value: number) => void;
  onAnchor: (offset: number) => void;
  onHead: (offset: number) => void;
}

export function HexViewer({
  window: hexWindow,
  offsetInput,
  bytesPerRow,
  loading,
  onNavigate,
  onOffsetInput,
  onBytesPerRow,
  onAnchor,
  onHead,
}: HexViewerProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(480);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setViewport(Math.max(120, entry.contentRect.height));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const rows = hexWindow?.rows ?? [];
  const slice = useMemo(
    () => visibleRows(rows, scrollTop, viewport, DEFAULT_ROW_HEIGHT),
    [rows, scrollTop, viewport],
  );

  useEffect(() => {
    dragging.current = false;
  }, [hexWindow]);

  function jump(delta: number) {
    if (!hexWindow) return;
    const target = navigateOffset(
      hexWindow.start + delta,
      0,
      hexWindow.total_bytes,
    );
    onNavigate(target);
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!hexWindow) return;
    const current = navigateOffset(
      Number.parseInt(offsetInput, 16) || hexWindow.start,
      0,
      hexWindow.total_bytes,
    );
    if (event.key === "ArrowDown") {
      event.preventDefault();
      onNavigate(current + bytesPerRow);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      onNavigate(Math.max(0, current - bytesPerRow));
    } else if (event.key === "PageDown") {
      event.preventDefault();
      onNavigate(
        current + bytesPerRow * Math.floor(viewport / DEFAULT_ROW_HEIGHT),
      );
    } else if (event.key === "PageUp") {
      event.preventDefault();
      onNavigate(
        Math.max(
          0,
          current - bytesPerRow * Math.floor(viewport / DEFAULT_ROW_HEIGHT),
        ),
      );
    } else if (event.key === "Home") {
      event.preventDefault();
      onNavigate(0);
    } else if (event.key === "End") {
      event.preventDefault();
      onNavigate(Math.max(0, hexWindow.total_bytes - 1));
    }
  }

  function submitOffset() {
    const parsed = Number.parseInt(offsetInput.replace(/^0x/i, ""), 16);
    if (Number.isFinite(parsed)) onNavigate(Math.max(0, parsed));
  }

  if (!hexWindow) {
    return (
      <div className="elf-hex__empty" data-testid="hex-empty">
        Inspect an evidence item to render its hex dump.
      </div>
    );
  }

  return (
    <div className="elf-hex" data-testid="hex-viewer" data-loading={loading}>
      <div className="elf-hex__toolbar">
        <label className="elf-hex__field">
          <span>Offset</span>
          <input
            aria-label="Hex offset"
            data-testid="hex-offset-input"
            value={offsetInput}
            onChange={(event) => onOffsetInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitOffset();
            }}
          />
        </label>
        <button
          type="button"
          className="elf-button"
          data-testid="hex-goto"
          onClick={submitOffset}
        >
          Go
        </button>
        <button
          type="button"
          className="elf-button"
          onClick={() => jump(-bytesPerRow)}
        >
          Prev
        </button>
        <button
          type="button"
          className="elf-button"
          onClick={() => jump(bytesPerRow)}
        >
          Next
        </button>
        <label className="elf-hex__field">
          <span>Bytes/row</span>
          <select
            aria-label="Bytes per row"
            value={bytesPerRow}
            onChange={(event) => onBytesPerRow(Number(event.target.value))}
          >
            {[8, 16, 24, 32].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <span className="elf-hex__meta" data-testid="hex-meta">
          {formatBytes(hexWindow.total_bytes)} · {hexWindow.rows.length} rows
          loaded
          {hexWindow.truncated ? " · window clipped" : ""}
        </span>
      </div>
      <div
        ref={viewportRef}
        className="elf-hex__viewport"
        data-testid="hex-scroll"
        tabIndex={0}
        role="grid"
        aria-label="Virtualized hex dump"
        onKeyDown={handleKeyDown}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        onMouseUp={() => {
          dragging.current = false;
        }}
        onMouseLeave={() => {
          dragging.current = false;
        }}
      >
        <div
          style={{
            height: rows.length * DEFAULT_ROW_HEIGHT,
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: slice.start * DEFAULT_ROW_HEIGHT,
              left: 0,
              right: 0,
            }}
          >
            {slice.items.map((row, index) => (
              <div
                key={row.offset}
                className="elf-hex__row"
                data-testid="hex-row"
                data-selected={row.selected}
                role="row"
                onMouseDown={() => {
                  dragging.current = true;
                  onAnchor(row.offset);
                }}
                onMouseEnter={() => {
                  if (dragging.current)
                    onHead(row.offset + row.cells.length - 1);
                }}
                onClick={() => scrollToRow(slice.start + index)}
              >
                <span className="elf-hex__offset">
                  {formatOffset(row.offset)}
                </span>
                <span className="elf-hex__cells">{groupCells(row.cells)}</span>
                <span className="elf-hex__ascii">{row.ascii}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
