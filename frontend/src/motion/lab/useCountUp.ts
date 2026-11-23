import { useEffect, useState } from "react";
import { easing, type EasingName } from "./easing";

export interface CountUpOptions {
  durationMs?: number;
  easingName?: EasingName;
  decimals?: number;
}

export function useCountUp(
  target: number,
  options: CountUpOptions = {},
): number {
  const {
    durationMs = 600,
    easingName = "easeOutCubic",
    decimals = 0,
  } = options;
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") {
      setValue(target);
      return;
    }
    const start = performance.now();
    const ease = easing[easingName];
    const factor = Math.pow(10, decimals);
    let frame = 0;
    const tick = (now: number): void => {
      const progress = Math.min(1, (now - start) / Math.max(1, durationMs));
      const next = target * ease(progress);
      setValue(Math.round(next * factor) / factor);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, easingName, decimals]);

  return value;
}
