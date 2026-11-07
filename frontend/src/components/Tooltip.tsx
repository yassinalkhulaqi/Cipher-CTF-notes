interface TooltipProps {
  label: string;
  x: number;
  y: number;
}

export function Tooltip({ label, x, y }: TooltipProps) {
  return (
    <div
      className="tooltip"
      role="tooltip"
      style={{
        left: x,
        top: y - 10,
        pointerEvents: "none",
      }}
    >
      <div className="tooltip-arrow" />
      <span className="tooltip-body">{label}</span>
    </div>
  );
}
