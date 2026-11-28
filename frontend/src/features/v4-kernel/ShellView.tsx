import type { ReactNode } from "react";

import { V4_ROUTES } from "./routes";
import {
  reduceShell,
  initialShellState,
  type ShellAction,
  type ShellState,
} from "./shell";
import type { V4RouteName } from "./types-v4";

export interface ShellProps {
  state: ShellState;
  dispatch: (action: ShellAction) => void;
  renderContent: (active: V4RouteName) => ReactNode;
}

export function routeLabel(name: V4RouteName): string {
  return V4_ROUTES.find((route) => route.name === name)?.label ?? name;
}

export function createShellController(initial: V4RouteName = "inbox"): {
  state: ShellState;
  dispatch: (action: ShellAction) => void;
} {
  let state = initialShellState(initial);
  return {
    get state() {
      return state;
    },
    dispatch(action: ShellAction) {
      state = reduceShell(state, action);
    },
  };
}

export function shellSummary(state: ShellState): string {
  const active = routeLabel(state.active);
  const theme = state.preference.theme;
  const sidebar = state.sidebarOpen ? "open" : "closed";
  return `${active} | ${theme} | ${sidebar}`;
}

export function visibleRoutes(filter: string): typeof V4_ROUTES {
  const needle = filter.trim().toLowerCase();
  if (!needle) return V4_ROUTES;
  return V4_ROUTES.filter(
    (route) =>
      route.label.toLowerCase().includes(needle) ||
      route.name.toLowerCase().includes(needle),
  );
}
