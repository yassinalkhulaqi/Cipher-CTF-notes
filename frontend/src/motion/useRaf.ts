import { useEffect, useRef } from "react";

export function useRaf(
  callback: (deltaSeconds: number, elapsedSeconds: number) => void,
  active = true,
): void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (!active) return;
    let frame = 0;
    let previous = performance.now();
    let elapsed = 0;

    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.064);
      previous = now;
      elapsed += delta;
      callbackRef.current(delta, elapsed);
      frame = window.requestAnimationFrame(tick);
    };

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [active]);
}
