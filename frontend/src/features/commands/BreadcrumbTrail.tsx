/** Breadcrumb trail rendered from the navigation graph. */

import type { NavNode } from "./types";

export interface BreadcrumbTrailProps {
  crumbs: NavNode[];
  current?: string;
  onNavigate?: (node: NavNode) => void;
  compact?: boolean;
}

export function BreadcrumbTrail({
  crumbs,
  current,
  onNavigate,
  compact = false,
}: BreadcrumbTrailProps) {
  return (
    <nav
      className="v3c-crumbs"
      aria-label="Command navigation breadcrumb"
      data-compact={compact}
    >
      {crumbs.map((crumb, index) => (
        <span className="v3c-crumb" key={crumb.id}>
          {index > 0 && (
            <span className="v3c-crumb__sep" aria-hidden="true">
              /
            </span>
          )}
          <button
            type="button"
            className="v3c-crumb__link"
            data-testid={`crumb-${crumb.id}`}
            aria-label={`Navigate to ${crumb.label}`}
            onClick={() => onNavigate?.(crumb)}
          >
            {crumb.label}
          </button>
        </span>
      ))}
      {current && (
        <span className="v3c-crumb v3c-crumb--current" aria-current="page">
          <span className="v3c-crumb__sep" aria-hidden="true">
            /
          </span>
          {current}
        </span>
      )}
    </nav>
  );
}
