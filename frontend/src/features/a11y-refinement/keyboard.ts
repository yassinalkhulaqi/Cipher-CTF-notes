/** Complete keyboard map helpers and keyboard-pass validation. */

import type { KeyboardBindingView, KeyboardMapView } from "./types";

export const NAVIGATION_ACTIONS = [
  "command_center",
  "findings_studio",
  "evidence_lab",
  "graph_workbench",
  "search_intelligence",
  "playbook_automation",
  "report_designer",
  "timeline_view",
  "sync_view",
  "security_view",
  "performance_hud",
  "a11y_refinement",
];

export const GROUP_LABELS: Record<string, string> = {
  navigation: "Surface navigation",
  focus: "Focus and announcements",
  display: "Display and motion",
  editing: "Editing",
  global: "Global commands",
  editor: "Editor",
  sidebar: "Sidebar",
  dialog: "Dialogs",
  reading: "Reading view",
};

export function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group.charAt(0).toUpperCase() + group.slice(1);
}

export function bindingsForGroup(
  map: KeyboardMapView,
  group: string,
): KeyboardBindingView[] {
  return map.bindings.filter((binding) => binding.group === group);
}

export function normalizeBinding(value: string | string[]): string[] {
  const parts = typeof value === "string" ? value.split(/\s*\+\s*|\s+/) : value;
  const aliases: Record<string, string> = {
    control: "ctrl",
    command: "meta",
    cmd: "meta",
    option: "alt",
    escape: "esc",
    return: "enter",
    arrowup: "up",
    arrowdown: "down",
    arrowleft: "left",
    arrowright: "right",
  };
  const order = ["ctrl", "alt", "shift", "meta"];
  const keys: string[] = [];
  for (const part of parts) {
    const key = aliases[part.toLowerCase()] ?? part.toLowerCase();
    if (key && !keys.includes(key)) keys.push(key);
  }
  return [
    ...order.filter((key) => keys.includes(key)),
    ...keys.filter((key) => !order.includes(key)),
  ];
}

export function bindingKey(keys: string[]): string {
  return normalizeBinding(keys).join("+");
}

export function findBindings(
  map: KeyboardMapView,
  pressed: string | string[],
  scope = "",
): KeyboardBindingView[] {
  const key = bindingKey(typeof pressed === "string" ? [pressed] : pressed);
  return map.bindings.filter(
    (binding) =>
      binding.enabled &&
      bindingKey(binding.keys) === key &&
      (!scope || binding.scope === scope || binding.scope === "global"),
  );
}

export function displayBinding(
  binding: KeyboardBindingView,
  platform: string,
): string {
  if (platform !== "mac") return binding.display;
  const labels: Record<string, string> = {
    ctrl: "⌘",
    alt: "⌥",
    shift: "⇧",
    meta: "⌘",
  };
  return normalizeBinding(binding.keys)
    .map((key) => labels[key] ?? (key.length === 1 ? key.toUpperCase() : key))
    .join("+");
}

export function focusOrder(map: KeyboardMapView, surface = ""): string[] {
  const ordered = [...map.bindings].sort((first, second) => {
    if (first.group === "navigation" && second.group !== "navigation")
      return -1;
    if (second.group === "navigation" && first.group !== "navigation") return 1;
    return (
      first.sequence - second.sequence ||
      first.action.localeCompare(second.action)
    );
  });
  const selected = surface
    ? ordered.filter(
        (item) => item.action.includes(surface) || item.group === surface,
      )
    : ordered;
  return selected.map((item) => item.action);
}

export function keyboardPass(map: KeyboardMapView): {
  complete: boolean;
  missing: string[];
  conflicts: number;
  enabled: number;
} {
  const actions = new Set(map.bindings.map((binding) => binding.action));
  const missing = NAVIGATION_ACTIONS.filter((action) => !actions.has(action));
  return {
    complete:
      missing.length === 0 &&
      map.conflicts.length === 0 &&
      map.bindings.length > 0,
    missing,
    conflicts: map.conflicts.length,
    enabled: map.bindings.filter((binding) => binding.enabled).length,
  };
}

export function summarizeMap(map: KeyboardMapView): {
  bindings: number;
  groups: number;
  conflicts: number;
  byScope: Record<string, number>;
} {
  const byScope: Record<string, number> = {};
  for (const binding of map.bindings) {
    byScope[binding.scope] = (byScope[binding.scope] ?? 0) + 1;
  }
  return {
    bindings: map.bindings.length,
    groups: Object.keys(map.groups).length,
    conflicts: map.conflicts.length,
    byScope,
  };
}

export function helpLine(
  binding: KeyboardBindingView,
  localeTemplate: string,
  locale: string,
): string {
  const rendered = localeTemplate
    .replace("{action}", binding.label)
    .replace("{binding}", binding.display);
  return locale === "fa" || locale === "ar" || locale === "ur"
    ? `\u2067${rendered}\u2069`
    : rendered;
}
