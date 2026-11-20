import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { A11yClient } from "../src/features/a11y/client";
import type { A11yTransport } from "../src/features/a11y/client";
import {
  DEFAULT_A11Y_PREFERENCES,
  DIRECTION_LABEL,
  WCAG_LEVELS,
} from "../src/features/a11y/config";
import {
  bidiWarnings,
  bindingId,
  clampFontScale,
  contrastGrade,
  contrastStatus,
  createAnnouncement,
  cssVarName,
  directionOfLocale,
  findBindingConflicts,
  focusStepLabel,
  formatBinding,
  formatFontScale,
  formatRatio,
  groupShortcuts,
  isolateBidiText,
  issuePenalty,
  matchLocale,
  mergePreferences,
  mirrorPunctuation,
  normalizeBinding,
  normalizeLocaleTag,
  normalizeThemeName,
  parseBinding,
  preferenceSignature,
  resolveDirection,
  sanitizeCssValue,
  severityLabel,
  severityRank,
  sortFocusSteps,
  sortIssues,
  summarizeIssues,
  themeToCss,
  trimAnnouncements,
} from "../src/features/a11y/pure";
import { useA11yStore } from "../src/features/a11y/store";
import type {
  AuditIssue,
  FocusStep,
  ShortcutBinding,
} from "../src/features/a11y/types";

const root = process.cwd();

function issue(
  rule: string,
  severity: AuditIssue["severity"],
  target = "document",
): AuditIssue {
  return {
    rule,
    severity,
    target,
    message: `${rule} message`,
    wcag: "4.1.2",
    remediation: `Fix ${rule}`,
  };
}

function shortcut(
  action: string,
  keys: readonly string[],
  scope = "global",
): ShortcutBinding {
  return {
    action,
    keys: [...keys],
    label: action,
    scope,
    description: `${action} shortcut`,
    enabled: true,
    sequence: 0,
    binding: keys.join("+"),
  };
}

test("locale normalization resolves languages and writing directions", () => {
  assert.equal(normalizeLocaleTag("en_US"), "en-US");
  assert.equal(normalizeLocaleTag("  he  "), "he");
  assert.equal(directionOfLocale("ar-EG"), "rtl");
  assert.equal(directionOfLocale("fr-CA"), "ltr");
  assert.equal(resolveDirection("auto", "ur-PK"), "rtl");
  assert.equal(resolveDirection("ltr", "ar"), "ltr");
  assert.equal(matchLocale("fr-CA", ["en", "fr", "fr-BE"]), "fr");
  assert.equal(DIRECTION_LABEL.rtl, "Right to left");
});

test("font scale and ratio formatting clamp and render values", () => {
  assert.equal(clampFontScale(Number.NaN), 1);
  assert.equal(clampFontScale(5), 2);
  assert.equal(clampFontScale(0.1), 0.75);
  assert.equal(formatFontScale(1.875), "188%");
  assert.equal(formatRatio(21), "21.00:1");
  assert.equal(formatRatio(Number.NaN), "—");
});

test("issue helpers rank, sort, and summarize findings", () => {
  const issues = [
    issue("aria.low", "minor"),
    issue("contrast.high", "critical", "body"),
    issue("aria.mid", "moderate"),
  ];
  assert.equal(severityRank("critical"), 5);
  assert.equal(severityRank("unknown"), 0);
  assert.equal(severityLabel("serious"), "Serious");
  assert.deepEqual(
    sortIssues(issues).map((item) => item.rule),
    ["contrast.high", "aria.mid", "aria.low"],
  );
  assert.deepEqual(summarizeIssues(issues), {
    critical: 1,
    serious: 0,
    moderate: 1,
    minor: 1,
    info: 0,
  });
  assert.equal(issuePenalty(issues), 20);
});

test("contrast grading and status honor WCAG levels", () => {
  assert.deepEqual(WcagLevelOrLevels(), ["A", "AA", "AAA"]);
  assert.equal(contrastGrade(95), "A");
  assert.equal(contrastGrade(72), "C");
  assert.equal(contrastGrade(12), "F");
  assert.equal(
    contrastStatus({ passed: true, ratio: 7, required: 4.5 }, "AA"),
    "pass",
  );
  assert.equal(
    contrastStatus({ passed: false, ratio: 7, required: 4.5 }, "AA"),
    "fail",
  );
  assert.equal(
    contrastStatus({ passed: true, ratio: 7, required: 4.5 }, "XYZ"),
    "unknown",
  );
});

