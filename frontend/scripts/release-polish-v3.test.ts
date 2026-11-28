import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { ReleasePolishClient } from "../src/features/release-polish/client";
import {
  ANIMATION_AUDITS,
  BREAKPOINTS,
  EMPTY_STATES,
  GOLDEN_PHASES,
  ICON_LABELS,
  KIND_LABELS,
  MOTION_TOKENS,
  ONBOARDING_STEPS,
  POLISH_CHECKS,
  RELEASE_ROUTES,
  RELEASE_SURFACES,
  SHOWCASE_ENTRIES,
} from "../src/features/release-polish/config";
import {
  animationSummarySafe,
  animationsWithInvalidTokens,
  auditAnimations,
  auditsSafeCount,
  emptyStateFor,
  filterPolishByArea,
  firstRunState,
  firstRunSurface,
  formatPercent,
  iconForKind,
  isOnboardingComplete,
  kindColorToken,
  labelConsistencyIssues,
  labelForKind,
  nextOnboardingStep,
  onboardingProgress,
  polishProgress,
  releaseSnapshot,
  resolveBreakpoint,
  responsiveRisk,
  showcaseByKind,
  showcaseTokens,
  usesMotionToken,
  withCheckState,
} from "../src/features/release-polish/pure";
import {
  activeStep,
  completionLabel,
  initialReleasePolishState,
  polishLabel,
  releasePolishReducer,
} from "../src/features/release-polish/state";

const root = process.cwd();

function source(relative: string): string {
  return readFileSync(path.join(root, relative), "utf8");
}

function json(data: unknown): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: { request_id: "req_test", api_version: "3.0" },
    }),
    {
      status: 200,
      headers: { "Content-Type": "application/json" },
    },
  );
}

test("config catalogues mirror the Python release content", () => {
  assert.equal(GOLDEN_PHASES.length, 7);
  assert.equal(GOLDEN_PHASES[0], "capture");
  assert.equal(GOLDEN_PHASES[6], "merge");
  assert.equal(ONBOARDING_STEPS.length, 5);
  assert.equal(ONBOARDING_STEPS.filter((step) => step.required).length, 4);
  assert.equal(EMPTY_STATES.length, 5);
  assert.equal(SHOWCASE_ENTRIES.length, 12);
  assert.equal(ICON_LABELS.length, 12);
  assert.equal(ANIMATION_AUDITS.length, 5);
  assert.equal(POLISH_CHECKS.length, 14);
  assert.equal(RELEASE_SURFACES.length, 6);
  assert.equal(Object.keys(RELEASE_ROUTES).length, 12);
  assert.deepEqual(
    BREAKPOINTS.map((point) => point.width),
    [480, 768, 1280],
  );
});

test("onboarding progress counts required steps", () => {
  const empty = onboardingProgress();
  assert.equal(empty.total, 5);
  assert.equal(empty.required, 4);
  assert.equal(empty.requiredDone, 0);
  assert.equal(empty.percent, 0);
  const partial = onboardingProgress(ONBOARDING_STEPS, [
    "welcome",
    "first-capture",
  ]);
  assert.equal(partial.done, 2);
  assert.equal(partial.requiredDone, 2);
  assert.equal(formatPercent(partial.percent), "40%");
  assert.equal(formatPercent(150), "100%");
});

test("next onboarding step skips done required steps", () => {
  assert.equal(nextOnboardingStep()?.id, "welcome");
  assert.equal(
    nextOnboardingStep(ONBOARDING_STEPS, ["welcome"])?.id,
    "first-capture",
  );
  assert.equal(
    nextOnboardingStep(
      ONBOARDING_STEPS,
      ONBOARDING_STEPS.map((step) => step.id),
    ),
    undefined,
  );
  assert.equal(isOnboardingComplete(), false);
  const required = ONBOARDING_STEPS.filter((step) => step.required).map(
    (step) => step.id,
  );
  assert.equal(isOnboardingComplete(ONBOARDING_STEPS, required), true);
});

