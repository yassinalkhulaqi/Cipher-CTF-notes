import assert from "node:assert/strict";
import test from "node:test";

import {
  additionalLocaleOptions,
  catalogKeys,
  catalogFor,
  coverage,
  interpolate,
  localeDirection,
  normalizeLocale,
  resolvedDirection,
  translate,
} from "../src/features/a11y-refinement/catalogs";
import {
  applyAllFixes,
  buildContrastReport,
  contrastTone,
  evaluatePair,
  formatRatio,
  mergeThemeReports,
  requiredRatio,
  suggestFix,
} from "../src/features/a11y-refinement/contrast";
import {
  formatBytes,
  formatDate,
  formatNumber,
  formatValue,
  isolateBidi,
  localeFormatOptions,
  parseNumber,
  pluralText,
  roundTrip,
} from "../src/features/a11y-refinement/format";
import {
  NAVIGATION_ACTIONS,
  displayBinding,
  findBindings,
  focusOrder,
  groupLabel,
  helpLine,
  keyboardPass,
  normalizeBinding,
  summarizeMap,
} from "../src/features/a11y-refinement/keyboard";
import {
  DEFAULT_APPEARANCE,
  appearanceCss,
  appearanceFromSnapshot,
  checksum,
  clampScale,
  directionPreference,
  motionEquivalence,
  preferenceDiff,
  recordLabel,
  snapshotWithAppearance,
  syncSummary,
  syncTone,
} from "../src/features/a11y-refinement/preferences";
import {
  cssVariables,
  documentAttributes,
  layoutFor,
  layoutManifest,
  paneNames,
  resolveDirection,
  sidesFor,
  validateLayout,
  warningForText,
} from "../src/features/a11y-refinement/rtl";
import type {
  ContrastPairView,
  KeyboardMapView,
  PreferenceSnapshotView,
  SurfaceView,
  SyncReportView,
} from "../src/features/a11y-refinement/types";
import {
  auditSurface,
  filterFindings,
  findingTone,
  rulesForLevel,
  scoreTone,
  severityWeight,
  summarizeAudits,
} from "../src/features/a11y-refinement/wcag";

function surface(patch: Partial<SurfaceView> = {}): SurfaceView {
  return {
    name: "finding-studio",
    label: "Finding studio",
    level: "AA",
    locale: "en",
    focus_obscured: "none",
    focus_indicator_width: 2,
    focus_indicator_contrast: 4.5,
    target_size: 32,
    drag_only: false,
    has_help: true,
    repeated_entry: false,
    auth_captcha: "none",
    non_text_contrast: 3.2,
    hover_content: false,
    keyboard_reachable: true,
    screen_reader_labels: true,
    tiles: ["list", "editor"],
    ...patch,
  };
}

function snapshot(patch: Partial<PreferenceSnapshotView> = {}): PreferenceSnapshotView {
  return {
    locale: "en",
    theme: "graphite",
    direction: "auto",
    font_scale: 1,
    reduce_motion: false,
    high_contrast: false,
    screen_reader_hints: true,
    focus_ring_boost: false,
    shortcuts: {},
    updated_at: "",
    revision: 1,
    ...patch,
  };
}

function keyboardMap(): KeyboardMapView {
  const bindings = NAVIGATION_ACTIONS.map((action, index) => ({
    action,
    keys: ["ctrl", "shift", String(index % 10)],
    label: action.replaceAll("_", " "),
    group: "navigation",
    scope: "global" as const,
    display: `Ctrl+Shift+${index % 10}`,
    enabled: true,
    sequence: index,
    description: "",
  }));
  bindings.push({
    action: "save",
    keys: ["ctrl", "s"],
    label: "Save",
    group: "editing",
    scope: "editor",
    display: "Ctrl+S",
    enabled: true,
    sequence: 0,
    description: "",
  });
  return {
    locale: "en",
    platform: "desktop",
    bindings,
    groups: { navigation: NAVIGATION_ACTIONS, editing: ["save"] },
    conflicts: [],
    coverage: { navigation: NAVIGATION_ACTIONS.length, editing: 1 },
    complete: true,
  };
}

