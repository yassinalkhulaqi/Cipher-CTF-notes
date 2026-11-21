import { useEffect, useRef } from "react";
import { easing, type EasingName } from "./easing";

export interface TweenOptions {
  durationMs?: number;
  easing?: EasingName;
  onUpdate: (value: number) => void;
}

export function useTween(
  from: number,
  to: number,
  options: TweenOptions,
): void {
  const {
    durationMs = 300,
    easing: easingName = "easeOutCubic",
    onUpdate,
  } = options;
  const callback = useRef(onUpdate);
  callback.current = onUpdate;

  useEffect(() => {
    if (typeof window === "undefined") {
      callback.current(to);
      return;
    }
    const start = performance.now();
    const ease = easing[easingName];
    let frame = 0;
    const tick = (now: number): void => {
      const progress = Math.min(1, (now - start) / Math.max(1, durationMs));
      callback.current(from + (to - from) * ease(progress));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [from, to, durationMs, easingName]);
}
