import { DIRECTION_LABEL } from "../config";
import { matchLocale } from "../pure";
import type { A11yDirection, LocaleOption, ResolvedDirection } from "../types";

export interface LocalePickerProps {
  locales: readonly LocaleOption[];
  value: string;
  direction: A11yDirection;
  onChange: (locale: string) => void;
  onDirectionChange: (direction: A11yDirection) => void;
  resolvedDirection: ResolvedDirection;
}

export function LocalePicker({
  locales,
  value,
  direction,
  onChange,
  onDirectionChange,
  resolvedDirection,
}: LocalePickerProps) {
  const selected = matchLocale(
    value,
    locales.map((locale) => locale.value),
  );
  return (
    <section className="a11y-section" aria-labelledby="a11y-locale-title">
      <h3 id="a11y-locale-title">Language and direction</h3>
      <label className="a11y-field">
        <span>Locale</span>
        <select
          value={selected}
          onChange={(event) => onChange(event.target.value)}
        >
          {locales.length === 0 ? (
            <option value={value}>{value}</option>
          ) : (
            locales.map((locale) => (
              <option key={locale.value} value={locale.value}>
                {locale.label} — {locale.native}
              </option>
            ))
          )}
        </select>
      </label>
      <label className="a11y-field">
        <span>Text direction</span>
        <select
          value={direction}
          onChange={(event) =>
            onDirectionChange(event.target.value as A11yDirection)
          }
        >
          <option value="auto">
            Automatic ({DIRECTION_LABEL[resolvedDirection]})
          </option>
          <option value="ltr">{DIRECTION_LABEL.ltr}</option>
          <option value="rtl">{DIRECTION_LABEL.rtl}</option>
        </select>
      </label>
    </section>
  );
}
