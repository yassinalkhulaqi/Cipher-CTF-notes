import { Button } from "../../ui/Button";
import { Banner } from "../../ui/Banner";
import {
  formatMinutes,
  issueText,
  nextAdvice,
  planVariables,
  summarizeRun,
} from "./helpers";
import type { RunPlan, RunState } from "./types";

export interface DryRunPanelProps {
  plan: RunPlan | null;
  run: RunState | null;
  saving: boolean;
  onStart: () => void;
  onAdvance: (stepId: string, status: string) => void;
  onCancel: () => void;
}

export function DryRunPanel({
  plan,
  run,
  saving,
  onStart,
  onAdvance,
  onCancel,
}: DryRunPanelProps) {
  if (!plan) {
    return (
      <p className="pb-muted">
        Build a dry run to preview commands and ordering.
      </p>
    );
  }
  const advice = nextAdvice(plan, run);
  const progress = run ? summarizeRun(run, plan) : null;
  const variables = planVariables(plan);

  return (
    <div className="pb-dry-run">
      <header className="pb-dry-run__header">
        <div>
          <strong>{plan.playbook_key}</strong>
          <span className="pb-muted">v{plan.version}</span>
        </div>
        <div className="pb-dry-run__meta">
          <span>{plan.steps.length} steps</span>
          <span>{formatMinutes(plan.estimated_minutes)}</span>
          <span>{variables.length} variables</span>
        </div>
      </header>

      {plan.issues.length > 0 ? (
        <Banner tone="warning" title="Plan issues">
          {issueText(plan.issues)}
        </Banner>
      ) : null}

      {progress ? (
        <div className="pb-progress">
          <div className="pb-progress__bar">
            <span style={{ width: `${progress.percent}%` }} />
          </div>
          <span className="pb-progress__label">
            {progress.settled}/{progress.total} steps · {progress.status}
          </span>
        </div>
      ) : null}

      {advice ? (
        <div className="pb-dry-run__advice">
          <span>Next: {advice.title}</span>
          <code>{advice.command}</code>
          {advice.blocked_by.length > 0 ? (
            <span className="pb-warning">
              Blocked by {advice.blocked_by.join(", ")}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="pb-dry-run__actions">
        {run ? (
          <>
            {advice ? (
              <>
                <Button
                  variant="primary"
                  loading={saving}
                  onClick={() => onAdvance(advice.step_id, "done")}
                >
                  Mark done
                </Button>
                <Button
                  variant="secondary"
                  loading={saving}
                  onClick={() => onAdvance(advice.step_id, "skipped")}
                >
                  Skip
                </Button>
              </>
            ) : null}
            <Button variant="danger" loading={saving} onClick={onCancel}>
              Cancel run
            </Button>
          </>
        ) : (
          <Button variant="primary" loading={saving} onClick={onStart}>
            Start run
          </Button>
        )}
      </div>

      <div className="pb-dry-run__path">
        <span>Critical path</span>
        <div className="pb-chip-row">
          {plan.critical_path.length === 0 ? (
            <span className="pb-muted">None</span>
          ) : (
            plan.critical_path.map((stepId) => (
              <span className="pb-chip pb-chip--muted" key={stepId}>
                {stepId}
              </span>
            ))
          )}
        </div>
      </div>

      <ol className="pb-plan-steps">
        {plan.steps.map((step, index) => (
          <li className="pb-plan-step" key={step.id}>
            <header>
              <span className="pb-plan-step__index">{index + 1}</span>
              <strong>{step.title}</strong>
              {step.skipped ? (
                <span className="pb-chip pb-chip--warning">skipped</span>
              ) : null}
            </header>
            <pre>{step.command || "(no command)"}</pre>
            {step.reason ? <p className="pb-muted">{step.reason}</p> : null}
            {step.warnings.length > 0 ? (
              <p className="pb-warning">{issueText(step.warnings)}</p>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
