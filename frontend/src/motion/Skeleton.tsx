interface SkeletonProps {
  lines?: number;
  className?: string;
  compact?: boolean;
}

export function Skeleton({ lines = 3, className = "", compact }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${compact ? "compact" : ""} ${className}`.trim()}
      aria-hidden="true"
    >
      {Array.from({ length: lines }, (_, index) => (
        <span
          key={index}
          className="skeleton-line"
          style={{ width: `${Math.max(32, 100 - index * 13)}%` }}
        />
      ))}
    </div>
  );
}
