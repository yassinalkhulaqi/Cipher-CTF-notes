import type { CSSProperties } from "react";
import { cx } from "../lib/ux";

export type SkeletonVariant = "text" | "block" | "circle";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  variant?: SkeletonVariant;
  lines?: number;
  className?: string;
  style?: CSSProperties;
}

function dimension(value: string | number | undefined): string | undefined {
  if (value === undefined) return undefined;
  return typeof value === "number" ? `${value}px` : value;
}

export function Skeleton({
  width,
  height,
  variant = "block",
  lines = 1,
  className,
  style,
}: SkeletonProps) {
  const resolvedStyle: CSSProperties = {
    width: dimension(width),
    height: dimension(height),
    ...style,
  };

  if (lines > 1) {
    return (
      <span className={cx("ui-skeleton-group", className)} aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <span
            key={index}
            className={cx("ui-skeleton", "ui-skeleton--text")}
            style={resolvedStyle}
          />
        ))}
      </span>
    );
  }

  return (
    <span
      className={cx("ui-skeleton", `ui-skeleton--${variant}`, className)}
      style={resolvedStyle}
      aria-hidden="true"
    />
  );
}
