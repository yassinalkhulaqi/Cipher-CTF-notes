/** Controller hook that binds the pure automation logic to the V3 API. */

import { useCallback, useMemo, useState } from "react";
import type { V3Client } from "../../v3/apiClient";
import { AutomationClient } from "./client";
import { compileDag, connectSteps } from "./dag";
import { validateVariableValues } from "./variables";
import type {
  DagCompilation,
  DiffEntry,
  DryRunTrace,
  Playbook,
  RecurrenceRule,
  RunRecord,
  StepDef,
  StepKind,
  TimelineItem,
  ValidationIssue,
} from "./types";
import { DEFAULT_RULE, expand, humanize } from "./recurrence";

export interface AutomationController {
  client: AutomationClient;
  playbook: Playbook;
  values: Record<string, unknown>;
  trace: DryRunTrace | null;
  timeline: TimelineItem[];
  runs: RunRecord[];
  selectedRunId: string;
  selectedRun: RunRecord | null;
  diff: DiffEntry[];
  replayOk: boolean | null;
  rollbackOk: boolean | null;
  recurrence: RecurrenceRule;
  occurrences: number[];
  issue: ValidationIssue | null;
  error: string;
  busy: boolean;
  dag: DagCompilation;
  setValue: (key: string, value: unknown) => void;
  addStep: () => void;
  updateStep: (id: string, changes: Partial<StepDef>) => void;
  removeStep: (id: string) => void;
  connect: (source: string, target: string) => void;
  setRule: (changes: Partial<RecurrenceRule>) => void;
  dryRun: () => Promise<void>;
  execute: () => Promise<void>;
  refreshRuns: () => Promise<void>;
  selectRun: (id: string) => Promise<void>;
  replaySelected: () => Promise<void>;
  rollbackSelected: () => Promise<void>;
  planRecurrence: (after: number, before: number) => void;
  clearIssue: () => void;
}

const STARTER_PLAYBOOK: Playbook = {
  id: "new-playbook",
  title: "New playbook",
  description: "Documentation-only automation",
  version: 1,
  tags: [],
  variables: [],
  steps: [
    {
      id: "collect",
      title: "Capture notes",
      kind: "create_note",
      depends_on: [],
      inputs: { title: "Investigation notes" },
    },
    {
      id: "record",
      title: "Record finding",
      kind: "create_finding",
      depends_on: ["collect"],
      inputs: { title: "Finding", severity: "medium" },
    },
  ],
  recurrence: null,
};

