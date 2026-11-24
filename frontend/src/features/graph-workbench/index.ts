/** Public surface of the V3 graph workbench feature. */

import { registerFeature } from "../../v3/registry";

export { GraphWorkbench, default } from "./GraphWorkbench";
export type { GraphWorkbenchProps } from "./GraphWorkbench";
export { ClusterChips } from "./ClusterChips";
export type { ClusterChipsProps } from "./ClusterChips";
export { LayoutSwitcher } from "./LayoutSwitcher";
export type { LayoutSwitcherProps } from "./LayoutSwitcher";
export { PathExplorer } from "./PathExplorer";
export type { PathExplorerProps } from "./PathExplorer";
export { RelationshipPanel } from "./RelationshipPanel";
export type { RelationshipPanelProps } from "./RelationshipPanel";
export { WorkbenchInspector } from "./WorkbenchInspector";
export type { WorkbenchInspectorProps } from "./WorkbenchInspector";
export { WorkbenchMinimap } from "./WorkbenchMinimap";
export type { WorkbenchMinimapProps } from "./WorkbenchMinimap";
export { GraphWorkbenchClient } from "./client";
export type { GraphWorkbenchClientOptions, OverviewResult } from "./client";
export {
  applyLocalEdge,
  canCommit,
  cancelGesture,
  commitGesture,
  describeGesture,
  draftToBody,
  draftToEdge,
  historySummary,
  initialGesture,
  initialHistory,
  invertEdge,
  pushEdit,
  redoEdit,
  removeLocalEdge,
  selectNode,
  setGestureKind,
  setGestureLabel,
  setGestureWeight,
  undoEdit,
  validateDraft,
} from "./editor";
export type { GesturePhase, GestureState, HistoryState } from "./editor";
export {
  buildAdjacency,
  adjacencyKeys,
  bridgeList,
  connectedComponents,
  articulationPoints,
  cutVertexSummary,
  neighborhood,
  nodeLabel,
  pathSummary,
  shortestPath,
  stepTone,
  structuralSummary,
} from "./analysis";
export type { Adjacency } from "./analysis";
export {
  buildClusters,
  clusterCentroids,
  clusterChips,
  clusterColor,
  clusterOf,
  clusterSummary,
  filterByCluster,
  isClusterDimension,
  primaryKey,
} from "./clusters";
export {
  SeededRandom,
  computeLayout,
  createRandom,
  forceLayout,
  hierarchicalLayout,
  hubOf,
  layoutSignature,
  normalizePositions,
  radialLayout,
  stableHash,
  timelineLayout,
} from "./layout";
export {
  boundsOf,
  centroid,
  clamp,
  constrainViewport,
  distance,
  edgeKey,
  fitScale,
  fitViewport,
  graphBounds,
  identityViewport,
  lerp,
  minimapRect,
  nearestEdge,
  nearestNode,
  normalize,
  panViewport,
  pointToSegment,
  roundPoint,
  screenToWorld,
  smoothstep,
  worldToScreen,
  zoomAt,
} from "./geometry";
export type { Bounds } from "./geometry";
export {
  centerViewportAt,
  clusterDots,
  minimapBounds,
  minimapCoverage,
  minimapNodes,
  minimapToWorld,
  minimapTransform,
  projectToMinimap,
  viewportRect,
} from "./minimap";
export type { MinimapTransform, Rect } from "./minimap";
export {
  buildInspector,
  clusterMemberships,
  formatMetadata,
  formatTimestamp,
  formatValue,
  groupNeighbors,
  inspectorSections,
  inspectorTitle,
  severityColor,
  severityTone,
  truncateLabel,
} from "./inspector";
export type { EntityDetail, InspectorExtra } from "./inspector";
export * from "./types";

export function registerGraphWorkbench(): void {
  registerFeature({
    id: "v3-graph-workbench",
    label: "Graph workbench",
    route: "/graph-workbench",
    order: 40,
    capability: "graph",
    icon: "share-2",
  });
}
