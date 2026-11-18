import { useState } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { checklistProgress, progressPercent } from "./helpers";
import type { ChecklistState, RunPlan, RunState } from "./types";

export interface ChecklistRunnerProps {
  plan: RunPlan | null;
  run: RunState | null;
  onSet: (itemId: string, state: ChecklistState, note: string) => void;
}

const STATES: ChecklistState[] = ["pending", "done", "skipped", "blocked"];

export function ChecklistRunner({ plan, run, onSet }: ChecklistRunnerProps) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  if (!plan || !run) {
    return (
      <p className="pb-muted">
        Create a dry run to work through the checklist.
      </p>
    );
  }
  const progress = checklistProgress(run, plan);
  if (progress.items.length === 0) {
    return <p className="pb-muted">This playbook has no checklist items.</p>;
  }

  return (
    <div className="pb-checklist-runner">
      <div className="pb-progress">
        <div className="pb-progress__bar">
          <span style={{ width: `${progress.percent}%` }} />
        </div>
        <span className="pb-progress__label">
          {progress.done}/{progress.total} checked ·{" "}
          {progressPercent(progress.required_done, progress.required_total)}%
          required
        </span>
      </div>

      <div className="pb-checklist-runner__list">
        {progress.items.map((item) => {
          const note = notes[item.id] ?? item.note;
          return (
            <article className="pb-check-item" key={item.id}>
              <header className="pb-check-item__head">
                <span
                  className={`pb-check-dot pb-check-dot--${item.state}`}
                  aria-hidden="true"
                />
                <div>
                  <strong>{item.title}</strong>
                  {item.required ? (
                    <span className="pb-required">required</span>
                  ) : null}
                </div>
              </header>
              <div className="pb-check-item__controls">
                <div className="pb-chip-row">
                  {STATES.map((state) => (
                    <Button
                      key={state}
                      size="sm"
                      variant={item.state === state ? "primary" : "ghost"}
                      onClick={() => onSet(item.id, state, note)}
                    >
                      {state}
                    </Button>
                  ))}
                </div>
                <Field
                  label="Note"
                  value={note}
                  placeholder="Evidence or observation"
                  onChange={(event) =>
                    setNotes({ ...notes, [item.id]: event.target.value })
                  }
                  onBlur={() => onSet(item.id, item.state, note)}
                />
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
