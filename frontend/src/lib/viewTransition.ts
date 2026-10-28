import { flushSync } from "react-dom";
import { motionDuration, motionEnabled } from "../motion/preferences";

interface ViewTransition {
  ready: Promise<void>;
  finished: Promise<void>;
  updateCallbackDone: Promise<void>;
  skipTransition: () => void;
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => ViewTransition;
};

export function supportsViewTransitions(): boolean {
  if (typeof document === "undefined") return false;
  return (
    typeof (document as ViewTransitionDocument).startViewTransition ===
    "function"
  );
}

export function startThemeTransition(
  origin: { x: number; y: number } | null,
  update: () => void,
): void {
  const doc = document as ViewTransitionDocument;
  if (!motionEnabled() || !supportsViewTransitions()) {
    update();
    return;
  }

  const root = document.documentElement;
  const x = origin?.x ?? window.innerWidth / 2;
  const y = origin?.y ?? window.innerHeight / 2;
  const radius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  );

  root.style.setProperty("--vt-x", `${x}px`);
  root.style.setProperty("--vt-y", `${y}px`);
  root.style.setProperty("--vt-radius", `${radius}px`);

  const transition = doc.startViewTransition?.(() => {
    flushSync(update);
  });
  if (!transition) {
    update();
    return;
  }

  transition.ready
    .then(() => {
      document.documentElement.animate(
        [
          { clipPath: `circle(0px at ${x}px ${y}px)` },
          { clipPath: `circle(${radius}px at ${x}px ${y}px)` },
        ],
        {
          duration: motionDuration(560),
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
          pseudoElement: "::view-transition-new(root)",
        },
      );
    })
    .catch(() => undefined);

  transition.finished
    .catch(() => undefined)
    .finally(() => {
      root.style.removeProperty("--vt-x");
      root.style.removeProperty("--vt-y");
      root.style.removeProperty("--vt-radius");
    });
}
