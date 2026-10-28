import { useLayoutEffect, useRef, type RefObject } from "react";
import { DURATION, EASE } from "./config";
import { currentMotionLevel, motionScale } from "./preferences";

interface FlipOptions {
  selector?: string;
  duration?: number;
}

interface ItemGeometry {
  top: number;
  height: number;
}

export function useFlipList(
  containerRef: RefObject<HTMLElement>,
  signature: string,
  options: FlipOptions = {},
): void {
  const { selector = "[data-node-id]", duration = DURATION.slow } = options;
  const previous = useRef<Map<string, ItemGeometry>>(new Map());

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const level = currentMotionLevel();
    const elements = Array.from(
      container.querySelectorAll<HTMLElement>(selector),
    );
    const next = new Map<string, ItemGeometry>();

    for (const element of elements) {
      const key = element.dataset.nodeId;
      if (!key) continue;
      next.set(key, { top: element.offsetTop, height: element.offsetHeight });
      if (level === "off") continue;
      const prior = previous.current.get(key);
      if (!prior) continue;
      const delta = prior.top - element.offsetTop;
      if (Math.abs(delta) < 0.5) continue;
      for (const animation of element.getAnimations()) {
        if (animation.id === "redscribe-flip") animation.cancel();
      }
      const animation = element.animate(
        [
          { transform: `translateY(${delta}px)` },
          { transform: "translateY(0)" },
        ],
        {
          duration: Math.max(80, duration * motionScale()),
          easing: EASE.out,
          composite: "replace",
        },
      );
      animation.id = "redscribe-flip";
    }

    previous.current = next;
  }, [containerRef, signature, selector, duration]);
}
