import {
  useCallback,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

export interface SplitPaneProps {
  leading: ReactNode;
  trailing: ReactNode;
  initialRatio?: number;
  minRatio?: number;
  maxRatio?: number;
  vertical?: boolean;
}

export function SplitPane({
  leading,
  trailing,
  initialRatio = 0.35,
  minRatio = 0.15,
  maxRatio = 0.85,
  vertical = false,
}: SplitPaneProps) {
  const container = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const [ratio, setRatio] = useState(initialRatio);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>): void => {
      if (!dragging.current) return;
      const rect = container.current?.getBoundingClientRect();
      if (!rect) return;
      const position = vertical
        ? (event.clientY - rect.top) / rect.height
        : (event.clientX - rect.left) / rect.width;
      setRatio(Math.max(minRatio, Math.min(maxRatio, position)));
    },
    [maxRatio, minRatio, vertical],
  );

  const stop = useCallback((): void => {
    dragging.current = false;
  }, []);

  const start = useCallback((): void => {
    dragging.current = true;
  }, []);

  const size = `${Math.round(ratio * 100)}%`;

  return (
    <div
      ref={container}
      className={`layout-split ${vertical ? "is-vertical" : "is-horizontal"}`}
      onPointerMove={onPointerMove}
      onPointerUp={stop}
      onPointerLeave={stop}
    >
      <div className="layout-split__pane" style={{ flexBasis: size }}>
        {leading}
      </div>
      <div
        className="layout-split__handle"
        role="separator"
        aria-orientation={vertical ? "horizontal" : "vertical"}
        aria-valuenow={Math.round(ratio * 100)}
        aria-valuemin={Math.round(minRatio * 100)}
        aria-valuemax={Math.round(maxRatio * 100)}
        tabIndex={0}
        onPointerDown={start}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 0.1 : 0.02;
          if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
            setRatio((current) => Math.max(minRatio, current - step));
          } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            setRatio((current) => Math.min(maxRatio, current + step));
          }
        }}
      />
      <div className="layout-split__pane">{trailing}</div>
    </div>
  );
}
