import { useId, type ChangeEvent, type CSSProperties } from "react";
import { cx, percentage, styleVars } from "./componentUtils";

export interface SliderProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  disabled?: boolean;
  showValue?: boolean;
  onChange: (value: number) => void;
  className?: string;
}

export function Slider({
  value,
  min = 0,
  max = 100,
  step = 1,
  label,
  disabled = false,
  showValue = false,
  onChange,
  className,
}: SliderProps) {
  const id = useId();
  const fill = percentage(value, min, max);
  const trackStyle = styleVars({
    "--slider-fill": `${fill}%`,
  }) as CSSProperties;

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    onChange(Number(event.target.value));
  };

  return (
    <div className={cx("ui-slider", className)}>
      {label ? (
        <div className="ui-slider__header">
          <label className="ui-slider__label" htmlFor={id}>
            {label}
          </label>
          {showValue ? (
            <output className="ui-slider__value" htmlFor={id}>
              {value}
            </output>
          ) : null}
        </div>
      ) : null}
      <input
        id={id}
        className="ui-slider__input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={handleChange}
        style={trackStyle}
      />
      <div className="ui-slider__scale" aria-hidden="true">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

export interface RangeSliderProps {
  lower: number;
  upper: number;
  min?: number;
  max?: number;
  onChange: (lower: number, upper: number) => void;
}

export function RangeSlider({
  lower,
  upper,
  min = 0,
  max = 100,
  onChange,
}: RangeSliderProps) {
  return (
    <div className="ui-slider ui-slider--range">
      <Slider
        label="Lower bound"
        value={lower}
        min={min}
        max={upper}
        onChange={(next) => onChange(next, upper)}
      />
      <Slider
        label="Upper bound"
        value={upper}
        min={lower}
        max={max}
        onChange={(next) => onChange(lower, next)}
      />
    </div>
  );
}
