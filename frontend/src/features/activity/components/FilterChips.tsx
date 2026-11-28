/** Filter chip bar for the activity stream. */

import type { FacetCounts, FilterChipData, FilterValidation } from "../types";
import { facetChips, removeChip } from "../filters";

export interface FilterChipsProps {
  chips: FilterChipData[];
  facets: FacetCounts;
  validation: FilterValidation | null;
  onChange: (chips: FilterChipData[]) => void;
  onClear: () => void;
}

export function FilterChips({
  chips,
  facets,
  validation,
  onChange,
  onClear,
}: FilterChipsProps) {
  const suggestions = [
    ...facetChips(facets, "kinds", 5),
    ...facetChips(facets, "actors", 3),
    ...facetChips(facets, "severities", 3),
  ];
  return (
    <div className="activity-filters">
      <div
        className="activity-filters__active"
        role="group"
        aria-label="Active filters"
      >
        {chips.length === 0 && (
          <span className="activity-filters__empty">No filters</span>
        )}
        {chips.map((chip) => (
          <button
            key={chip.token}
            type="button"
            className="activity-chip activity-chip--active"
            data-operator={chip.operator}
            onClick={() => onChange(removeChip(chips, chip.token))}
            title={`Remove ${chip.token}`}
          >
            <span className="activity-chip__key">{chip.key}</span>
            <span className="activity-chip__value">{chip.label}</span>
            <span aria-hidden="true">×</span>
          </button>
        ))}
        {chips.length > 0 && (
          <button
            type="button"
            className="activity-filters__clear"
            onClick={onClear}
          >
            Clear
          </button>
        )}
      </div>
      <div
        className="activity-filters__suggestions"
        role="group"
        aria-label="Suggested filters"
      >
        {suggestions
          .filter(
            (chip) => !chips.some((active) => active.token === chip.token),
          )
          .map((chip) => (
            <button
              key={`suggestion-${chip.token}`}
              type="button"
              className="activity-chip"
              onClick={() => onChange([...chips, chip])}
            >
              + {chip.key}:{chip.label}
            </button>
          ))}
      </div>
      {validation && !validation.valid && (
        <ul className="activity-filters__errors">
          {validation.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
