import { useEffect, useRef, useState, type RefObject } from "react";

interface InViewOptions {
  once?: boolean;
  threshold?: number;
  rootMargin?: string;
}

export function useInView<T extends Element>(
  options: InViewOptions = {},
): { ref: RefObject<T>; inView: boolean } {
  const { once = true, threshold = 0.16, rootMargin = "0px 0px -8% 0px" } =
    options;
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (!("IntersectionObserver" in window)) {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { threshold, rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [once, threshold, rootMargin]);

  return { ref, inView };
}
