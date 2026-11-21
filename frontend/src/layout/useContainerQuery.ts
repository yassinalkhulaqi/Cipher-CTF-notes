import { useEffect, useState, type RefObject } from "react";

export function useContainerWidth<T extends HTMLElement>(
  ref: RefObject<T>,
  fallback = 0,
): number {
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof ResizeObserver === "undefined") {
      setWidth(node.clientWidth);
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}

export function useContainerClass<T extends HTMLElement>(
  ref: RefObject<T>,
  threshold: number,
): boolean {
  const width = useContainerWidth(ref);
  return width > 0 && width < threshold;
}