test("first-run state selects the earliest missing surface", () => {
  const empty = { notes: 0, findings: 0, evidence: 0, reports: 0 };
  assert.equal(firstRunSurface(empty), "notes");
  assert.equal(firstRunState(empty)?.actionRoute, "capture.create");
  assert.equal(firstRunSurface({ ...empty, notes: 1 }), "findings");
  assert.equal(
    firstRunSurface({ ...empty, notes: 1, findings: 1 }),
    "evidence",
  );
  assert.equal(
    firstRunSurface({ ...empty, notes: 1, findings: 1, evidence: 1 }),
    "report",
  );
  assert.equal(
    firstRunSurface({ notes: 1, findings: 1, evidence: 1, reports: 1 }),
    "ready",
  );
  assert.equal(emptyStateFor("missing"), undefined);
});

test("showcase and icon helpers resolve kinds", () => {
  assert.equal(showcaseByKind(SHOWCASE_ENTRIES, "finding").length, 2);
  assert.equal(showcaseTokens(SHOWCASE_ENTRIES).length, 12);
  assert.equal(
    kindColorToken("finding"),
    "var(--v3-kind-finding, var(--v3-kind-default))",
  );
  assert.equal(iconForKind(ICON_LABELS, "evidence"), "paperclip");
  assert.equal(iconForKind(ICON_LABELS, "unknown"), undefined);
  assert.equal(labelForKind("finding"), "Finding");
  assert.equal(labelForKind("extra-kind"), "ExtraKind");
  assert.deepEqual(labelConsistencyIssues(ICON_LABELS, KIND_LABELS), []);
  assert.equal(
    labelConsistencyIssues([{ icon: "x", label: "Wrong", kind: "note" }])
      .length,
    1,
  );
});

test("animation audit reports unsafe surfaces and invalid tokens", () => {
  const summary = auditAnimations();
  assert.equal(summary.total, 5);
  assert.equal(summary.safe, 4);
  assert.deepEqual(summary.unsafe, ["skeleton-shimmer"]);
  assert.equal(formatPercent(summary.percent), "80%");
  assert.equal(auditsSafeCount(), 4);
  assert.deepEqual(animationSummarySafe([]).unsafe, []);
  assert.deepEqual(animationsWithInvalidTokens(ANIMATION_AUDITS), []);
  assert.equal(usesMotionToken("--v3-motion-fast"), true);
  assert.equal(usesMotionToken("--v3-motion-instant"), false);
});

test("polish checklist helpers filter and compute progress", () => {
  const progress = polishProgress();
  assert.equal(progress.total, 14);
  assert.equal(progress.done, 14);
  assert.equal(progress.required, 2);
  assert.equal(filterPolishByArea(POLISH_CHECKS, "Animation").length, 2);
  assert.equal(filterPolishByArea(POLISH_CHECKS, "All").length, 14);
  assert.equal(
    withCheckState(POLISH_CHECKS, ["onboarding.steps"]).filter(
      (item) => item.done,
    ).length,
    1,
  );
});

test("responsive helpers resolve breakpoints", () => {
  assert.equal(resolveBreakpoint(320), "narrow");
  assert.equal(resolveBreakpoint(600), "narrow");
  assert.equal(resolveBreakpoint(900), "medium");
  assert.equal(resolveBreakpoint(1600), "wide");
  assert.equal(responsiveRisk("narrow"), "high");
  assert.equal(responsiveRisk("medium"), "medium");
  assert.equal(responsiveRisk("wide"), "low");
});

test("release snapshot combines all audits", () => {
  const snapshot = releaseSnapshot(
    ["welcome"],
    [],
    { notes: 1, findings: 1, evidence: 1, reports: 1 },
    900,
  );
  assert.equal(snapshot.onboarding.done, 1);
  assert.equal(snapshot.polish.done, 0);
  assert.equal(snapshot.animation.unsafe.length, 1);
  assert.equal(snapshot.firstRun, "ready");
  assert.equal(snapshot.breakpoint, "medium");
  assert.equal(snapshot.labelIssues, 0);
});

