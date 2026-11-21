export interface ProgressRingProps {
  value: number;
  size?: number;
  stroke?: number;
  label?: string;
}

export function ProgressRing({
  value,
  size = 48,
  stroke = 4,
  label,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <div
      className="motion-progress-ring"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          className="motion-progress-ring__track"
          cx={center}
          cy={center}
          r={radius}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className="motion-progress-ring__value"
          cx={center}
          cy={center}
          r={radius}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
        />
      </svg>
      <span className="motion-progress-ring__label">
        {label ?? `${Math.round(clamped)}%`}
      </span>
    </div>
  );
}
