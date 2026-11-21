import type { CSSProperties, ReactNode } from "react";

export interface ResponsiveGridProps {
  children: ReactNode;
  minColumnWidth?: number;
  gap?: number;
  className?: string;
}

/** Fluid grid that fits as many columns as the container allows. */
export function ResponsiveGrid({
  children,
  minColumnWidth = 240,
  gap = 16,
  className = "",
}: ResponsiveGridProps) {
  const style: CSSProperties = {
    display: "grid",
    gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${minColumnWidth}px), 1fr))`,
    gap: `${gap}px`,
    alignItems: "start",
  };

  return (
    <div className={`layout-grid ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
