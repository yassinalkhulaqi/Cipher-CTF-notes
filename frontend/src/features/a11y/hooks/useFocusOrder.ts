import { useCallback, useEffect, useMemo, useState } from "react";
import type { RefObject } from "react";
import { focusStepLabel, sortFocusSteps } from "../pure";
import type { FocusStep } from "../types";

export const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function scanFocusOrder(root: ParentNode): FocusStep[] {
  const nodes = Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  );
  return sortFocusSteps(
    nodes.map((element, index) => {
      const rawTabIndex = element.getAttribute("tabindex");
      const parsed =
        rawTabIndex === null ? 0 : Number.parseInt(rawTabIndex, 10);
      const tabIndex = Number.isFinite(parsed) ? parsed : 0;
      const description =
        element.getAttribute("aria-label") ??
        element.getAttribute("title") ??
        (element.textContent ?? "").trim();
      const hidden =
        element.getAttribute("aria-hidden") === "true" ||
        element.hasAttribute("hidden") ||
        element.closest("[hidden]") !== null;
      return {
        order: index + 1,
        target: element.id || `${element.tagName.toLowerCase()}-${index + 1}`,
        tag: element.tagName.toLowerCase(),
        tab_index: tabIndex,
        description: description.slice(0, 80),
        hidden,
      };
    }),
  );
}

export function useFocusOrder(
  rootRef: RefObject<HTMLElement | null>,
  deps: readonly unknown[] = [],
) {
  const [steps, setSteps] = useState<FocusStep[]>([]);

  const refresh = useCallback(() => {
    const root = rootRef.current;
    setSteps(root ? scanFocusOrder(root) : []);
  }, [rootRef]);

  useEffect(() => {
    refresh();
  }, [refresh, ...deps]);

  const labels = useMemo(() => steps.map(focusStepLabel), [steps]);
  const positiveSteps = useMemo(
    () => steps.filter((step) => step.tab_index > 0),
    [steps],
  );

  return { steps, labels, positiveSteps, refresh };
}
