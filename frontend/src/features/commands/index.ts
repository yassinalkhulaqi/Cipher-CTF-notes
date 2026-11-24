/** Public surface of the V3 command-center feature. */

export { ArgumentForm } from "./ArgumentForm";
export type { ArgumentFormProps } from "./ArgumentForm";
export { BreadcrumbTrail } from "./BreadcrumbTrail";
export type { BreadcrumbTrailProps } from "./BreadcrumbTrail";
export {
  CommandPaletteV3,
  invocationFor,
  useCommandBarHotkey,
} from "./CommandPaletteV3";
export type { CommandPaletteV3Props } from "./CommandPaletteV3";
export { CommandsClient } from "./client";
export type { ContextBody, ManifestData } from "./client";
export { FocusError, FocusManager, parseFocusStatus } from "./focus";
export {
  MAX_MACRO_STEPS,
  MacroError,
  MacroLibrary,
  MacroRecorder,
  expandMacro,
  macroStepsAsData,
} from "./macros";
export { NavigationGraph, defaultNavigation } from "./navigation";
export {
  ParseError,
  bindArguments,
  canonicalizeCommandId,
  parseCommand,
  parseSequence,
  renderCommand,
  tokenize,
  validateArgument,
} from "./parse";
export type { ParsedInput, Token } from "./parse";
export {
  contextWeight,
  groupHits,
  isCommandAvailable,
  normalize,
  rankCommands,
  scoreCommand,
  subsequenceRatio,
  tokenizeQuery,
} from "./scoring";
export type { CommandScore } from "./scoring";
export {
  clampSelection,
  flattenGroups,
  focusRestoreTarget,
  initialPaletteState,
  isCommandBarShortcut,
  paletteReducer,
} from "./state";
export type { PaletteAction, PaletteState } from "./state";
export type {
  ArgumentSpec,
  CommandContext,
  CommandEffect,
  CommandGroup,
  CommandGroupResult,
  CommandHit,
  CommandInvocation,
  CommandSpec,
  CommandStatus,
  FocusSession,
  FocusStatus,
  MacroRecord,
  MacroStep,
  NavNode,
  NavPath,
  PaneNode,
  PaneOrientation,
  PaneSpec,
  UsageEvent,
  WorkspaceSnapshot,
} from "./types";
export { UsageModel } from "./usage";
export {
  MemoryPanePersistence,
  WorkspaceError,
  WorkspaceModel,
  branch,
  findPane,
  insertPane,
  leaf,
  leaves,
  makePane,
  nodeAt,
  paneNodeFromData,
  parseOrientation,
  paths,
  removePane,
  resizePane,
  updatePane,
} from "./workspace";
export type { PanePersistence } from "./workspace";
export { FocusOverlay } from "./FocusOverlay";
export type { FocusOverlayProps } from "./FocusOverlay";
export { PaneHeader } from "./PaneHeader";
export type { PaneHeaderProps } from "./PaneHeader";
export { WorkspaceCanvas } from "./WorkspaceCanvas";
export type { WorkspaceCanvasProps } from "./WorkspaceCanvas";
