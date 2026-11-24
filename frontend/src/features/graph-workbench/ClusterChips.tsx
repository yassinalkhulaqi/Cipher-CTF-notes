/** Cluster chips with dimension selection and deterministic colors. */

import type { CSSProperties } from "react";

import type { Chip, ClusterDimension } from "./types";
import { CLUSTER_DIMENSIONS, CLUSTER_LABELS } from "./types";

export interface ClusterChipsProps {
  chips: Chip[];
  selected: string;
  dimension: ClusterDimension;
  onSelect: (key: string) => void;
  onDimension: (dimension: ClusterDimension) => void;
}

export function ClusterChips({
  chips,
  selected,
  dimension,
  onSelect,
  onDimension,
}: ClusterChipsProps) {
  return (
    <div
      className="gw-clusters"
      data-testid="gw-cluster-chips"
      data-selected={selected}
    >
      <div
        className="gw-clusters__dimensions"
        role="group"
        aria-label="Cluster dimension"
      >
        {CLUSTER_DIMENSIONS.map((item) => (
          <button
            key={item}
            type="button"
            className="gw-dimension"
            data-active={item === dimension}
            aria-pressed={item === dimension}
            onClick={() => onDimension(item)}
          >
            {CLUSTER_LABELS[item]}
          </button>
        ))}
      </div>
      <div className="gw-clusters__chips" data-testid="gw-cluster-chip-list">
        {chips.length === 0 ? (
          <span className="gw-empty">No clusters for this dimension.</span>
        ) : (
          chips.map((chip) => (
            <button
              key={`${chip.dimension}:${chip.key}`}
              type="button"
              className="gw-chip"
              data-cluster={chip.key}
              data-selected={chip.selected}
              style={{ "--gw-chip-color": chip.color } as CSSProperties}
              aria-pressed={chip.selected}
              onClick={() => onSelect(chip.selected ? "" : chip.key)}
            >
              <span className="gw-chip__dot" aria-hidden="true" />
              <span className="gw-chip__label">{chip.label}</span>
              <span className="gw-chip__count">{chip.count}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