function WcagLevelOrLevels(): readonly string[] {
  return WCAG_LEVELS;
}

test("shortcut parsing produces stable sorted bindings", () => {
  assert.deepEqual(parseBinding("Ctrl + Shift + F"), ["ctrl", "shift", "f"]);
  assert.deepEqual(parseBinding(["escape", "control", "ctrl"]), [
    "ctrl",
    "esc",
  ]);
  assert.equal(normalizeBinding("option+cmd+a"), "alt+meta+a");
  assert.equal(formatBinding(["ctrl", "p"], "desktop"), "Ctrl+P");
  assert.equal(formatBinding(["meta", "shift", "a"], "mac"), "⇧+⌘+A");
  assert.equal(bindingId(["ctrl", "alt", "s"]), "ctrl+alt+s");
});

test("shortcut grouping and conflict detection respect scopes", () => {
  const shortcuts = [
    shortcut("notes.save", ["ctrl", "s"], "editor"),
    shortcut("app.save", ["ctrl", "s"], "global"),
    shortcut("find", ["ctrl", "f"], "editor"),
  ];
  const groups = groupShortcuts(shortcuts);
  assert.equal(groups.global.length, 1);
  assert.equal(groups.editor.length, 2);
  const conflicts = findBindingConflicts(shortcuts);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].binding, "ctrl+s");
  assert.equal(conflicts[0].first, "editor::notes.save");
});

test("preferences merge clamps values and signatures track changes", () => {
  const merged = mergePreferences(
    DEFAULT_A11Y_PREFERENCES,
    {
      locale: "ar_EG",
      theme: "High Contrast",
      font_scale: 5,
      shortcuts: { "notes.save": ["Control", "S"] },
    },
    "2026-11-18T12:00:00Z",
  );
  assert.equal(merged.locale, "ar-EG");
  assert.equal(merged.theme, "high-contrast");
  assert.equal(merged.font_scale, 2);
  assert.equal(merged.revision, 1);
  assert.deepEqual(merged.shortcuts["notes.save"], ["ctrl", "s"]);
  const signature = preferenceSignature(merged);
  assert.match(signature, /^[0-9a-f]{8}$/);
  assert.equal(signature, preferenceSignature(merged));
  assert.notEqual(
    signature,
    preferenceSignature({ ...merged, theme: "paper" }),
  );
});

