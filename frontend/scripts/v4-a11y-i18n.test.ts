import assert from "node:assert/strict";
import test from "node:test";

import {
  ACCESSIBILITY_ROUTE,
  AccessibilityClient,
  AccessibilityClientError,
  describeClientError,
} from "../src/features/a11y-i18n/client";
import type {
  AccessibilityStatus,
  AuditIssueView,
  PatchResponse,
  TourStateView,
} from "../src/features/a11y-i18n/client";
import {
  accessibilityReducer,
  canSaveSnapshot,
  directionForLocale,
  hydrateStatus,
  initialAccessibilityState,
  issueCountLabel,
  issueSeverityCounts,
  motionDurationLabel,
  motionLabel,
  nextTourOperation,
  preferencePatch,
  sortedIssues,
  statusSummary,
  tourProgress,
} from "../src/features/a11y-i18n/state";
import type {
  AccessibilityAction,
  AccessibilityState,
} from "../src/features/a11y-i18n/state";
import { V4Client } from "../src/features/v4-kernel/client";

const STATUS: AccessibilityStatus = {
  actions: ["preferences", "audit", "tour", "snapshot-save"],
  capabilities: ["read", "write"],
  catalogs: {
    version: 1,
    catalogs: [
      {
        locale: "en",
        language: "en",
        direction: "ltr",
        message_count: 26,
        checksum: "abc123",
      },
      {
        locale: "ar",
        language: "ar",
        direction: "rtl",
        message_count: 3,
        checksum: "def456",
      },
    ],
  },
  directions: { en: "ltr", ar: "rtl", fr: "ltr" },
  empty_states: {
    issues: {
      title: "No issues",
      body: "Run the audit",
      action_label: "Audit",
    },
    snapshots: {
      title: "No snapshots",
      body: "Save one",
      action_label: "Save",
    },
    tour: { title: "Done", body: "Restart", action_label: "Restart" },
  },
  event_count: 2,
  feature_enabled: true,
  locales: ["ar", "en", "fr"],
  motion: {
    preference: "full",
    durations: { fast: 120, normal: 220, slow: 380, pulse: 1600 },
    reduce_transparency: false,
    animated: true,
  },
  preferences: {
    theme: "light",
    density: "default",
    motion: "full",
    locale: "en",
    direction: "ltr",
    reduce_transparency: false,
    high_contrast: false,
    font_scale: 1,
  },
  reduce_motion: false,
  rules: [
    {
      id: "missing-label",
      description: "Names for controls",
      severity: "error",
      enabled: true,
    },
    {
      id: "low-contrast",
      description: "Contrast matters",
      severity: "warning",
      enabled: true,
    },
  ],
  snapshots: {
    names: ["baseline"],
    locales: ["en"],
    total: 1,
    latest_saved_at: "2026-11-28T00:00:00.000Z",
  },
  tour: {
    index: 0,
    status: "not_started",
    visited_ids: [],
    completed_ids: [],
    total: 3,
    can_advance: true,
    can_go_back: false,
    progress: 0.333,
  },
  tour_step: {
    id: "tour-controls",
    target: "control-grid",
    title: "Choose your display",
    body: "Start here",
  },
};

const ISSUES: AuditIssueView[] = [
  {
    rule_id: "low-contrast",
    target: "muted",
    detail: "Low contrast",
    suggestion: "Darken text",
    severity: "warning",
    fingerprint: "low-contrast:muted",
  },
  {
    rule_id: "missing-label",
    target: "save",
    detail: "No name",
    suggestion: "Add aria-label",
    severity: "error",
    fingerprint: "missing-label:save",
  },
];

function patchResponse(
  action: string,
  result: Record<string, unknown> = {},
): PatchResponse {
  return { action, result, status: STATUS };
}

function fakeClient(payload: unknown, status = 200): V4Client {
  const fetchImpl = (async () => ({
    ok: status < 400,
    status,
    json: async () => payload,
  })) as unknown as typeof fetch;
  return new V4Client("/api/v4", fetchImpl);
}

