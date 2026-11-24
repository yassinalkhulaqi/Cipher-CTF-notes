/** Locale picker with direction, coverage, and catalog metadata. */

import { additionalLocaleOptions, catalogKeys, coverage, localeDirection } from "./catalogs";
import type { LocaleOptionView } from "./types";
import { V3Panel } from "../../v3/components/V3Panel";

export interface LocaleCatalogPickerProps {
  locales?: LocaleOptionView[];
  value: string;
  onChange?: (locale: string) => void;
}

export function LocaleCatalogPicker({
  locales = additionalLocaleOptions(),
  value,
  onChange,
}: LocaleCatalogPickerProps) {
  const options = [...locales].sort((first, second) => first.value.localeCompare(second.value));
  const selected = options.find((option) => option.value === value);
  const direction = localeDirection(value);
  const percent = coverage(value);

  return (
    <V3Panel
      title="Locale"
      subtitle={selected?.native_name ?? value}
      density="compact"
      actions={<span className="a11y-refine__badge" data-dir={direction}>{direction}</span>}
    >
      <div className="a11y-refine__locale">
        <label htmlFor="a11y-refine-locale">Language</label>
        <select
          id="a11y-refine-locale"
          value={value}
          dir={direction}
          onChange={(event) => onChange?.(event.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value} dir={option.direction}>
              {option.native_name} ({option.value})
            </option>
          ))}
        </select>
        <dl className="a11y-refine__locale-meta">
          <dt>Catalog keys</dt>
          <dd>{catalogKeys().length}</dd>
          <dt>Coverage</dt>
          <dd>{percent}%</dd>
          <dt>Script</dt>
          <dd>{selected?.script ?? "Latn"}</dd>
        </dl>
        <p className="a11y-refine__hint" role="status">
          {direction === "rtl" ? "Panels mirror automatically." : "Panels use left-to-right order."}
        </p>
      </div>
    </V3Panel>
  );
}
