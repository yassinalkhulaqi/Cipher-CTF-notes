import { useEffect, useRef, useState } from "react";
import { SPRING, type SpringConfig } from "./config";
import { springSettled, springStep } from "./math";
import { useRaf } from "./useRaf";

interface SpringOptions {
  immediate?: boolean;
  epsilon?: number;
}

export function useSpringValue(
  target: number,
  config: SpringConfig = SPRING.gentle,
  options: SpringOptions = {},
): number {
  const immediate = options.immediate ?? false;
  const epsilon = options.epsilon ?? 0.002;
  const [display, setDisplay] = useState(immediate ? target : 0);
  const [active, setActive] = useState(false);
  const simulation = useRef({
    value: immediate ? target : 0,
    velocity: 0,
    target,
  });

  useEffect(() => {
    simulation.current.target = target;
    setActive(true);
  }, [target]);

  useRaf(
    (delta) => {
      const current = simulation.current;
      const next = springStep(
        current.value,
        current.velocity,
        current.target,
        config,
        delta,
      );
      simulation.current = {
        value: next.value,
        velocity: next.velocity,
        target: current.target,
      };
      if (springSettled(next.value, next.velocity, current.target, epsilon)) {
        simulation.current.value = current.target;
        simulation.current.velocity = 0;
        setDisplay(current.target);
        setActive(false);
        return;
      }
      setDisplay(next.value);
    },
    active,
  );

  return display;
}