function jsonResponse(payload: unknown) {
  return {
    data: payload,
    meta: { request_id: "req-1", version: "v4", page: 1, page_size: 50 },
  };
}

function apply(
  state: AccessibilityState,
  ...actions: AccessibilityAction[]
): AccessibilityState {
  return actions.reduce(
    (current, action) => accessibilityReducer(current, action),
    state,
  );
}

test("initial state is deterministic and unhydrated", () => {
  const state = initialAccessibilityState();
  assert.equal(state.status, null);
  assert.equal(state.theme, "light");
  assert.equal(state.locale, "en");
  assert.equal(state.activeTab, "controls");
  assert.equal(state.dirty, false);
  assert.equal(state.issues.length, 0);
});

test("hydrate syncs preferences from the status envelope", () => {
  const state = apply(initialAccessibilityState(), {
    type: "hydrate",
    status: STATUS,
  });
  assert.equal(state.locale, "en");
  assert.equal(state.direction, "ltr");
  assert.equal(state.tour?.total, 3);
  assert.deepEqual(state.snapshots, ["baseline"]);
  assert.equal(state.error, null);
});

test("hydrateStatus mirrors RTL direction", () => {
  const rtl: AccessibilityStatus = {
    ...STATUS,
    preferences: { ...STATUS.preferences, locale: "ar", direction: "rtl" },
  };
  const state = hydrateStatus(initialAccessibilityState(), rtl);
  assert.equal(state.previewDirection, "rtl");
  assert.equal(directionForLocale(rtl.directions, "ar"), "rtl");
  assert.equal(directionForLocale(rtl.directions, "en"), "ltr");
});

test("preference actions mark the state dirty", () => {
  const start = apply(initialAccessibilityState(), {
    type: "hydrate",
    status: STATUS,
  });
  const state = apply(
    start,
    { type: "set-theme", theme: "graphite" },
    { type: "set-density", density: "compact" },
    { type: "set-motion", motion: "off" },
    { type: "set-locale", locale: "ar", direction: "rtl" },
    { type: "set-reduce-motion", value: true },
    { type: "set-high-contrast", value: true },
    { type: "set-font-scale", value: 1.25 },
  );
  assert.equal(state.theme, "graphite");
  assert.equal(state.density, "compact");
  assert.equal(state.motion, "off");
  assert.equal(state.locale, "ar");
  assert.equal(state.direction, "rtl");
  assert.equal(state.previewDirection, "rtl");
  assert.equal(state.reduceMotion, true);
  assert.equal(state.highContrast, true);
  assert.equal(state.fontScale, 1.25);
  assert.equal(state.dirty, true);
});

test("set-locale uses existing direction when none is supplied", () => {
  const start = apply(initialAccessibilityState(), {
    type: "set-locale",
    locale: "ar",
    direction: "rtl",
  });
  const state = apply(start, { type: "set-locale", locale: "fr" });
  assert.equal(state.direction, "rtl");
});

test("preview toggle does not mark state dirty", () => {
  const state = apply(initialAccessibilityState(), {
    type: "set-preview",
    direction: "rtl",
  });
  assert.equal(state.previewDirection, "rtl");
  assert.equal(state.dirty, false);
});

test("issue, tour, snapshot, tab, and error actions update their fields", () => {
  const tour: TourStateView = {
    ...STATUS.tour,
    index: 1,
    status: "in_progress",
  };
  const state = apply(
    initialAccessibilityState(),
    { type: "set-issues", issues: ISSUES },
    { type: "set-tour", state: tour, step: STATUS.tour_step },
    { type: "set-snapshots", names: ["a", "b"] },
    { type: "set-tab", tab: "audit" },
    { type: "set-busy", busy: true },
    { type: "set-error", error: "No such snapshot" },
  );
  assert.equal(state.issues.length, 2);
  assert.equal(state.tour?.index, 1);
  assert.equal(state.tourStep?.id, "tour-controls");
  assert.deepEqual(state.snapshots, ["a", "b"]);
  assert.equal(state.activeTab, "audit");
  assert.equal(state.busy, false);
  assert.equal(state.error, "No such snapshot");
});

