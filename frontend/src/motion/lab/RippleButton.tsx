import { useCallback, useState, type MouseEvent, type ReactNode } from "react";

interface Ripple {
  id: number;
  x: number;
  y: number;
}

export interface RippleButtonProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
}

export function RippleButton({
  children,
  onClick,
  className = "",
  disabled = false,
}: RippleButtonProps) {
  const [ripples, setRipples] = useState<Ripple[]>([]);

  const handleClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>): void => {
      const rect = event.currentTarget.getBoundingClientRect();
      const ripple = {
        id: Date.now() + Math.random(),
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };
      setRipples((current) => [...current, ripple]);
      setTimeout(() => {
        setRipples((current) =>
          current.filter((item) => item.id !== ripple.id),
        );
      }, 600);
      onClick?.();
    },
    [onClick],
  );

  return (
    <button
      type="button"
      className={`motion-ripple-btn ${className}`.trim()}
      onClick={handleClick}
      disabled={disabled}
    >
      {children}
      {ripples.map((ripple) => (
        <span
          key={ripple.id}
          className="motion-ripple"
          style={{ left: ripple.x, top: ripple.y }}
        />
      ))}
    </button>
  );
}
