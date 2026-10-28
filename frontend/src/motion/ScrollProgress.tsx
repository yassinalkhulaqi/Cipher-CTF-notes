interface ScrollProgressProps {
  value: number;
  visible?: boolean;
}

export function ScrollProgress({ value, visible = true }: ScrollProgressProps) {
  const progress = Math.min(1, Math.max(0, value));
  return (
    <div
      className={`scroll-progress ${visible ? "visible" : ""}`}
      aria-hidden="true"
    >
      <span style={{ transform: `scaleX(${progress})` }} />
    </div>
  );
}