test("apply-response hydrates and remembers the last action", () => {
  const state = apply(initialAccessibilityState(), {
    type: "apply-response",
    response: patchResponse("motion", { preference: "off" }),
  });
  assert.equal(state.lastAction, "motion");
  assert.equal(state.dirty, false);
  assert.equal(state.busy, false);
});

test("mark-saved deduplicates and sorts snapshot names", () => {
  const start = apply(initialAccessibilityState(), {
    type: "hydrate",
    status: STATUS,
  });
  const state = apply(
    start,
    { type: "mark-saved", name: "zeta" },
    { type: "mark-saved", name: "alpha" },
  );
  assert.deepEqual(state.snapshots, ["alpha", "baseline", "zeta"]);
  assert.equal(state.lastSaved, "alpha");
});

test("clear resets the panel", () => {
  const state = apply(
    initialAccessibilityState(),
    { type: "hydrate", status: STATUS },
    { type: "set-theme", theme: "graphite" },
    { type: "clear" },
  );
  assert.equal(state.status, null);
  assert.equal(state.theme, "light");
});

test("preferencePatch builds a complete PATCH body", () => {
  const state = apply(
    initialAccessibilityState(),
    { type: "set-motion", motion: "subtle" },
    { type: "set-reduce-motion", value: true },
  );
  const patch = preferencePatch(state);
  assert.equal(patch.motion, "subtle");
  assert.equal(patch.reduce_transparency, true);
  assert.equal(patch.direction, "ltr");
  assert.equal(patch.font_scale, 1);
});

test("sortedIssues orders errors before warnings", () => {
  assert.deepEqual(
    sortedIssues(ISSUES).map((issue) => issue.fingerprint),
    ["missing-label:save", "low-contrast:muted"],
  );
  assert.deepEqual(issueSeverityCounts(ISSUES), {
    error: 1,
    warning: 1,
    info: 0,
  });
  assert.deepEqual(issueSeverityCounts([]), { error: 0, warning: 0, info: 0 });
});

test("display selectors format labels and progress", () => {
  assert.equal(motionLabel("off"), "No motion");
  assert.equal(motionLabel("subtle"), "Reduced motion");
  assert.equal(motionDurationLabel(STATUS.motion), "220ms");
  assert.equal(motionDurationLabel(null), "—");
  assert.equal(tourProgress(null), 0);
  assert.equal(tourProgress(STATUS.tour), 0);
  assert.equal(tourProgress({ ...STATUS.tour, index: 3 }), 100);
  assert.equal(issueCountLabel(1), "1 issue");
  assert.equal(issueCountLabel(2), "2 issues");
  assert.equal(statusSummary(STATUS), "2 rules · 3 locales · 1 snapshots");
  assert.ok(statusSummary(null).includes("Loading"));
});

test("nextTourOperation follows the tour lifecycle", () => {
  assert.equal(nextTourOperation(null), "start");
  assert.equal(nextTourOperation(STATUS.tour), "start");
  assert.equal(
    nextTourOperation({ ...STATUS.tour, status: "in_progress" }),
    "next",
  );
  assert.equal(
    nextTourOperation({ ...STATUS.tour, status: "completed" }),
    "reset",
  );
  assert.equal(
    nextTourOperation({ ...STATUS.tour, status: "skipped" }),
    "reset",
  );
});

test("canSaveSnapshot validates names", () => {
  const state = apply(initialAccessibilityState(), {
    type: "hydrate",
    status: STATUS,
  });
  assert.equal(canSaveSnapshot(state, "baseline"), false);
  assert.equal(canSaveSnapshot(state, "fresh"), true);
  assert.equal(canSaveSnapshot(state, "  "), false);
});

test("client fetches the status envelope", async () => {
  const client = new AccessibilityClient(fakeClient(jsonResponse(STATUS)));
  const result = await client.status();
  assert.equal(result.data.locales.length, 3);
  assert.equal(result.meta.version, "v4");
});

