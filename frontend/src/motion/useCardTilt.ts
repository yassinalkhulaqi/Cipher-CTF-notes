import { useEffect } from "react";
import { useMotion } from "./MotionProvider";

const TILT_SELECTOR = "[data-tilt]";

export function useCardTilt(): void {
  const { enabled, scale } = useMotion();

  useEffect(() => {
    if (!enabled) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      return;
    }

    let active: HTMLElement | null = null;
    let frame = 0;
    let pending: { element: HTMLElement; x: number; y: number } | null = null;

    const reset = (element: HTMLElement) => {
      element.classList.remove("is-tilting");
      element.style.removeProperty("--tilt-x");
      element.style.removeProperty("--tilt-y");
      element.style.removeProperty("--spot-x");
      element.style.removeProperty("--spot-y");
    };

    const flush = () => {
      frame = 0;
      if (!pending) return;
      const { element, x, y } = pending;
      const rect = element.getBoundingClientRect();
      const px = (x - rect.left) / Math.max(rect.width, 1);
      const py = (y - rect.top) / Math.max(rect.height, 1);
      const rotateX = (0.5 - py) * 4.4 * scale;
      const rotateY = (px - 0.5) * 5.4 * scale;
      element.style.setProperty("--tilt-x", `${rotateX.toFixed(2)}deg`);
      element.style.setProperty("--tilt-y", `${rotateY.toFixed(2)}deg`);
      element.style.setProperty("--spot-x", `${((px * 100) | 0).toString()}%`);
      element.style.setProperty("--spot-y", `${((py * 100) | 0).toString()}%`);
    };

    const onMove = (event: PointerEvent) => {
      const target =
        event.target instanceof Element
          ? event.target.closest<HTMLElement>(TILT_SELECTOR)
          : null;
      if (!target) return;
      if (active !== target) {
        if (active) reset(active);
        active = target;
        target.classList.add("is-tilting");
      }
      pending = { element: target, x: event.clientX, y: event.clientY };
      if (!frame) frame = window.requestAnimationFrame(flush);
    };

    const onOut = (event: PointerEvent) => {
      if (!active) return;
      const related = event.relatedTarget;
      if (related instanceof Node && active.contains(related)) return;
      reset(active);
      active = null;
    };

    const onLeaveWindow = () => {
      if (active) reset(active);
      active = null;
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerout", onOut, { passive: true });
    window.addEventListener("blur", onLeaveWindow);

    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerout", onOut);
      window.removeEventListener("blur", onLeaveWindow);
      if (frame) window.cancelAnimationFrame(frame);
      if (active) reset(active);
    };
  }, [enabled, scale]);
}
