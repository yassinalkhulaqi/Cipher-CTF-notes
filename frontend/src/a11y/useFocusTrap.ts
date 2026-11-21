import { useEffect, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export interface FocusTrapOptions {
  active?: boolean;
  onEscape?: () => void;
  restoreFocus?: boolean;
}

/** Confines Tab focus to a container and restores focus when it deactivates. */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement>,
  options: FocusTrapOptions = {},
): void {
  const { active = true, onEscape, restoreFocus = true } = options;

  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const getFocusable = (): HTMLElement[] =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) =>
          element.offsetParent !== null || element === document.activeElement,
      );

    const initial = getFocusable()[0];
    if (initial) initial.focus();
    else container.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && onEscape) {
        event.preventDefault();
        onEscape();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable();
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", onKeyDown);
    return () => {
      container.removeEventListener("keydown", onKeyDown);
      if (restoreFocus && previouslyFocused) previouslyFocused.focus();
    };
  }, [active, containerRef, onEscape, restoreFocus]);
}
