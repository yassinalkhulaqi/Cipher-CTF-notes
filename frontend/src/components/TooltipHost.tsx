import { useEffect } from "react";
import { Tooltip } from "./Tooltip";
import { useTooltip } from "../hooks/useTooltip";

export function TooltipHost() {
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    const onMouseOver = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(
        "[data-tooltip]",
      );
      if (!target) {
        hide();
        return;
      }
      const label = target.dataset.tooltip ?? "";
      if (!label) {
        hide();
        return;
      }
      const rect = target.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top;
      show(label, x, y);
    };

    const onMouseOut = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(
        "[data-tooltip]",
      );
      if (target) hide();
    };

    const onScroll = () => hide();

    document.addEventListener("mouseover", onMouseOver);
    document.addEventListener("mouseout", onMouseOut);
    document.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      document.removeEventListener("mouseover", onMouseOver);
      document.removeEventListener("mouseout", onMouseOut);
      document.removeEventListener("scroll", onScroll);
    };
  }, [show, hide]);

  if (!tip) return null;

  return <Tooltip label={tip.label} x={tip.x} y={tip.y} />;
}
