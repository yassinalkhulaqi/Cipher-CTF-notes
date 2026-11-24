/** Cluster groups rendered as selectable summary tiles. */

import { clusterSummary, clusterTone } from "../clusters";
import { formatCount } from "../format";
import type { ClusterGroupV2 } from "../types";

export interface ClusterGroupsProps {
  clusters: ClusterGroupV2[];
  activeKey?: string;
  onSelect?: (cluster: ClusterGroupV2) => void;
}

export function ClusterGroups({
  clusters,
  activeKey = "",
  onSelect,
}: ClusterGroupsProps) {
  if (!clusters.length) return null;
  return (
    <section
      aria-label="Result clusters"
      className="si-clusters"
      data-testid="search-clusters"
    >
      <h3>Clusters</h3>
      <div className="si-clusters__list">
        {clusters.map((cluster) => (
          <button
            aria-label={clusterSummary(cluster)}
            aria-pressed={cluster.key === activeKey}
            className="si-cluster v3-focusable"
            data-key={cluster.key}
            data-tone={clusterTone(cluster.key)}
            data-testid="search-cluster"
            key={cluster.key}
            onClick={() => onSelect?.(cluster)}
            type="button"
          >
            <span className="si-cluster__label">{cluster.label}</span>
            <span className="si-cluster__count">
              {formatCount(cluster.count)}
            </span>
            <span className="si-cluster__score">
              {cluster.score.toFixed(1)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