test("state reducer is additive and reversible", () => {
  const initial = initialReleasePolishState(1000);
  assert.equal(initial.width, 1000);
  assert.equal(initial.checked.length, POLISH_CHECKS.length);
  const completed = releasePolishReducer(initial, {
    type: "complete",
    step: "welcome",
  });
  assert.equal(activeStep(completed), "first-capture");
  assert.equal(
    releasePolishReducer(completed, { type: "complete", step: "welcome" }),
    completed,
  );
  assert.equal(completionLabel(completed), "In progress");
  const dismissed = releasePolishReducer(completed, {
    type: "dismiss",
    surface: "notes",
  });
  assert.deepEqual(dismissed.dismissed, ["notes"]);
  const unchecked = releasePolishReducer(dismissed, {
    type: "toggle-check",
    check: "onboarding.steps",
  });
  assert.equal(unchecked.checked.length, POLISH_CHECKS.length - 1);
  assert.equal(polishLabel(unchecked), "13/14");
  const resized = releasePolishReducer(unchecked, {
    type: "resize",
    width: -10,
  });
  assert.equal(resized.width, 0);
  assert.deepEqual(
    releasePolishReducer(resized, { type: "reset" }),
    initialReleasePolishState(0),
  );
});

test("state reducer validates phase selection", () => {
  const initial = initialReleasePolishState();
  const selected = releasePolishReducer(initial, {
    type: "select-phase",
    phase: "merge",
  });
  assert.equal(selected.selectedPhase, "merge");
  assert.equal(
    releasePolishReducer(initial, { type: "select-phase", phase: "bogus" }),
    initial,
  );
  assert.equal(
    releasePolishReducer(initial, { type: "select-area", area: "Animation" })
      .selectedArea,
    "Animation",
  );
  assert.equal(
    releasePolishReducer(initial, {
      type: "select-surface",
      surface: "evidence",
    }).selectedSurface,
    "evidence",
  );
});

test("client targets every release route", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return json({ ok: true, actions: RELEASE_ROUTES });
  }) as typeof globalThis.fetch;
  const client = new ReleasePolishClient({
    fetch: fetchImpl,
    requestId: () => "req_test",
  });
  await client.manifest();
  await client.golden("capture-to-merge");
  await client.smoke();
  await client.gates();
  await client.docs(true);
  await client.changelog();
  await client.migrationNotes();
  await client.readiness(true);
  await client.onboarding();
  await client.showcase();
  await client.polish();
  assert.equal(calls.length, 11);
  assert.equal(calls[0], "/api/v3/release/manifest");
  assert.equal(calls[1], "/api/v3/release/golden");
  assert.equal(calls[5], "/api/v3/release/changelog");
  assert.equal(calls[10], "/api/v3/release/polish");
  assert.ok(calls.every((entry) => entry.startsWith("/api/v3/release/")));
});

test("components expose stable data and aria attributes", () => {
  const components = [
    "src/features/release-polish/ReleasePolishFeature.tsx",
    "src/features/release-polish/components/OnboardingFlow.tsx",
    "src/features/release-polish/components/EmptyAndFirstRun.tsx",
    "src/features/release-polish/components/DesignSystemShowcase.tsx",
    "src/features/release-polish/components/IconographyAudit.tsx",
    "src/features/release-polish/components/AnimationAuditView.tsx",
    "src/features/release-polish/components/ResponsivePolishChecklist.tsx",
  ];
  for (const relative of components) {
    const text = source(relative);
    assert.ok(
      text.includes("data-"),
      `${relative} must expose data attributes`,
    );
    assert.ok(
      text.includes("aria-"),
      `${relative} must expose aria attributes`,
    );
    assert.ok(text.includes("focusable") || text.includes("focus-visible"));
  }
});

test("feature CSS consumes tokens without redefining them", () => {
  const text = source("src/features/release-polish/release-polish.css");
  assert.ok(text.includes("var(--v3-space-3)"));
  assert.ok(text.includes("prefers-reduced-motion: reduce"));
  assert.ok(!text.includes(":root"));
  assert.ok(!/^\s*--v3-[a-z0-9-]+\s*:/m.test(text));
  assert.ok(text.includes("[data-density"));
});
