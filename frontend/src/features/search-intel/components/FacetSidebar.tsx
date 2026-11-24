/** Facet sidebar with counts and saved facet sets. */

import {
  facetDisplayCount,
  facetSelectionCount,
  selectedValues,
  sortFacetValues,
} from "../facets";
import { formatCount } from "../format";
import type { FacetResultV2, SavedFacetSetV2 } from "../types";

export interface FacetSidebarProps {
  facets: FacetResultV2[];
  selection: Record<string, string[]>;
  onToggle: (field: string, value: string) => void;
  onClear: () => void;
  facetSets?: SavedFacetSetV2[];
  activeSetId?: string;
  onApplySet?: (set: SavedFacetSetV2) => void;
}

export function FacetSidebar({
  facets,
  selection,
  onToggle,
  onClear,
  facetSets = [],
  activeSetId = "",
  onApplySet,
}: FacetSidebarProps) {
  const activeCount = facetSelectionCount(selection);
  return (
    <aside
      aria-label="Result facets"
      className="si-facets"
      data-testid="search-facet-sidebar"
    >
      <header className="si-facets__header">
        <h3>Facets</h3>
        {activeCount > 0 && (
          <button
            className="si-button si-button--link v3-focusable"
            data-testid="search-facets-clear"
            onClick={onClear}
            type="button"
          >
            Clear ({activeCount})
          </button>
        )}
      </header>
      {facetSets.length > 0 && (
        <div className="si-facets__sets">
          <span className="si-facets__label">Facet sets</span>
          {facetSets.map((set) => (
            <button
              aria-pressed={set.id === activeSetId}
              className="si-button si-button--chip v3-focusable"
              data-testid="search-facet-set"
              key={set.id}
              onClick={() => onApplySet?.(set)}
              type="button"
            >
              {set.name}
            </button>
          ))}
        </div>
      )}
      {facets.map((facet) => {
        const chosen = selectedValues(selection, facet.field);
        return (
          <section
            className="si-facets__group"
            data-field={facet.field}
            data-testid="search-facet-group"
            key={facet.field}
          >
            <h4>
              {facet.field.replace(/_/g, " ")}
              <span className="si-facets__sum">
                {formatCount(facetDisplayCount(facet))}
              </span>
            </h4>
            <ul>
              {sortFacetValues(facet).map((value) => (
                <li key={value.value}>
                  <button
                    aria-pressed={chosen.some(
                      (item) =>
                        item.toLowerCase() === value.value.toLowerCase(),
                    )}
                    className="si-facet v3-focusable"
                    data-selected={chosen.some(
                      (item) =>
                        item.toLowerCase() === value.value.toLowerCase(),
                    )}
                    data-testid="search-facet-value"
                    onClick={() => onToggle(facet.field, value.value)}
                    type="button"
                  >
                    <span className="si-facet__value">{value.value}</span>
                    <span className="si-facet__count">
                      {formatCount(value.count)}
                    </span>
                  </button>
                </li>
              ))}
              {facet.values.length === 0 && (
                <li className="si-facets__empty">No values</li>
              )}
            </ul>
          </section>
        );
      })}
      {facets.length === 0 && (
        <p className="si-facets__empty">Run a search to see facets.</p>
      )}
    </aside>
  );
}

export function facetSidebarSummary(facets: FacetResultV2[]): string {
  const values = facets.reduce(
    (total, facet) => total + facet.values.length,
    0,
  );
  return `${facets.length} facets · ${values} values`;
}
