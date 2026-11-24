/** Public surface of the evidence-lab V3 feature. */

export { EvidenceLab, default } from "./EvidenceLab";
export type { EvidenceLabProps } from "./EvidenceLab";
export { EvidenceLabClient } from "./client";
export type {
  EvidenceLabClientOptions,
  HashResult,
  InspectOptions,
} from "./client";
export { ComparisonView } from "./components/ComparisonView";
export { CustodyTimeline } from "./components/CustodyTimeline";
export { HexViewer } from "./components/HexViewer";
export { IngestStrip } from "./components/IngestStrip";
export { StringsEntropyTabs } from "./components/StringsEntropyTabs";
export { sizeDeltaTotal, compareRows, changedDeltas } from "./compareModel";
export { custodyColumns, flattenTimeline, custodyIssues } from "./custodyModel";
export {
  badgeLabel,
  badgeTone,
  bytesToBase64,
  formatBytes,
  formatOffset,
  hexToBytes,
  maskHash,
  parseOffset,
  textToBase64,
} from "./format";
export {
  markSelection,
  navigateOffset,
  selectedByteCount,
  visibleRows,
} from "./hexModel";
export { createIngestItem, ingestCounts, validateDrop } from "./ingestModel";
export { initialLabState, labReducer } from "./state";
export { filterHits, stringTabs } from "./stringsModel";
export * from "./types";