test("locale normalization and catalogs cover additional languages", () => {
  assert.equal(normalizeLocale("pt_BR"), "pt-BR");
  assert.equal(normalizeLocale(""), "en");
  assert.equal(localeDirection("ar-EG"), "rtl");
  assert.equal(localeDirection("de-DE"), "ltr");
  assert.equal(resolvedDirection("fa", "ltr"), "ltr");
  assert.equal(resolvedDirection("en", "auto"), "ltr");
  assert.ok(catalogKeys().includes("v3.search.results"));
  assert.equal(catalogFor("pt-BR")["v3.search.results"], "{count} resultados");
  assert.equal(coverage("en"), 100);
  assert.ok(coverage("fa") < 100);
  assert.equal(additionalLocaleOptions().length, 6);
});

test("translation interpolates and falls back to English", () => {
  assert.equal(translate("en", "v3.search.results", { count: 7 }).message, "7 results");
  const portuguese = translate("pt-BR", "v3.search.results", { count: 3 });
  assert.equal(portuguese.message, "3 resultados");
  assert.equal(portuguese.missing, false);
  const missing = translate("it", "v3.not.a.key");
  assert.equal(missing.message, "v3.not.a.key");
  assert.equal(missing.missing, true);
  assert.equal(translate("fa", "v3.layout.direction", { direction: "rtl" }).message.includes("rtl"), true);
  assert.equal(interpolate("{a} and {b}", { a: "1" }), "1 and {b}");
});

test("locale-aware formatting covers numbers, dates, and bytes", () => {
  assert.equal(formatNumber(1234.5, "en", 2), "1,234.50");
  assert.equal(formatNumber(1234.5, "de-DE", 2), "1.234,50");
  assert.equal(parseNumber("1.234,50", "de-DE"), 1234.5);
  assert.equal(roundTrip(1234.56, "de-DE").exact, true);
  assert.equal(roundTrip(12.5, "en").exact, true);
  assert.equal(formatDate("2026-03-04", "en"), "2026-03-04");
  assert.equal(formatDate("2026-03-04", "de"), "04/03/2026");
  assert.equal(formatBytes(2048, "en", true), "2.0 KiB");
  assert.equal(pluralText(1, "note", "notes", "en"), "1 note");
  assert.equal(pluralText(2, "note", "notes", "en"), "2 notes");
});

test("formatted values carry direction and bidi isolation", () => {
  const english = formatValue("number", 42, "en");
  const persian = formatValue("number", 42, "fa");
  assert.equal(english.direction, "ltr");
  assert.equal(english.bidi_isolated, false);
  assert.equal(persian.direction, "rtl");
  assert.equal(persian.bidi_isolated, true);
  assert.equal(english.text, "42");
  assert.equal(formatValue("percent", 0.125, "en").text, "12.5%");
  assert.equal(formatValue("currency", 12.5, "en").text, "$12.50");
  assert.ok(isolateBidi("abc", "ar").startsWith("\u2068"));
  assert.equal(localeFormatOptions("de-DE").decimal, ",");
});

test("contrast thresholds and evaluation follow WCAG 2.2", () => {
  assert.equal(requiredRatio("AA"), 4.5);
  assert.equal(requiredRatio("AAA"), 7);
  assert.equal(requiredRatio("AA", { graphical: true }), 3);
  assert.equal(requiredRatio("AA", { largeText: true }), 3);
  const dark = evaluatePair({ name: "body", foreground: "#000000", background: "#ffffff" });
  assert.equal(dark.ratio, 21);
  assert.equal(dark.passed, true);
  const faint = evaluatePair({ name: "muted", foreground: "#eeeeee", background: "#ffffff" });
  assert.equal(faint.passed, false);
  assert.equal(formatRatio(4.5), "4.50:1");
});

test("contrast repair produces passing pairs", () => {
  const faint: ContrastPairView = evaluatePair({
    name: "muted",
    foreground: "#eeeeee",
    background: "#ffffff",
  });
  const fix = suggestFix(faint);
  assert.ok(fix.after >= fix.required);
  const report = buildContrastReport([faint]);
  assert.equal(report.passed, false);
  assert.equal(report.failures.length, 1);
  assert.equal(report.fixes.length, 1);
  const repaired = applyAllFixes(report);
  assert.equal(repaired.passed, true);
  assert.equal(buildContrastReport([faint], false).fixes.length, 0);
  assert.equal(contrastTone(100), "good");
  assert.equal(contrastTone(40), "bad");
});

