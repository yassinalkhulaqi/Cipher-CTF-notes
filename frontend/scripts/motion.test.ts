import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { DURATION, EASE, SPRING, STAGGER } from "../src/motion/config";
import {
  clamp,
  damp,
  inverseLerp,
  lerp,
  mapRange,
  springDuration,
  springSettled,
  springStep,
  staggerDelay,
  velocitySample,
} from "../src/motion/math";
import {
  MOTION_MODE_LABEL,
  MOTION_STORAGE_KEY,
  normalizeMotionMode,
  resolveMotionLevel,
} from "../src/motion/preferences";

const root = process.cwd();

test("clamp and interpolation stay inside their range", () => {
  assert.equal(clamp(12, 0, 10), 10);
  assert.equal(clamp(-4, 0, 10), 0);
  assert.equal(lerp(0, 10, 0.25), 2.5);
  assert.equal(inverseLerp(0, 10, 5), 0.5);
  assert.equal(inverseLerp(4, 4, 4), 0);
  assert.equal(mapRange(5, 0, 10, 100, 200), 150);
});

test("damp converges without overshooting", () => {
  let value = 0;
  for (let index = 0; index < 240; index += 1) {
    const next = damp(value, 100, 12, 1 / 60);
    assert.ok(next <= 100);
    assert.ok(next >= value);
    value = next;
  }
  assert.ok(value > 99.9);
});

test("spring steps settle at the target", () => {
  let value = 0;
  let velocity = 0;
  for (let index = 0; index < 600; index += 1) {
    const next = springStep(value, velocity, 1, SPRING.snappy, 1 / 120);
    value = next.value;
    velocity = next.velocity;
    if (springSettled(value, velocity, 1)) break;
  }
  assert.ok(springSettled(value, velocity, 1));
  assert.ok(Math.abs(value - 1) < 0.01);
});

test("spring durations are bounded and ordered", () => {
  const snappy = springDuration(SPRING.snappy);
  const heavy = springDuration(SPRING.heavy);
  assert.ok(snappy > 80);
  assert.ok(snappy < 1000);
  assert.ok(heavy > snappy);
});

test("stagger delays are capped", () => {
  assert.equal(staggerDelay(0, 30), 0);
  assert.equal(staggerDelay(3, 30), 90);
  assert.equal(staggerDelay(100, 30, 8), 240);
  assert.equal(staggerDelay(2, 30, 8, 4), 0);
});

test("velocity sampling is finite and clamped", () => {
  const sample = velocitySample(
    { x: 0, y: 0, time: 0 },
    { x: 5000, y: -5000, time: 1000 },
  );
  assert.equal(sample.x, 2000);
  assert.equal(sample.y, -2000);
});

test("motion preferences normalize unknown values", () => {
  assert.equal(normalizeMotionMode("full"), "full");
  assert.equal(normalizeMotionMode("subtle"), "subtle");
  assert.equal(normalizeMotionMode("off"), "off");
  assert.equal(normalizeMotionMode("turbo"), "system");
  assert.equal(normalizeMotionMode(null), "system");
  assert.equal(MOTION_STORAGE_KEY, "redscribe.motion.mode");
  assert.equal(MOTION_MODE_LABEL.off, "Off");
});

test("system mode honors reduced motion while full overrides it", () => {
  assert.equal(resolveMotionLevel("system", true), "off");
  assert.equal(resolveMotionLevel("system", false), "full");
  assert.equal(resolveMotionLevel("full", true), "full");
  assert.equal(resolveMotionLevel("subtle", true), "subtle");
  assert.equal(resolveMotionLevel("off", false), "off");
});

test("durations and easing expose the motion vocabulary", () => {
  assert.ok(DURATION.instant < DURATION.fast);
  assert.ok(DURATION.fast < DURATION.base);
  assert.ok(DURATION.base < DURATION.slow);
  assert.ok(DURATION.slow < DURATION.slower);
  assert.ok(DURATION.slower < DURATION.cinematic);
  assert.match(EASE.out, /^cubic-bezier\(/);
  assert.ok(STAGGER.tight < STAGGER.base);
  assert.ok(STAGGER.base < STAGGER.loose);
});

test("motion styles ship tokens, keyframes, and kill switches", () => {
  const tokens = readFileSync(
    path.join(root, "src/styles/motion-tokens.css"),
    "utf8",
  );
  const keyframes = readFileSync(
    path.join(root, "src/styles/motion-keyframes.css"),
    "utf8",
  );
  const accessibility = readFileSync(
    path.join(root, "src/styles/motion-accessibility.css"),
    "utf8",
  );
  const index = readFileSync(path.join(root, "src/styles/index.css"), "utf8");

  assert.match(tokens, /--motion-duration-base/);
  assert.match(tokens, /html\[data-motion="off"\]/);
  assert.match(keyframes, /@keyframes mx-page-in/);
  assert.match(keyframes, /@keyframes mx-modal-in/);
  assert.match(keyframes, /@keyframes mx-toast-in/);
  assert.match(accessibility, /prefers-reduced-motion: reduce/);
  assert.match(accessibility, /html\[data-motion-mode="system"\]/);
  assert.match(index, /motion-tokens\.css/);
  assert.match(index, /motion-accessibility\.css/);
});
