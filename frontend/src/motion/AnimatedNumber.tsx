import { SPRING } from "./config";
import { useMotion } from "./MotionProvider";
import { useSpringValue } from "./useSpring";

interface AnimatedNumberProps {
  value: number;
  className?: string;
  format?: (value: number) => string;
}

export function AnimatedNumber({
  value,
  className,
  format,
}: AnimatedNumberProps) {
  const { enabled } = useMotion();
  const animated = useSpringValue(value, SPRING.counter);
  const rounded = enabled ? Math.round(animated) : value;
  const text = format ? format(rounded) : rounded.toLocaleString();
  return (
    <span className={className} aria-label={text}>
      <span aria-hidden="true">{text}</span>
    </span>
  );
}