test("theme contrast comparison detects equivalence and shared failures", () => {
  const passing = evaluatePair({ name: "body", foreground: "#111111", background: "#ffffff" });
  const dark = evaluatePair({ name: "body", foreground: "#eeeeee", background: "#111111", level: "AAA" });
  const compared = mergeThemeReports(buildContrastReport([passing]), buildContrastReport([dark]));
  assert.equal(compared.passed, true);
  assert.equal(compared.equivalent, true);
  const failure = evaluatePair({ name: "body", foreground: "#ffffff", background: "#ffffff" });
  const shared = mergeThemeReports(buildContrastReport([failure]), buildContrastReport([failure]));
  assert.equal(shared.passed, false);
  assert.deepEqual(shared.shared, ["body"]);
});

test("WCAG rule catalog and level filtering", () => {
  assert.equal(rulesForLevel("A").length < rulesForLevel("AAA").length, true);
  assert.ok(rulesForLevel("AA").some((rule) => rule.id === "focus.not_obscured"));
  assert.ok(!rulesForLevel("AA").some((rule) => rule.id === "focus.appearance"));
  assert.equal(severityWeight("critical"), 4);
  assert.equal(findingTone("serious"), "bad");
  assert.equal(findingTone("minor"), "neutral");
  assert.equal(scoreTone(95), "good");
  assert.equal(scoreTone(30), "bad");
});

test("client-side audit mirrors backend rule outcomes", () => {
  const clean = auditSurface(surface());
  assert.equal(clean.passed, true);
  assert.equal(clean.findings.length, 0);
  assert.equal(clean.score, 100);
  const failing = auditSurface(
    surface({
      name: "graph",
      drag_only: true,
      target_size: 8,
      focus_obscured: "full",
      keyboard_reachable: false,
      auth_captcha: "puzzle",
      screen_reader_labels: false,
      non_text_contrast: 1.2,
      repeated_entry: true,
      hover_content: true,
      locale: "english",
    }),
  );
  assert.equal(failing.passed, false);
  const rules = failing.findings.map((item) => item.rule);
  assert.ok(rules.includes("pointer.dragging"));
  assert.ok(rules.includes("pointer.target_size"));
  assert.ok(rules.includes("keyboard.reachable"));
  assert.ok(rules.includes("locale.direction"));
  assert.ok(failing.score < 50);
  assert.equal(auditSurface(surface(), "AAA").checked > clean.checked, true);
});

test("audit summaries aggregate findings by severity", () => {
  const runs = [
    auditSurface(surface({ name: "a" })),
    auditSurface(surface({ name: "b", hover_content: true, has_help: false })),
  ];
  const summary = summarizeAudits(runs);
  assert.equal(summary.surfaces, 2);
  assert.equal(summary.failed, 1);
  assert.equal(summary.findings, 2);
  assert.ok(summary.by_severity.moderate >= 1);
  assert.equal(filterFindings(runs, "minor").length, 1);
  assert.equal(filterFindings(runs, "all").length, 2);
  assert.equal(summarizeAudits([]).score, 100);
});

test("RTL layouts mirror panes and keep focus order logical", () => {
  const ltr = layoutFor("finding-studio", "en");
  const rtl = layoutFor("finding-studio", "fa");
  assert.equal(ltr.sides.start, "left");
  assert.equal(rtl.sides.start, "right");
  assert.equal(rtl.sides.end, "left");
  assert.equal(rtl.css_class, "v3-rtl-rtl");
  assert.deepEqual(rtl.ordered_regions, [...ltr.ordered_regions].reverse());
  assert.equal(rtl.mirror_icons.includes("chevron-left"), true);
  assert.equal(validateLayout(rtl).valid, true);
  assert.equal(resolveDirection("ar", "auto"), "rtl");
  assert.equal(sidesFor("rtl").end, "left");
  assert.equal(documentAttributes("ar", "rtl").dir, "rtl");
  assert.ok(paneNames().includes("a11y-refinement"));
  assert.equal(warningForText("hello שלום", "he"), "isolate embedded Latin text");
  assert.equal(warningForText("hello", "en"), "");
});

test("RTL manifest exposes CSS variables for every pane", () => {
  const manifest = layoutManifest("he");
  assert.equal(manifest.rtl, true);
  assert.equal(manifest.css["--v3-inline-start"], "right");
  assert.equal(manifest.panes.length, paneNames().length);
  assert.equal(cssVariables("en")["--v3-inline-start"], "left");
  assert.equal(layoutFor("unknown", "en").ordered_regions.length, 1);
});