test("client converts error envelopes into typed errors", async () => {
  const client = new AccessibilityClient(
    fakeClient(
      {
        error: {
          code: "not_found",
          message: "No snapshot",
          details: ["ghost"],
        },
      },
      404,
    ),
  );
  await assert.rejects(
    () => client.patch({ action: "snapshot-load", name: "ghost" }),
    (error: unknown) => {
      assert.ok(error instanceof AccessibilityClientError);
      assert.equal(error.code, "not_found");
      assert.deepEqual(error.details, ["ghost"]);
      return true;
    },
  );
});

test("client wraps preference, motion, and reset patches", async () => {
  const seen: unknown[] = [];
  const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    seen.push(JSON.parse(String(init?.body)));
    return {
      ok: true,
      status: 200,
      json: async () => jsonResponse(patchResponse("preferences")),
    } as Response;
  }) as typeof fetch;
  const client = new AccessibilityClient(new V4Client("/api/v4", fetchImpl));
  await client.applyPreferences({ theme: "graphite" });
  await client.setMotion("subtle", true);
  await client.reset();
  assert.equal(seen.length, 3);
  assert.deepEqual(seen[0], {
    action: "preferences",
    preferences: { theme: "graphite" },
  });
  assert.deepEqual(seen[1], {
    action: "motion",
    motion: "subtle",
    reduce_motion: true,
  });
  assert.deepEqual(seen[2], { action: "reset" });
});

test("client unwraps translation, audit, and tour results", async () => {
  const payloads: Record<string, unknown> = {
    translate: {
      translation: {
        text: "2 items",
        message: "items.count",
        locale: "en",
        resolved_locale: "en",
        fallback_used: false,
        missing_placeholders: [],
      },
    },
    audit: {
      report: {
        issues: ISSUES,
        rules_run: ["missing-label"],
        descriptor_count: 2,
        passed: false,
        severity_counts: { error: 1, warning: 1, info: 0 },
      },
    },
    tour: {
      operation: "next",
      state: STATUS.tour,
      step: STATUS.tour_step,
    },
  };
  const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { action: string };
    return {
      ok: true,
      status: 200,
      json: async () =>
        jsonResponse(
          patchResponse(
            body.action,
            payloads[body.action] as Record<string, unknown>,
          ),
        ),
    } as Response;
  }) as typeof fetch;
  const client = new AccessibilityClient(new V4Client("/api/v4", fetchImpl));
  assert.equal(
    (await client.translate({ message: "items.count", locale: "en" })).text,
    "2 items",
  );
  assert.equal((await client.audit([])).issues.length, 2);
  assert.equal((await client.tour("next")).step.id, "tour-controls");
});

test("client wraps snapshot actions with the right verbs", async () => {
  const seen: Array<{ action: string; name?: string }> = [];
  const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    seen.push(
      JSON.parse(String(init?.body)) as { action: string; name?: string },
    );
    return {
      ok: true,
      status: 200,
      json: async () => jsonResponse(patchResponse("snapshot-save")),
    } as Response;
  }) as typeof fetch;
  const client = new AccessibilityClient(new V4Client("/api/v4", fetchImpl));
  await client.saveSnapshot("night", true);
  await client.loadSnapshot("night");
  await client.deleteSnapshot("night");
  assert.deepEqual(seen, [
    { action: "snapshot-save", name: "night", overwrite: true },
    { action: "snapshot-load", name: "night" },
    { action: "snapshot-delete", name: "night" },
  ]);
});

test("describeClientError normalizes unknown failures", () => {
  const typed = describeClientError({
    code: "forbidden",
    message: "No access",
    details: ["a"],
  });
  assert.equal(typed.code, "forbidden");
  assert.deepEqual(typed.details, ["a"]);
  const fallback = describeClientError("broken");
  assert.equal(fallback.code, "internal");
  assert.equal(fallback.message, "Accessibility request failed");
  const existing = new AccessibilityClientError("conflict", "Duplicate");
  assert.equal(describeClientError(existing), existing);
});

test("client route constant matches the kernel route", () => {
  assert.equal(ACCESSIBILITY_ROUTE, "/accessibility");
});
