/** One unified theme, motion, density, and contrast control. */

import { useState, type CSSProperties } from "react";

import { translate } from "./catalogs";
import {
  DEFAULT_APPEARANCE,
  appearanceCss,
  clampScale,
  motionEquivalence,
} from "./preferences";
import type { MotionMode, UnifiedAppearanceView } from "./types";
import { V3Panel } from "../../v3/components/V3Panel";

export interface UnifiedAppearanceControlProps {
  appearance?: UnifiedAppearanceView;
  locale?: string;
  themes?: string[];
  onChange?: (appearance: UnifiedAppearanceView) => void;
}

const MOTIONS: MotionMode[] = ["full", "reduced", "off"];

export function UnifiedAppearanceControl({
  appearance = DEFAULT_APPEARANCE,
  locale = "en",
  themes = ["graphite", "light", "midnight", "high-contrast"],
  onChange,
}: UnifiedAppearanceControlProps) {
  const [draft, setDraft] = useState<UnifiedAppearanceView>(appearance);
  const css = appearanceCss(draft);
  const motion = motionEquivalence(draft.motion);

  const update = (patch: Partial<UnifiedAppearanceView>): void => {
    const next = { ...draft, ...patch };
    setDraft(next);
    onChange?.(next);
  };

  return (
    <V3Panel
      title="Appearance"
      subtitle={`theme ${draft.theme} · motion ${draft.motion}`}
      actions={
        <span className="a11y-refine__badge" data-motion={draft.motion}>
          {draft.motion}
        </span>
      }
    >
      <div className="a11y-refine__appearance" data-density={draft.density} style={
        {
          "--v3-theme": css["--v3-theme"],
          "--v3-motion-normal": css["--v3-motion-normal"],
        } as CSSProperties
      }>
        <div className="a11y-refine__field">
          <label htmlFor="a11y-refine-theme">Theme</label>
          <select
            id="a11y-refine-theme"
            value={draft.theme}
            onChange={(event) => update({ theme: event.target.value })}
          >
            {themes.map((theme) => (
              <option key={theme} value={theme}>
                {theme}
              </option>
            ))}
          </select>
          <span className="a11y-refine__sr-only">
            {translate(locale, "v3.theme.changed", { theme: draft.theme }).message}
          </span>
        </div>
        <fieldset className="a11y-refine__field">
          <legend>Motion</legend>
          <div className="a11y-refine__segmented" role="group" aria-label="Motion mode">
            {MOTIONS.map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={draft.motion === mode}
                data-active={draft.motion === mode}
                onClick={() => update({ motion: mode })}
              >
                {mode}
              </button>
            ))}
          </div>
          <span className="a11y-refine__hint" role="status">
            {motion.contentHidden ? "content hidden" : "content visible"} · focus preserved
          </span>
        </fieldset>
        <div className="a11y-refine__field">
          <label htmlFor="a11y-refine-scale">Text scale ({draft.font_scale.toFixed(2)})</label>
          <input
            id="a11y-refine-scale"
            type="range"
            min={0.75}
            max={1.75}
            step={0.05}
            value={draft.font_scale}
            onChange={(event) => update({ font_scale: clampScale(Number(event.target.value)) })}
            aria-valuetext={`${Math.round(draft.font_scale * 100)} percent`}
          />
        </div>
        <div className="a11y-refine__checks">
          <label>
            <input
              type="checkbox"
              checked={draft.high_contrast}
              onChange={(event) => update({ high_contrast: event.target.checked })}
            />
            High contrast
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.focus_ring_boost}
              onChange={(event) => update({ focus_ring_boost: event.target.checked })}
            />
            Stronger focus ring
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.density === "compact"}
              onChange={(event) =>
                update({ density: event.target.checked ? "compact" : "comfortable" })
              }
            />
            Compact density
          </label>
        </div>
      </div>
    </V3Panel>
  );
}
