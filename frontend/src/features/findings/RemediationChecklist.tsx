import { useState, type FormEvent, type KeyboardEvent } from "react";

import { remediationPercent, taskSummary } from "./logic";
import type { FindingDetail } from "./types";

export interface RemediationChecklistProps {
  detail: FindingDetail;
  onAdd: (lines: string) => Promise<void>;
  onStatus: (taskId: string, status: string) => Promise<void>;
  busy?: boolean;
}

export function RemediationChecklist({
  detail,
  onAdd,
  onStatus,
  busy = false,
}: RemediationChecklistProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const tasks = detail.remediation.tasks;
  const percent = remediationPercent(tasks);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const lines = draft.trim();
    if (!lines) return;
    try {
      await onAdd(lines);
      setDraft("");
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not add remediation tasks",
      );
    }
  };

  const cycleStatus = (taskId: string, current: string) => {
    const next =
      current === "todo"
        ? "in_progress"
        : current === "in_progress"
          ? "done"
          : "todo";
    void onStatus(taskId, next).catch((cause: unknown) => {
      setError(
        cause instanceof Error ? cause.message : "Could not update task",
      );
    });
  };

  const handleKey = (
    event: KeyboardEvent<HTMLButtonElement>,
    taskId: string,
    status: string,
  ) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const options = ["todo", "in_progress", "done", "skipped"];
      const index = options.indexOf(status);
      const next =
        options[Math.min(options.length - 1, Math.max(0, index + direction))];
      void onStatus(taskId, next).catch(() => undefined);
    }
  };

  return (
    <section
      className="remediation"
      data-testid="remediation-panel"
      data-complete={detail.remediation.complete}
    >
      <header className="remediation__header">
        <h3>Remediation checklist</h3>
        <span className="remediation__percent">{percent}%</span>
      </header>
      <div
        className="remediation__progress"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Remediation progress"
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="remediation__summary">{taskSummary(tasks)}</p>

      {tasks.length === 0 ? (
        <p className="remediation__empty">
          Add the steps needed to resolve this finding.
        </p>
      ) : (
        <ul className="remediation__list">
          {tasks.map((task, index) => (
            <li
              key={task.task_id}
              data-status={task.status}
              data-testid="remediation-task"
            >
              <button
                type="button"
                className="remediation__status"
                aria-label={`Cycle status for ${task.title}`}
                data-status={task.status}
                disabled={busy}
                onClick={() => cycleStatus(task.task_id, task.status)}
                onKeyDown={(event) =>
                  handleKey(event, task.task_id, task.status)
                }
              >
                {task.status === "done"
                  ? "✓"
                  : task.status === "skipped"
                    ? "–"
                    : index + 1}
              </button>
              <div className="remediation__task-body">
                <span className="remediation__title">{task.title}</span>
                {task.detail && (
                  <span className="remediation__detail">{task.detail}</span>
                )}
                {task.proof_refs.length > 0 && (
                  <span className="remediation__proof">
                    {task.proof_refs.length} proof links
                  </span>
                )}
              </div>
              <span className="remediation__status-label">
                {task.status.replace("_", " ")}
              </span>
            </li>
          ))}
        </ul>
      )}

      <form
        className="remediation__form"
        onSubmit={(event) => void submit(event)}
      >
        <label htmlFor="remediation-lines">Add steps (one per line)</label>
        <textarea
          id="remediation-lines"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          placeholder="Rotate the exposed credential&#10;Add a regression test"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          Add to checklist
        </button>
      </form>
      {error && (
        <p className="remediation__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
