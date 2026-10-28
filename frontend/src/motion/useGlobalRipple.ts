import { useEffect } from "react";
import { DURATION } from "./config";
import { useMotion } from "./MotionProvider";
import { motionDuration } from "./preferences";

const RIPPLE_TARGETS = [
  ".btn",
  ".icon-btn",
  ".tool-btn",
  ".menu-item",
  ".palette-item",
  ".pulse-cell",
  ".start-card",
  ".template-tile",
  ".theme-card",
  ".segmented button",
  ".chip",
  ".tree-row",
  ".command-trigger",
  ".link-btn",
].join(",");

export function useGlobalRipple(): void {
  const { enabled } = useMotion();

  useEffect(() => {
    if (!enabled) return;

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const host = target.closest<HTMLElement>(RIPPLE_TARGETS);
      if (!host || host.hasAttribute("disabled")) return;
      if (host.closest(".cm-editor, textarea, input")) return;

      const rect = host.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 1.9;
      const ripple = document.createElement("span");
      ripple.className = "motion-ripple";
      ripple.style.width = `${size}px`;
      ripple.style.height = `${size}px`;
      ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
      ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
      ripple.style.animationDuration = `${motionDuration(DURATION.slower)}ms`;

      if (getComputedStyle(host).position === "static") {
        host.classList.add("motion-ripple-host");
        window.setTimeout(() => {
          if (!host.querySelector(".motion-ripple")) {
            host.classList.remove("motion-ripple-host");
          }
        }, motionDuration(DURATION.slower) + 80);
      }

      host.appendChild(ripple);
      ripple.addEventListener(
        "animationend",
        () => {
          ripple.remove();
          if (!host.querySelector(".motion-ripple")) {
            host.classList.remove("motion-ripple-host");
          }
        },
        { once: true },
      );
    };

    document.addEventListener("pointerdown", onPointerDown, {
      passive: true,
    });
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [enabled]);
}
