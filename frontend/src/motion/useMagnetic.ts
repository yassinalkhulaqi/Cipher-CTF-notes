import { useEffect, useRef, type RefObject } from "react";
import { clamp, damp } from "./math";
import { useMotion } from "./MotionProvider";

export function useMagnetic<T extends HTMLElement>(
  strength = 0.22,
  maxDistance = 9,
): RefObject<T> {
  const ref = useRef<T>(null);
  const { enabled, scale } = useMotion();

  useEffect(() => {
    const element = ref.current;
    if (!element || !enabled) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      return;
    }

    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let frame = 0;

    const tick = () => {
      currentX = damp(currentX, targetX, 16, 1 / 60);
      currentY = damp(currentY, targetY, 16, 1 / 60);
      const settled =
        Math.abs(currentX - targetX) < 0.05 &&
        Math.abs(currentY - targetY) < 0.05;
      if (settled) {
        currentX = targetX;
        currentY = targetY;
      }
      element.style.transform =
        currentX === 0 && currentY === 0
          ? ""
          : `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`;
      if (settled) {
        frame = 0;
        return;
      }
      frame = window.requestAnimationFrame(tick);
    };

    const start = () => {
      if (!frame) frame = window.requestAnimationFrame(tick);
    };

    const onMove = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect();
      const localStrength = strength * scale;
      targetX = clamp(
        (event.clientX - rect.left - rect.width / 2) * localStrength,
        -maxDistance * scale,
        maxDistance * scale,
      );
      targetY = clamp(
        (event.clientY - rect.top - rect.height / 2) * localStrength,
        -maxDistance * scale,
        maxDistance * scale,
      );
      start();
    };

    const onLeave = () => {
      targetX = 0;
      targetY = 0;
      start();
    };

    element.addEventListener("pointermove", onMove);
    element.addEventListener("pointerleave", onLeave);
    element.addEventListener("blur", onLeave);

    return () => {
      element.removeEventListener("pointermove", onMove);
      element.removeEventListener("pointerleave", onLeave);
      element.removeEventListener("blur", onLeave);
      if (frame) window.cancelAnimationFrame(frame);
      element.style.transform = "";
    };
  }, [enabled, scale, strength, maxDistance]);

  return ref;
}
