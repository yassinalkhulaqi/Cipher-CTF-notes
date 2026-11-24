/** Design-system v3 showcase: tokens, kind colors, and density. */

import { V3Panel, V3Stat } from "../../../v3/components/V3Panel";
import { SHOWCASE_ENTRIES } from "../config";
import { kindColorToken, showcaseTokens } from "../pure";

export interface DesignSystemShowcaseProps {
  density: "comfortable" | "compact";
  onDensityChange: (value: "comfortable" | "compact") => void;
}

export function DesignSystemShowcase({
  density,
  onDensityChange,
}: DesignSystemShowcaseProps) {
  const tokens = showcaseTokens(SHOWCASE_ENTRIES);
  return (
    <V3Panel
      title="Design system v3"
      subtitle="Shared foundations only — no feature redefines a token"
      kind="section"
    >
      <div
        className="release-showcase"
        data-surface="design-system-showcase"
        data-density={density}
        aria-label="Design system showcase"
      >
        <div className="release-showcase__stats" data-role="showcase-stats">
          <V3Stat label="Tokens" value={tokens.length} hint="semantic + foundations" />
          <V3Stat label="Kinds" value={12} hint="with fallback" tone="good" />
          <V3Stat label="Density" value={density} hint="row height token" />
        </div>
        <div className="release-showcase__density" data-role="density-toggle">
          {(["comfortable", "compact"] as const).map((value) => (
            <button
              aria-label={`Use ${value} density`}
              aria-pressed={density === value}
              className="release-v3-focusable"
              data-action="set-density"
              data-density-value={value}
              key={value}
              onClick={() => onDensityChange(value)}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
        <ul className="release-showcase__tokens" data-role="token-list">
          {SHOWCASE_ENTRIES.map((entry) => (
            <li
              className="release-showcase__token"
              data-token={entry.token}
              data-kind={entry.kind}
              key={entry.token}
            >
              <span
                aria-hidden="true"
                className="release-showcase__swatch"
                style={{ background: kindColorToken(entry.kind) }}
              />
              <code>{entry.token}</code>
              <span>{entry.label}</span>
            </li>
          ))}
        </ul>
      </div>
    </V3Panel>
  );
}
