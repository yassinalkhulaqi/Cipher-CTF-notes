import { useEffect } from "react";
import { Tooltip } from "./Tooltip";
import { useTooltip } from "../hooks/useTooltip";

export function TooltipHost() {
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    const showFor = (target: HTMLElement) => {
      const label = target.dataset.tooltip ?? "";
      if (!label) {
        hide();
        return;
      }
      const rect = target.getBoundingClientRect();
      show(label, rect.left + rect.width / 2, rect.top);
    };

    const onMouseOver = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(
        "[data-tooltip]",
      );
      if (!target) {
        hide();
        return;
      }
      showFor(target);
    };

    const onMouseOut = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(
        "[data-tooltip]",
      );
      if (target) hide();
    };

    const onFocusIn = (event: FocusEvent) => {
      const target = (event.target as HTMLElement).closest?.<HTMLElement>(
        "[data-tooltip]",
      );
      if (target) showFor(target);
    };

    const onFocusOut = (event: FocusEvent) => {
      const target = (event.target as HTMLElement).closest?.<HTMLElement>(
        "[data-tooltip]",
      );
      if (target) hide();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") hide();
    };

    const onScroll = () => hide();

    document.addEventListener("mouseover", onMouseOver);
    document.addEventListener("mouseout", onMouseOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      document.removeEventListener("mouseover", onMouseOver);
      document.removeEventListener("mouseout", onMouseOut);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("scroll", onScroll);
    };
  }, [show, hide]);

  if (!tip) return null;

  return <Tooltip label={tip.label} x={tip.x} y={tip.y} />;
}
