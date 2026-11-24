/** Public surface of the search-intel feature. */

export { SearchIntelFeature, default } from "./SearchIntelFeature";
export type { SearchIntelFeatureProps } from "./SearchIntelFeature";
export {
  MAX_QUERY_LENGTH,
  allClauses,
  completeQuery,
  describeParsedQuery,
  fieldHint,
  foldValue,
  formatClause,
  parseDateBoundary,
  parseQueryV2,
  queryFingerprint,
  serializeQueryV2,
  tokenizeV2,
  validateQueryText,
} from "./query";
export type { CompletionOptions } from "./query";
export {
  clearFacets,
  facetSelectionCount,
  facetSetFields,
  mergeFacetResult,
  selectedValues,
  selectionFromQuery,
  selectionToQuery,
  sortFacetValues,
  toggleFacetValue,
} from "./facets";
export {
  clusterSummary,
  clusterTone,
  groupHitsByCluster,
  largestCluster,
  totalClusterCount,
  ungroupedHits,
} from "./clusters";
export {
  groupPivotsByRole,
  pivotChipLabel,
  pivotDestinationCounts,
  pivotQuery,
  roleLabel,
  roleTone,
  topPivots,
} from "./pivots";
export {
  draftFromSaved,
  filterSaved,
  isDirty,
  mergeSaved,
  normalizeDraft,
  savedSummary,
  savedTags,
  sortSaved,
  validateDraft,
} from "./saved";
export type { DraftValidation } from "./saved";
export {
  formatCount,
  formatScore,
  kindLabel,
  relativeTime,
  severityTone,
} from "./format";
export { fragmentPreview, splitFragment } from "./highlight";
export type { FragmentChunk } from "./highlight";
export { createSearchIntelClient, SearchIntelClient } from "./client";
export type { SearchIntelRequest } from "./client";
export { QueryBuilder } from "./components/QueryBuilder";
export { FacetSidebar } from "./components/FacetSidebar";
export { ClusterGroups } from "./components/ClusterGroups";
export { PivotChips } from "./components/PivotChips";
export { ResultList } from "./components/ResultList";
export { SavedSearchManager } from "./components/SavedSearchManager";
export * from "./types";
