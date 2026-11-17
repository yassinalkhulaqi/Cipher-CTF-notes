import {
  NOT_FOUND_ROUTE,
  ROUTES,
  routeByName,
  type RouteDefinition,
  type RouteName,
} from "../app/routes";

export type RouteParams = Record<string, string>;

export interface ParsedLocation {
  path: string;
  search: string;
  hash: string;
  query: URLSearchParams;
}

export interface RouteMatch {
  name: RouteName;
  params: RouteParams;
  path: string;
  title: string;
  requiresNote: boolean;
  route: RouteDefinition;
}

export interface NavigateOptions {
  replace?: boolean;
}

export type RouteListener = (route: RouteMatch) => void;

function normalizePath(path: string): string {
  let next = path.trim();
  if (!next) return "/";
  if (!next.startsWith("/")) next = `/${next}`;
  next = next.replace(/\/{2,}/g, "/");
  if (next.length > 1) next = next.replace(/\/+$/, "");
  return next || "/";
}

function decodeParam(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

/**
 * Parse a location hash such as `#/notes/12?tab=preview`.
 * Encoded path separators stay encoded until a route param is matched.
 */
export function parseLocation(hash: string): ParsedLocation {
  let raw = typeof hash === "string" ? hash.trim() : "";
  while (raw.startsWith("#")) raw = raw.slice(1);
  const question = raw.indexOf("?");
  const rawPath = question >= 0 ? raw.slice(0, question) : raw;
  const search = question >= 0 ? raw.slice(question + 1) : "";
  const path = normalizePath(rawPath);
  return {
    path,
    search,
    hash: `#${path}${search ? `?${search}` : ""}`,
    query: new URLSearchParams(search),
  };
}

function makeMatch(
  route: RouteDefinition,
  params: RouteParams,
  path: string,
): RouteMatch {
  return {
    name: route.name,
    params,
    path,
    title: route.title,
    requiresNote: route.requiresNote === true,
    route,
  };
}

/**
 * Match a typed route definition (or route name) against a path.
 * Returns `null` for a shape mismatch, a missing param, or malformed encoding.
 */
export function matchRoute(
  route: RouteDefinition | RouteName,
  path: string,
): RouteMatch | null {
  const definition = typeof route === "string" ? routeByName(route) : route;
  if (!definition) return null;

  const location = parseLocation(path.startsWith("#") ? path : `#${path}`);
  const target = location.path;

  if (definition.path === "*") {
    return makeMatch(definition, {}, target);
  }

  const patternSegments = definition.path.split("/").filter(Boolean);
  const pathSegments = target.split("/").filter(Boolean);
  if (patternSegments.length !== pathSegments.length) return null;

  const params: RouteParams = {};
  for (let index = 0; index < patternSegments.length; index += 1) {
    const pattern = patternSegments[index];
    const segment = pathSegments[index];
    if (pattern.startsWith(":")) {
      const key = pattern.slice(1);
      if (!key) return null;
      const decoded = decodeParam(segment);
      if (decoded === null || decoded === "") return null;
      params[key] = decoded;
    } else if (pattern !== segment) {
      return null;
    }
  }

  return makeMatch(definition, params, target);
}

/** Resolve any path to a known route, falling back to not-found. */
export function resolvePath(path: string): RouteMatch {
  const normalized = parseLocation(
    path.startsWith("#") ? path : `#${path}`,
  ).path;
  for (const route of ROUTES) {
    const match = matchRoute(route, normalized);
    if (match) return match;
  }
  const fallback = matchRoute(NOT_FOUND_ROUTE, normalized);
  if (!fallback) {
    throw new Error(`Cannot resolve fallback route for ${normalized}`);
  }
  return fallback;
}

/** Build an encoded path for a named route and its params. */
export function buildPath(
  name: RouteName,
  params: Record<string, string | number> = {},
): string {
  const route = routeByName(name);
  if (!route || route.path === "*") {
    throw new Error(`Unknown route: ${name}`);
  }

  const segments = route.path
    .split("/")
    .filter(Boolean)
    .map((segment) => {
      if (!segment.startsWith(":")) return segment;
      const key = segment.slice(1);
      const value = params[key];
      if (value === undefined || value === null || `${value}` === "") {
        throw new Error(`Missing route param: ${key}`);
      }
      return encodeURIComponent(String(value));
    });

  return segments.length ? `/${segments.join("/")}` : "/";
}

/** Read the current route. Safe when called without a browser (`window`). */
export function currentRoute(): RouteMatch {
  if (typeof window === "undefined") return resolvePath("/");
  return resolvePath(window.location.hash);
}

const listeners = new Set<RouteListener>();
let listening = false;

function emit(): void {
  const route = currentRoute();
  listeners.forEach((listener) => {
    try {
      listener(route);
    } catch {
      // A single broken subscriber must not break navigation for the rest.
    }
  });
}

function onLocationChange(): void {
  emit();
}

function startListening(): void {
  if (listening || typeof window === "undefined") return;
  window.addEventListener("hashchange", onLocationChange);
  window.addEventListener("popstate", onLocationChange);
  listening = true;
}

function stopListening(): void {
  if (!listening || typeof window === "undefined") return;
  window.removeEventListener("hashchange", onLocationChange);
  window.removeEventListener("popstate", onLocationChange);
  listening = false;
}

/** Subscribe to route changes. Returns an unsubscribe function. */
export function subscribe(listener: RouteListener): () => void {
  listeners.add(listener);
  startListening();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) stopListening();
  };
}

/**
 * Navigate to a named route using the History API.
 * Returns the built path even when no browser is present.
 */
export function navigate(
  name: RouteName,
  params: Record<string, string | number> = {},
  options: NavigateOptions = {},
): string {
  const path = buildPath(name, params);
  if (typeof window === "undefined") return path;

  const hash = `#${path}`;
  const url = `${window.location.pathname}${window.location.search}${hash}`;
  if (window.location.hash === hash) {
    emit();
    return path;
  }

  if (options.replace) {
    window.history.replaceState(null, "", url);
  } else {
    window.history.pushState(null, "", url);
  }
  emit();
  return path;
}
