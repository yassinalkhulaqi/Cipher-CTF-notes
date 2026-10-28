import { useEffect, useRef } from "react";
import { damp } from "./math";
import { useMotion } from "./MotionProvider";

export function CursorGlow() {
  const { enabled } = useMotion();
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      return;
    }

    const element = glowRef.current;
    if (!element) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currentX = targetX;
    let currentY = targetY;
    let frame = 0;
    let visible = false;

    const tick = () => {
      currentX = damp(currentX, targetX, 10, 1 / 60);
      currentY = damp(currentY, targetY, 10, 1 / 60);
      element.style.transform = `translate3d(${currentX - 320}px, ${currentY - 320}px, 0)`;
      const settled =
        Math.abs(currentX - targetX) < 0.4 &&
        Math.abs(currentY - targetY) < 0.4;
      if (settled) {
        frame = 0;
        return;
      }
      frame = window.requestAnimationFrame(tick);
    };

    const onMove = (event: PointerEvent) => {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!visible) {
        visible = true;
        currentX = targetX;
        currentY = targetY;
        element.dataset.visible = "true";
      }
      if (!frame) frame = window.requestAnimationFrame(tick);
    };

    const onLeave = () => {
      visible = false;
      element.dataset.visible = "false";
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    window.addEventListener("blur", onLeave);

    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [enabled]);

  if (!enabled) return null;
  return <div ref={glowRef} className="cursor-glow" aria-hidden="true" />;
}
