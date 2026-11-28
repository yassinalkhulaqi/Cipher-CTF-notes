/** RTL pane preview with logical region ordering and mirrored icons. */

import type { CSSProperties } from "react";

import { layoutFor, validateLayout } from "./rtl";
import type { PaneLayoutView } from "./types";
import { V3Panel } from "../../v3/components/V3Panel";

export interface RtlLayoutPaneProps {
  locale: string;
  pane: string;
  override?: string;
  onRegion?: (region: string) => void;
}

export function RtlLayoutPane({
  locale,
  pane,
  override,
  onRegion,
}: RtlLayoutPaneProps) {
  const layout: PaneLayoutView = layoutFor(pane, locale, override);
  const validation = validateLayout(layout);
  const icons = layout.mirror_icons;

  return (
    <section
      className="a11y-refine__rtl-pane"
      data-dir={layout.direction}
      data-pane={pane}
      data-valid={validation.valid}
      style={
        {
          "--v3-inline-start": layout.sides.start,
          "--v3-inline-end": layout.sides.end,
        } as CSSProperties
      }
      aria-label={`${pane} layout, ${layout.direction}`}
    >
      <header className="a11y-refine__rtl-head">
        <V3Panel
          title={pane}
          subtitle={`${layout.direction} · ${layout.css_class}`}
          density="compact"
        >
          <span className="a11y-refine__sr-only">
            {layout.direction === "rtl"
              ? "Right to left layout"
              : "Left to right layout"}
          </span>
        </V3Panel>
      </header>
      <ol className="a11y-refine__regions" aria-label="Logical pane regions">
        {layout.ordered_regions.map((region) => (
          <li key={region} data-region={region}>
            <button type="button" onClick={() => onRegion?.(region)}>
              {region}
            </button>
          </li>
        ))}
      </ol>
      <footer className="a11y-refine__rtl-icons" aria-label="Mirrored icons">
        {icons.length ? (
          icons.map((icon) => (
            <span
              key={icon}
              data-icon={icon}
              data-mirror="true"
              aria-hidden="true"
            >
              {icon}
            </span>
          ))
        ) : (
          <span data-mirror="false">no mirrored icons</span>
        )}
      </footer>
    </section>
  );
}
