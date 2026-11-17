import type { ReactNode } from "react";
import { cx } from "../lib/ux";

export interface AppShellProps {
  brand?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  nav?: ReactNode;
  navLabel?: string;
  headerActions?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  mainId?: string;
}

/**
 * Additive, accessible application shell. It is intentionally not mounted by
 * `App.tsx`; later v2 routes can compose it without changing current runtime.
 */
export function AppShell({
  brand,
  title,
  subtitle,
  nav,
  navLabel = "Primary",
  headerActions,
  aside,
  children,
  footer,
  className,
  mainId = "main-content",
}: AppShellProps) {
  return (
    <>
      <a className="ui-skip-link" href={`#${mainId}`}>
        Skip to content
      </a>
      <div className={cx("ui-app-shell", className)}>
        <header className="ui-app-shell__header">
          <div className="ui-app-shell__brand">
            {brand}
            {title ? (
              <span className="ui-app-shell__title">{title}</span>
            ) : null}
            {subtitle ? (
              <span className="ui-app-shell__subtitle">{subtitle}</span>
            ) : null}
          </div>
          {headerActions ? (
            <div className="ui-app-shell__actions">{headerActions}</div>
          ) : null}
        </header>
        <div className="ui-app-shell__body">
          {aside ? (
            <aside className="ui-app-shell__aside" aria-label="Context">
              {aside}
            </aside>
          ) : null}
          {nav ? (
            <nav className="ui-app-shell__nav" aria-label={navLabel}>
              {nav}
            </nav>
          ) : null}
          <main
            id={mainId}
            className="ui-app-shell__main"
            tabIndex={-1}
            aria-label="Main content"
          >
            {children}
          </main>
        </div>
        {footer ? (
          <footer className="ui-app-shell__footer">{footer}</footer>
        ) : null}
      </div>
    </>
  );
}
