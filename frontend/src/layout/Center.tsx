import type { CSSProperties, ReactNode } from "react";

export interface CenterProps {
  children: ReactNode;
  maxWidth?: number | string;
  textAlign?: "left" | "center";
  className?: string;
}

export function Center({
  children,
  maxWidth = 720,
  textAlign = "left",
  className = "",
}: CenterProps) {
  const width = typeof maxWidth === "number" ? `${maxWidth}px` : maxWidth;
  const style: CSSProperties = {
    width: "100%",
    maxWidth: width,
    marginInline: "auto",
    textAlign,
  };

  return (
    <div className={`layout-center ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
