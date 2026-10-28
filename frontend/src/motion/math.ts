import type { SpringConfig } from "./config";

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount;
}

export function inverseLerp(from: number, to: number, value: number): number {
  if (from === to) return 0;
  return clamp((value - from) / (to - from), 0, 1);
}

export function mapRange(
  value: number,
  fromLow: number,
  fromHigh: number,
  toLow: number,
  toHigh: number,
): number {
  return lerp(toLow, toHigh, inverseLerp(fromLow, fromHigh, value));
}

export function damp(
  current: number,
  target: number,
  lambda: number,
  deltaSeconds: number,
): number {
  return lerp(current, target, 1 - Math.exp(-lambda * deltaSeconds));
}

export function springStep(
  value: number,
  velocity: number,
  target: number,
  config: SpringConfig,
  deltaSeconds: number,
): { value: number; velocity: number } {
  const { stiffness, damping, mass } = config;
  const delta = clamp(deltaSeconds, 0, 0.064);
  const force = -stiffness * (value - target);
  const drag = -damping * velocity;
  const acceleration = (force + drag) / Math.max(mass, 0.05);
  const nextVelocity = velocity + acceleration * delta;
  const nextValue = value + nextVelocity * delta;
  return { value: nextValue, velocity: nextVelocity };
}

export function springSettled(
  value: number,
  velocity: number,
  target: number,
  epsilon = 0.002,
  velocityEpsilon = 0.02,
): boolean {
  return (
    Math.abs(value - target) < epsilon &&
    Math.abs(velocity) < velocityEpsilon
  );
}

export function springDuration(config: SpringConfig, epsilon = 0.002): number {
  let value = 0;
  let velocity = 0;
  let elapsed = 0;
  const step = 1 / 120;
  for (let index = 0; index < 240; index += 1) {
    const next = springStep(value, velocity, 1, config, step);
    value = next.value;
    velocity = next.velocity;
    elapsed += step;
    if (springSettled(value, velocity, 1, epsilon)) break;
  }
  return Math.round(elapsed * 1000);
}

export function staggerDelay(
  index: number,
  step: number,
  max = 16,
  origin = 0,
): number {
  const offset = Math.max(0, index - origin);
  return Math.min(offset, max) * step;
}

export function round(value: number, precision = 3): number {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
}

export function distanceBetween(
  first: { x: number; y: number },
  second: { x: number; y: number },
): number {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

export function velocitySample(
  previous: { x: number; y: number; time: number },
  next: { x: number; y: number; time: number },
): { x: number; y: number } {
  const delta = Math.max(1, next.time - previous.time) / 1000;
  return {
    x: clamp((next.x - previous.x) / delta, -2000, 2000),
    y: clamp((next.y - previous.y) / delta, -2000, 2000),
  };
}
