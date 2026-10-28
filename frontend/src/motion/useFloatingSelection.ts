import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type CSSProperties,
  type RefObject,
} from "react";
import { motionDuration } from "./preferences";

interface SelectionRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export function useFloatingSelection(
  containerRef: RefObject<HTMLElement>,
  activeId: number | null,
  signature: string,
): { style: CSSProperties; active: boolean } {
  const [rect, setRect] = useState<SelectionRect | null>(null);

  const measure = useCallback(() => {
    const container = containerRef.current;
    if (!container || activeId === null) {
      setRect(null);
      return;
    }
    const row = container.querySelector<HTMLElement>(
      `[data-node-id="${activeId}"]`,
    );
    if (!row) {
      setRect(null);
      return;
    }
    setRect({
      top: row.offsetTop,
      left: row.offsetLeft,
      width: row.offsetWidth,
      height: row.offsetHeight,
    });
  }, [containerRef, activeId]);

  useLayoutEffect(() => {
    measure();
  }, [measure, signature]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !("ResizeObserver" in window)) return;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef, measure]);

  if (!rect) {
    return { style: {}, active: false };
  }

  return {
    active: true,
    style: {
      transform: `translate3d(${rect.left}px, ${rect.top}px, 0)`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      transitionDuration: `${motionDuration(280)}ms`,
    },
  };
}
