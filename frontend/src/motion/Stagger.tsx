import type { ReactNode } from "react";

interface StaggerProps {
  children: ReactNode;
  className?: string;
  step?: "tight" | "base" | "loose";
}

export function Stagger({
  children,
  className = "",
  step = "base",
}: StaggerProps) {
  return (
    <div
      className={`motion-stagger stagger-${step} ${className}`.trim()}
      data-stagger={step}
    >
      {children}
    </div>
  );
}
