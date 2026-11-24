import type { CSSProperties } from "react";
import { cx, styleVars } from "./componentUtils";

export interface SkeletonCardProps {
  lines?: number;
  showAvatar?: boolean;
  showImage?: boolean;
  width?: number | string;
  className?: string;
}

export function SkeletonCard({
  lines = 3,
  showAvatar = false,
  showImage = false,
  width,
  className,
}: SkeletonCardProps) {
  const style = width
    ? (styleVars({
        width: typeof width === "number" ? `${width}px` : width,
      }) as CSSProperties)
    : undefined;

  return (
    <div
      className={cx("ui-skeleton-card", className)}
      style={style}
      aria-hidden="true"
    >
      {showImage ? <div className="ui-skeleton ui-skeleton--image" /> : null}
      <div className="ui-skeleton-card__body">
        {showAvatar ? (
          <div className="ui-skeleton ui-skeleton--avatar" />
        ) : null}
        <div className="ui-skeleton-card__lines">
          {Array.from({ length: Math.max(1, lines) }, (_, index) => (
            <div
              key={index}
              className={cx(
                "ui-skeleton",
                "ui-skeleton--line",
                index === 0 && "is-wide",
                index === lines - 1 && "is-short",
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="ui-skeleton-list" aria-hidden="true">
      {Array.from({ length: Math.max(1, rows) }, (_, index) => (
        <SkeletonCard key={index} lines={2} showAvatar />
      ))}
    </div>
  );
}