test("keyboard bindings normalize, resolve, and validate the full pass", () => {
  const map = keyboardMap();
  assert.deepEqual(normalizeBinding("Control+Shift+A"), ["ctrl", "shift", "a"]);
  assert.deepEqual(normalizeBinding(["meta", "ctrl", "K"]), ["ctrl", "meta", "k"]);
  const save = findBindings(map, ["ctrl", "s"], "editor");
  assert.equal(save.length, 1);
  assert.equal(save[0].action, "save");
  assert.equal(findBindings(map, "Control+S", "dialog").length, 0);
  assert.equal(focusOrder(map)[0], "command_center");
  assert.equal(focusOrder(map, "navigation").length, NAVIGATION_ACTIONS.length);
  assert.equal(groupLabel("navigation"), "Surface navigation");
  assert.equal(displayBinding(save[0], "desktop"), "Ctrl+S");
  assert.ok(helpLine(save[0], "{action}: {binding}", "en").includes("Save: Ctrl+S"));
  const pass = keyboardPass(map);
  assert.equal(pass.complete, true);
  assert.equal(pass.enabled, NAVIGATION_ACTIONS.length + 1);
  assert.equal(summarizeMap(map).groups, 2);
});

test("keyboard pass reports missing navigation bindings", () => {
  const map = keyboardMap();
  const partial: KeyboardMapView = {
    ...map,
    bindings: map.bindings.filter(
      (binding) => binding.action !== "command_center" && binding.action !== "save",
    ),
    groups: { navigation: NAVIGATION_ACTIONS.filter((item) => item !== "command_center") },
    complete: false,
  };
  const pass = keyboardPass(partial);
  assert.equal(pass.complete, false);
  assert.ok(pass.missing.includes("command_center"));
});

test("unified appearance controls theme, motion, and CSS", () => {
  const custom = { ...DEFAULT_APPEARANCE, theme: "light", motion: "off" as const, font_scale: 1.4 };
  const css = appearanceCss(custom);
  assert.equal(css["--v3-theme"], "light");
  assert.equal(css["--v3-motion-slow"], "0ms");
  assert.equal(css["--v3-font-scale"], "1.40");
  assert.equal(clampScale(9), 1.75);
  assert.equal(motionEquivalence("reduced").contentHidden, false);
  assert.equal(motionEquivalence("full").focusOrderPreserved, true);
  const fromSnapshot = appearanceFromSnapshot(snapshot({ theme: "light", reduce_motion: true }));
  assert.equal(fromSnapshot.motion, "reduced");
  assert.equal(fromSnapshot.density, "comfortable");
});

test("appearance round-trips through preference snapshots", () => {
  const base = snapshot();
  const off = { ...DEFAULT_APPEARANCE, motion: "off" as const, theme: "light" };
  const updated = snapshotWithAppearance(base, off);
  assert.equal(updated.revision, 2);
  assert.equal(updated.reduce_motion, true);
  assert.deepEqual(updated.shortcuts["v3.motion_mode"], ["off"]);
  assert.equal(appearanceFromSnapshot(updated).motion, "off");
  const restored = appearanceFromSnapshot(snapshotWithAppearance(updated, DEFAULT_APPEARANCE));
  assert.equal(restored.motion, "full");
  assert.equal(restored.theme, "graphite");
  assert.equal(clampScale(0.1), 0.75);
});

test("preference diff, checksum, and sync reporting", () => {
  const local = snapshot();
  const remote = snapshot({ locale: "fa", theme: "light", revision: 4 });
  assert.notEqual(checksum(local), checksum(remote));
  assert.equal(checksum(local), checksum(snapshot()));
  const changes = preferenceDiff(local, remote);
  assert.deepEqual(changes.map((change) => change.field).sort(), ["locale", "theme"]);
  const report: SyncReportView = {
    strategy: "merge",
    applied: true,
    record: {
      profile: "default",
      revision: 4,
      source: "remote",
      checksum: "abc",
      tags: [],
      preferences: remote,
    },
    changes: ["locale", "theme"],
    conflicts: [],
    warnings: [],
  };
  assert.equal(syncTone(report), "good");
  assert.ok(syncSummary(report).includes("2 changed"));
  assert.equal(syncTone({ ...report, applied: false }), "bad");
  assert.equal(syncTone({ ...report, warnings: ["stale"] }), "warn");
  assert.equal(directionPreference(snapshot({ direction: "rtl" }), "en"), "rtl");
  assert.equal(directionPreference(snapshot(), "ar"), "rtl");
  assert.equal(recordLabel(report.record), "default · r4 · remote");
});
