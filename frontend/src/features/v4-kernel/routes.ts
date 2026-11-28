import type { V4Route } from "./types-v4";

export const V4_ROUTES: readonly V4Route[] = [
  {
    name: "inbox",
    label: "Inbox",
    path: "/v4/inbox",
    shortcut: "Ctrl+Shift+I",
    icon: "inbox",
  },
  {
    name: "findings",
    label: "Findings",
    path: "/v4/findings",
    shortcut: "Ctrl+Shift+N",
    icon: "shield",
  },
  {
    name: "evidence-lab",
    label: "Evidence Lab",
    path: "/v4/evidence",
    shortcut: "Ctrl+Shift+E",
    icon: "microscope",
  },
  {
    name: "blocks-pro",
    label: "Editor",
    path: "/v4/editor",
    shortcut: "Ctrl+Shift+B",
    icon: "edit",
  },
  {
    name: "query",
    label: "Query",
    path: "/v4/query",
    shortcut: "Ctrl+Shift+Q",
    icon: "search",
  },
  {
    name: "automation",
    label: "Automation",
    path: "/v4/automation",
    shortcut: "Ctrl+Shift+A",
    icon: "workflow",
  },
  {
    name: "report-designer",
    label: "Reports",
    path: "/v4/reports",
    shortcut: "Ctrl+Shift+R",
    icon: "file-text",
  },
  {
    name: "graph-workbench",
    label: "Graph",
    path: "/v4/graph",
    shortcut: "Ctrl+Shift+G",
    icon: "network",
  },
  {
    name: "security-vault",
    label: "Vault",
    path: "/v4/vault",
    shortcut: "Ctrl+Shift+V",
    icon: "lock",
  },
  {
    name: "a11y-i18n",
    label: "Accessibility",
    path: "/v4/accessibility",
    shortcut: "Ctrl+Shift+Y",
    icon: "accessibility",
  },
] as const;

export function routeByName(name: string): V4Route | undefined {
  return V4_ROUTES.find((route) => route.name === name);
}

export function routeByPath(path: string): V4Route | undefined {
  const normalized = path.replace(/\/+$/, "") || "/";
  return V4_ROUTES.find((route) => route.path === normalized);
}

export function applyPreference(preference: {
  theme: "light" | "graphite" | "system";
  density: "compact" | "default" | "comfortable";
  direction: "ltr" | "rtl";
}): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const resolvedTheme =
    preference.theme === "system"
      ? typeof window !== "undefined" &&
        window.matchMedia?.("(prefers-color-scheme: dark)").matches
        ? "graphite"
        : "light"
      : preference.theme;
  root.dataset.v4Theme = resolvedTheme;
  root.dataset.v4Density = preference.density;
  root.dir = preference.direction;
}
