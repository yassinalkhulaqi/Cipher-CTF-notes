import { V4_ROUTES, routeByName } from "./routes";
import type { V4Preference, V4RouteName } from "./types-v4";

export interface ShellState {
  active: V4RouteName;
  preference: V4Preference;
  sidebarOpen: boolean;
}

export type ShellAction =
  | { type: "navigate"; name: V4RouteName }
  | { type: "toggle-sidebar" }
  | { type: "set-theme"; theme: V4Preference["theme"] }
  | { type: "set-density"; density: V4Preference["density"] }
  | { type: "set-motion"; motion: V4Preference["motion"] }
  | {
      type: "set-locale";
      locale: string;
      direction?: V4Preference["direction"];
    };

const DEFAULT_PREFERENCE: V4Preference = {
  theme: "light",
  density: "default",
  motion: "full",
  locale: "en",
  direction: "ltr",
};

export function initialShellState(active: V4RouteName = "inbox"): ShellState {
  return { active, preference: { ...DEFAULT_PREFERENCE }, sidebarOpen: true };
}

export function reduceShell(
  state: ShellState,
  action: ShellAction,
): ShellState {
  switch (action.type) {
    case "navigate":
      return routeByName(action.name)
        ? { ...state, active: action.name }
        : state;
    case "toggle-sidebar":
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case "set-theme":
      return {
        ...state,
        preference: { ...state.preference, theme: action.theme },
      };
    case "set-density":
      return {
        ...state,
        preference: { ...state.preference, density: action.density },
      };
    case "set-motion":
      return {
        ...state,
        preference: { ...state.preference, motion: action.motion },
      };
    case "set-locale":
      return {
        ...state,
        preference: {
          ...state.preference,
          locale: action.locale,
          direction: action.direction ?? state.preference.direction,
        },
      };
    default:
      return state;
  }
}

export function shortcutMap(): Record<string, V4RouteName> {
  const map: Record<string, V4RouteName> = {};
  for (const route of V4_ROUTES) {
    if (route.shortcut) map[route.shortcut] = route.name;
  }
  return map;
}
