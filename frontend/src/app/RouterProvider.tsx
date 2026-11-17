import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { currentRoute, subscribe, type RouteMatch } from "../lib/router";

const RouterContext = createContext<RouteMatch | null>(null);

export interface RouterProviderProps {
  children: ReactNode;
  /** Override the initial route, primarily for tests and SSR. */
  initialRoute?: RouteMatch;
}

/**
 * Provides the active hash route to the tree. `currentRoute()` is only called
 * during render/effects, so importing this module is safe without `window`.
 */
export function RouterProvider({
  children,
  initialRoute,
}: RouterProviderProps) {
  const [route, setRoute] = useState<RouteMatch>(
    () => initialRoute ?? currentRoute(),
  );

  useEffect(() => subscribe(setRoute), []);

  return (
    <RouterContext.Provider value={route}>{children}</RouterContext.Provider>
  );
}

export function useRoute(): RouteMatch {
  const route = useContext(RouterContext);
  if (!route) {
    throw new Error("useRoute must be used inside a RouterProvider");
  }
  return route;
}

export { RouterContext };