export function useAutomation(v3Client?: V3Client): AutomationController {
  const [client] = useState(() => new AutomationClient({ client: v3Client }));
  const [playbook, setPlaybook] = useState<Playbook>(STARTER_PLAYBOOK);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [trace, setTrace] = useState<DryRunTrace | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [diff, setDiff] = useState<DiffEntry[]>([]);
  const [replayOk, setReplayOk] = useState<boolean | null>(null);
  const [rollbackOk, setRollbackOk] = useState<boolean | null>(null);
  const [recurrence, setRecurrenceState] =
    useState<RecurrenceRule>(DEFAULT_RULE);
  const [occurrences, setOccurrences] = useState<number[]>([]);
  const [issue, setIssue] = useState<ValidationIssue | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const dag = useMemo(() => compileDag(playbook.steps), [playbook.steps]);
  const resolution = useMemo(
    () => validateVariableValues(playbook.variables, values),
    [playbook.variables, values],
  );
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );

  const setValue = useCallback((key: string, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value }));
  }, []);

  const addStep = useCallback(() => {
    setPlaybook((current) => {
      const index = current.steps.length + 1;
      const id = `step_${index}`;
      const previous = current.steps[current.steps.length - 1]?.id;
      const step: StepDef = {
        id,
        title: `Step ${index}`,
        kind: "create_note" as StepKind,
        depends_on: previous ? [previous] : [],
        inputs: { title: `Note ${index}` },
      };
      return {
        ...current,
        steps: [...current.steps, step],
        version: current.version + 1,
      };
    });
  }, []);

  const updateStep = useCallback((id: string, changes: Partial<StepDef>) => {
    setPlaybook((current) => ({
      ...current,
      steps: current.steps.map((step) =>
        step.id === id ? { ...step, ...changes } : step,
      ),
      version: current.version + 1,
    }));
  }, []);

  const removeStep = useCallback((id: string) => {
    setPlaybook((current) => ({
      ...current,
      steps: current.steps
        .filter((step) => step.id !== id)
        .map((step) => ({
          ...step,
          depends_on: (step.depends_on ?? []).filter((value) => value !== id),
        })),
      version: current.version + 1,
    }));
  }, []);

  const connect = useCallback(
    (source: string, target: string) => {
      const result = connectSteps(playbook.steps, source, target);
      if (!result.accepted) {
        setIssue(result.problem);
        return;
      }
      setIssue(null);
      setPlaybook((current) => ({
        ...current,
        steps: result.steps,
        version: current.version + 1,
      }));
    },
    [playbook.steps],
  );

  const runGuarded = useCallback(
    async <T>(action: () => Promise<T>): Promise<T | null> => {
      if (!dag.ok || !resolution.ok) {
        setError("Resolve the DAG and variable issues before running");
        return null;
      }
      setBusy(true);
      setError("");
      try {
        return await action();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [dag.ok, resolution.ok],
  );

  const dryRun = useCallback(async () => {
    const result = await runGuarded(() => client.dryRun(playbook, values));
    if (!result) return;
    setTrace(result.trace);
    setTimeline(result.timeline);
  }, [client, playbook, values, runGuarded]);

  const refreshRuns = useCallback(async () => {
    const result = await runGuarded(() =>
      client.runs(`playbook:${playbook.id}`),
    );
    if (result) setRuns(result.runs);
  }, [client, playbook.id, runGuarded]);

  const execute = useCallback(async () => {
    const result = await runGuarded(() => client.run(playbook, values));
    if (!result) return;
    await refreshRuns();
    setSelectedRunId(result.run.id);
    setTrace(null);
  }, [client, playbook, values, runGuarded, refreshRuns]);

  const selectRun = useCallback(
    async (id: string) => {
      setSelectedRunId(id);
      setReplayOk(null);
      setRollbackOk(null);
      const result = await runGuarded(() => client.runGet(id));
      if (!result) return;
      setTimeline(result.timeline);
      const index = runs.findIndex((run) => run.id === id);
      const neighbor = runs[index + 1];
      if (neighbor) {
        const comparison = await runGuarded(() => client.diff(id, neighbor.id));
        if (comparison) setDiff(comparison.differences);
      } else {
        setDiff([]);
      }
    },
    [client, runs, runGuarded],
  );

  const replaySelected = useCallback(async () => {
    if (!selectedRunId) return;
    const result = await runGuarded(() => client.replay(selectedRunId));
    if (result) setReplayOk(result.replay.deterministic);
  }, [client, selectedRunId, runGuarded]);

  const rollbackSelected = useCallback(async () => {
    if (!selectedRunId) return;
    const result = await runGuarded(() => client.rollback(selectedRunId));
    if (result) {
      setRollbackOk(result.rollback.ok);
      await refreshRuns();
    }
  }, [client, selectedRunId, runGuarded, refreshRuns]);

  const setRule = useCallback((changes: Partial<RecurrenceRule>) => {
    setRecurrenceState((current) => ({ ...current, ...changes }));
  }, []);

  const planRecurrence = useCallback(
    (after: number, before: number) =>
      setOccurrences(expand(recurrence, after, before)),
    [recurrence],
  );

  return {
    client,
    playbook,
    values,
    trace,
    timeline,
    runs,
    selectedRunId,
    selectedRun,
    diff,
    replayOk,
    rollbackOk,
    recurrence,
    occurrences,
    issue,
    error,
    busy,
    dag,
    setValue,
    addStep,
    updateStep,
    removeStep,
    connect,
    setRule,
    dryRun,
    execute,
    refreshRuns,
    selectRun,
    replaySelected,
    rollbackSelected,
    planRecurrence,
    clearIssue: () => setIssue(null),
  };
}

export { humanize };
