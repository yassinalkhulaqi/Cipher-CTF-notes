export type RouteName =
  | "home"
  | "note"
  | "engagements"
  | "engagement"
  | "finding"
  | "search"
  | "reports"
  | "settings"
  | "not-found";

export interface RouteDefinition {
  /** Stable identifier used by `buildPath`, `navigate`, and typed links. */
  name: RouteName;
  /** Canonical path pattern. `:name` segments are decoded into route params. */
  path: string;
  /** Human-readable title used for document titles and navigation. */
  title: string;
  /** True when the route cannot render without an open note. */
  requiresNote?: boolean;
}

/** Canonical, ordered route registry. Keep names and paths unique. */
export const ROUTES: readonly RouteDefinition[] = [
  { name: "home", path: "/", title: "Vault" },
  { name: "note", path: "/notes/:id", title: "Note", requiresNote: true },
  { name: "engagements", path: "/engagements", title: "Engagements" },
  {
    name: "engagement",
    path: "/engagements/:id",
    title: "Engagement",
    requiresNote: true,
  },
  {
    name: "finding",
    path: "/findings/:id",
    title: "Finding",
    requiresNote: true,
  },
  { name: "search", path: "/search", title: "Search" },
  { name: "reports", path: "/reports", title: "Reports" },
  { name: "settings", path: "/settings", title: "Settings" },
];

/** Fallback route for unknown or malformed paths. */
export const NOT_FOUND_ROUTE: RouteDefinition = {
  name: "not-found",
  path: "*",
  title: "Not found",
  requiresNote: false,
};

/** Every route, including the not-found fallback. */
export const ROUTE_REGISTRY: readonly RouteDefinition[] = [
  ...ROUTES,
  NOT_FOUND_ROUTE,
];

export function routeByName(name: RouteName): RouteDefinition | undefined {
  return ROUTE_REGISTRY.find((route) => route.name === name);
}

/** Resolve a route title from a name, definition, or empty value. */
export function routeTitle(
  route: RouteName | RouteDefinition | null | undefined,
): string {
  if (!route) return NOT_FOUND_ROUTE.title;
  if (typeof route === "string") {
    return routeByName(route)?.title ?? NOT_FOUND_ROUTE.title;
  }
  return route.title;
}
