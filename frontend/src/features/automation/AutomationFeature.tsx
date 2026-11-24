/** V3 automation feature surface: plan, inspect, run, replay, roll back. */

import { useMemo, useState } from "react";
import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { DagEditor } from "./DagEditor";
import { RecurrencePicker } from "./RecurrencePicker";
import { RunHistory } from "./RunHistory";
import { StepRunner } from "./StepRunner";
import { TraceTimeline } from "./TraceTimeline";
import { VariableForm } from "./VariableForm";
import { useAutomation } from "./useAutomation";
import type { StepKind } from "./types";
import { STEP_LABELS } from "./types";

const KINDS = Object.keys(STEP_LABELS) as StepKind[];

export interface AutomationFeatureProps {
  client?: Parameters<typeof useAutomation>[0];
}

export function AutomationFeature({ client }: AutomationFeatureProps) {
  const controller = useAutomation(client);
  const [selectedId, setSelectedId] = useState("");
  const selected = useMemo(
    () => controller.playbook.steps.find((step) => step.id === selectedId) ?? null,
    [controller.playbook.steps, selectedId],
  );

  return (
    <section className="automation-feature" data-automation="feature" data-density="comfortable">
      <header className="automation-feature__header">
        <div>
          <h1>Playbook automation</h1>
          <p>Deterministic, inspectable documentation workflows. No commands, no network.</p>
        </div>
        <div className="automation-feature__stats">
          <V3Stat label="Steps" value={controller.playbook.steps.length} hint="in playbook" />
          <V3Stat label="DAG" value={controller.dag.ok ? "valid" : "invalid"} tone={controller.dag.ok ? "good" : "bad"} />
          <V3Stat label="Runs" value={controller.runs.length} hint="recorded" />
        </div>
      </header>

      {controller.error && <p className="automation-feature__error" role="alert" data-automation="error">{controller.error}</p>}
      {controller.issue && (
        <p className="automation-feature__error" role="alert" data-automation="connection-issue">
          {controller.issue.message}
          <button type="button" onClick={controller.clearIssue}>Dismiss</button>
        </p>
      )}

      <div className="automation-feature__grid">
        <V3Panel
          title="DAG editor"
          subtitle="Connect steps; cycles are rejected before they are applied."
          kind="playbook"
          density="compact"
          actions={
            <button type="button" data-automation="add-step" onClick={controller.addStep}>
              Add step
            </button>
          }
        >
          <DagEditor
            steps={controller.playbook.steps}
            dag={controller.dag}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onConnect={controller.connect}
          />
          {selected && (
            <div className="automation-feature__step-editor" data-automation="step-editor">
              <label htmlFor="automation-step-title">Step title</label>
              <input
                id="automation-step-title"
                data-automation="step-title"
                value={selected.title}
                onChange={(event) => controller.updateStep(selected.id, { title: event.target.value })}
              />
              <label htmlFor="automation-step-kind">Operation</label>
              <select
                id="automation-step-kind"
                data-automation="step-kind"
                value={selected.kind}
                onChange={(event) => controller.updateStep(selected.id, { kind: event.target.value as StepKind })}
              >
                {KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {STEP_LABELS[kind]}
                  </option>
                ))}
              </select>
              <button type="button" data-automation="remove-step" onClick={() => controller.removeStep(selected.id)}>
                Remove step
              </button>
            </div>
          )}
        </V3Panel>

        <V3Panel title="Variables" subtitle="Typed inputs with inline validation." kind="note" density="compact">
          <VariableForm
            definitions={controller.playbook.variables}
            values={controller.values}
            onChange={controller.setValue}
          />
        </V3Panel>

        <V3Panel title="Guided runner" subtitle="Keyboard-first step walkthrough." kind="run" density="compact">
          <StepRunner key={controller.playbook.steps.map((step) => step.id).join("|")} steps={controller.playbook.steps} />
        </V3Panel>

        <V3Panel title="Execution" subtitle="Dry-run first; every mutation is recorded." kind="finding" density="compact">
          <div className="automation-feature__actions">
            <button type="button" data-automation="dry-run" onClick={controller.dryRun} disabled={controller.busy}>
              Dry run
            </button>
            <button type="button" data-automation="execute" onClick={controller.execute} disabled={controller.busy}>
              Execute
            </button>
            <button type="button" data-automation="refresh-runs" onClick={controller.refreshRuns} disabled={controller.busy}>
              Refresh runs
            </button>
          </div>
          <TraceTimeline trace={controller.trace} />
        </V3Panel>

        <V3Panel title="Recurrence" subtitle="UTC schedule preview for this playbook." kind="activity" density="compact">
          <RecurrencePicker
            rule={controller.recurrence}
            occurrences={controller.occurrences}
            onChange={controller.setRule}
            onPreview={() => controller.planRecurrence(Date.UTC(2026, 0, 1), Date.UTC(2026, 2, 1))}
          />
        </V3Panel>

        <V3Panel title="Run history" subtitle="Replay determinism and rollback equivalence." kind="run" density="compact">
          <RunHistory
            runs={controller.runs}
            selectedId={controller.selectedRunId}
            replayOk={controller.replayOk}
            rollbackOk={controller.rollbackOk}
            differences={controller.diff}
            onSelect={controller.selectRun}
            onReplay={controller.replaySelected}
            onRollback={controller.rollbackSelected}
          />
        </V3Panel>
      </div>
    </section>
  );
}
