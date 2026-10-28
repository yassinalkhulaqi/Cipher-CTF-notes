import type { CSSProperties, ReactNode } from "react";
import { useInView } from "./useInView";

interface RevealProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  once?: boolean;
}

export function Reveal({
  children,
  className = "",
  delay = 0,
  once = true,
}: RevealProps) {
  const { ref, inView } = useInView<HTMLDivElement>({ once });
  const style = { "--reveal-delay": `${delay}ms` } as CSSProperties;
  return (
    <div
      ref={ref}
      className={`reveal ${inView ? "is-revealed" : ""} ${className}`.trim()}
      style={style}
    >
      {children}
    </div>
  );
}
