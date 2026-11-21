import type { CSSProperties } from "react";
import { clamp, cx, styleVars } from "./componentUtils";

export type ProgressTone = "accent" | "success" | "warning" | "danger";

export interface ProgressProps {
  value: number;
  max?: number;
  label?: string;
  tone?: ProgressTone;
  showValue?: boolean;
  indeterminate?: boolean;
  className?: string;
}

export function Progress({
  value,
  max = 100,
  label,
  tone = "accent",
  showValue = false,
  indeterminate = false,
  className,
}: ProgressProps) {
  const bounded = clamp(value, 0, max);
  const fill = max > 0 ? (bounded / max) * 100 : 0;
  const style = styleVars({ "--progress-fill": `${fill}%` }) as CSSProperties;

  return (
    <div className={cx("ui-progress", className)}>
      {label || showValue ? (
        <div className="ui-progress__header">
          {label ? <span className="ui-progress__label">{label}</span> : null}
          {showValue ? (
            <span className="ui-progress__value">{Math.round(bounded)}</span>
          ) : null}
        </div>
      ) : null}
      <div
        className={cx(
          "ui-progress__track",
          indeterminate && "is-indeterminate",
        )}
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : bounded}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
        style={style}
      >
        <div className={cx("ui-progress__fill", `is-${tone}`)} />
      </div>
    </div>
  );
}

export interface StepProgressProps {
  steps: string[];
  current: number;
}

export function StepProgress({ steps, current }: StepProgressProps) {
  return (
    <ol className="ui-step-progress" aria-label="Progress">
      {steps.map((step, index) => (
        <li
          key={step}
          className={cx(
            "ui-step-progress__step",
            index < current && "is-complete",
            index === current && "is-current",
          )}
          aria-current={index === current ? "step" : undefined}
        >
          <span className="ui-step-progress__marker">{index + 1}</span>
          <span className="ui-step-progress__label">{step}</span>
        </li>
      ))}
    </ol>
  );
}
