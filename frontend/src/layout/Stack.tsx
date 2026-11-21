import type { CSSProperties, ReactNode } from "react";

export interface StackProps {
  children: ReactNode;
  gap?: number;
  direction?: "vertical" | "horizontal";
  align?: "start" | "center" | "end" | "stretch";
  wrap?: boolean;
  className?: string;
}

export function Stack({
  children,
  gap = 12,
  direction = "vertical",
  align = "stretch",
  wrap = false,
  className = "",
}: StackProps) {
  const style: CSSProperties = {
    display: "flex",
    flexDirection: direction === "vertical" ? "column" : "row",
    gap: `${gap}px`,
    alignItems: align,
    flexWrap: wrap ? "wrap" : "nowrap",
  };

  return (
    <div className={`layout-stack ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