test("theme helpers emit safe CSS custom properties", () => {
  const css = themeToCss(
    {
      name: "custom",
      label: "Custom",
      mode: "dark",
      tokens: { "text-muted": "#667085;", background: "#ffffff" },
    },
    "[data-a11y-theme='custom']",
  );
  assert.match(css, /--a11y-text-muted: #667085;/);
  assert.match(css, /--a11y-background: #ffffff;/);
  assert.equal(cssVarName("Focus Ring"), "--a11y-focus-ring");
  assert.equal(sanitizeCssValue("#fff;} body{}"), "#fff body");
});

test("bidi helpers isolate text and warn on mixed punctuation", () => {
  assert.equal(mirrorPunctuation("(hello)"), ")hello(");
  assert.equal(isolateBidiText("مرحبا", "ltr"), "مرحبا");
  assert.match(isolateBidiText("مرحبا", "rtl"), /^\u2068.+\u2069$/);
  assert.deepEqual(bidiWarnings("Review (v2"), [
    "Unbalanced brackets",
    "Mixed digits and letters",
  ]);
  assert.deepEqual(bidiWarnings("plain text"), []);
});

test("focus and announcement helpers sort and trim entries", () => {
  const steps: FocusStep[] = [
    {
      order: 1,
      target: "one",
      tag: "button",
      tab_index: 2,
      description: "Second",
      hidden: false,
    },
    {
      order: 2,
      target: "two",
      tag: "a",
      tab_index: -1,
      description: "Hidden link",
      hidden: true,
    },
    {
      order: 3,
      target: "three",
      tag: "input",
      tab_index: 0,
      description: "",
      hidden: false,
    },
  ];
  assert.deepEqual(
    sortFocusSteps(steps).map((step) => step.order),
    [2, 3, 1],
  );
  assert.equal(focusStepLabel(steps[1]), "2. Hidden link (hidden)");
  const announcements = Array.from({ length: 9 }, (_, index) =>
    createAnnouncement(`Message ${index}`, "polite", `id-${index}`),
  );
  assert.equal(trimAnnouncements(announcements).length, 6);
  assert.equal(trimAnnouncements(announcements)[0].message, "Message 3");
});

test("A11yClient maps facade methods to namespace routes", async () => {
  const calls: Array<{
    route: string;
    body: Record<string, unknown>;
    options: Record<string, unknown>;
  }> = [];
  const transport: A11yTransport = {
    async call<T>(
      route: string,
      body: Record<string, unknown> = {},
      options: Record<string, unknown> = {},
    ): Promise<T> {
      calls.push({ route, body, options });
      if (route === "a11y.shortcuts") {
        return {
          shortcuts: [],
          conflicts: [],
          unknown_keys: {},
          valid: true,
          groups: {},
        } as T;
      }
      if (route === "a11y.preferences_update") {
        return {
          version: 1,
          profile: "default",
          source: "test",
          signature: "abc",
          preferences: DEFAULT_A11Y_PREFERENCES,
        } as T;
      }
      return { route } as T;
    },
  };
  const client = new A11yClient({ client: transport });

  await client.contrastCheck("#000000", "#ffffff", "AAA");
  await client.shortcuts(
    { "notes.save": ["ctrl", "shift", "s"] },
    "notes.save",
    "editor",
  );
  await client.preferencesUpdate({ locale: "fr" }, "default", "idem-1");
  await client.dashboard({ locale: "fr" });

  assert.deepEqual(
    calls.map((entry) => entry.route),
    [
      "a11y.contrast_check",
      "a11y.shortcuts",
      "a11y.preferences_update",
      "a11y.dashboard",
    ],
  );
  assert.deepEqual(calls[0].body, {
    foreground: "#000000",
    background: "#ffffff",
    level: "AAA",
  });
  assert.deepEqual(calls[1].body.suggest_for, "notes.save");
  assert.equal(calls[1].body.scope, "editor");
  assert.deepEqual(calls[2].options, { idempotencyKey: "idem-1" });
});

test("store updates preferences, revisions, and announcements", () => {
  const store = useA11yStore;
  store.getState().resetPreferences();
  const before = store.getState().preferences;
  store.getState().updatePreferences({ locale: "de-DE", font_scale: 1.5 });
  const after = store.getState().preferences;
  assert.equal(after.locale, "de-DE");
  assert.equal(after.font_scale, 1.5);
  assert.equal(after.revision, before.revision + 1);
  assert.ok(store.getState().announcements.length > 0);
  const firstId = store.getState().announcements[0].id;
  store.getState().dismissAnnouncement(firstId);
  assert.equal(
    store.getState().announcements.some((item) => item.id === firstId),
    false,
  );
  store.getState().clearAnnouncements();
  assert.equal(store.getState().announcements.length, 0);
});

test("a11y stylesheet and test registration are wired into the frontend", () => {
  const css = readFileSync(
    path.join(root, "src", "styles", "a11y.css"),
    "utf8",
  );
  const panel = readFileSync(
    path.join(root, "src", "features", "a11y", "components", "A11yPanel.tsx"),
    "utf8",
  );
  const suitesDir = path.join(root, "scripts", "test-suites");
  const registration = readdirSync(suitesDir)
    .filter((name) => name.endsWith(".json"))
    .map((name) => readFileSync(path.join(suitesDir, name), "utf8"))
    .join("\n");
  assert.match(css, /--a11y-font-scale/);
  assert.match(css, /a11y-reduce-motion/);
  assert.match(panel, /styles\/a11y\.css/);
  assert.match(registration, /"a11y_v2\.test\.ts"/);
});
