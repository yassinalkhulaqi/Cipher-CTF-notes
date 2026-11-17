import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { describeCondition, stepKindLabel } from "./helpers";
import type {
  ChecklistItem,
  Condition,
  PlaybookStep,
  SnippetRecord,
  StepKind,
} from "./types";

export interface StepEditorProps {
  step: PlaybookStep;
  index: number;
  total: number;
  stepIds: string[];
  snippets: SnippetRecord[];
  onChange: (step: PlaybookStep) => void;
  onRemove: () => void;
  onMove: (offset: number) => void;
}

const KINDS: StepKind[] = [
  "action",
  "checklist",
  "command",
  "decision",
  "note",
  "verification",
];

function newChecklistItem(index: number): ChecklistItem {
  return {
    id: `check-${Date.now().toString(36)}-${index}`,
    label: "",
    detail: "",
    required: true,
    condition: null,
    tags: [],
  };
}

function newCondition(): Condition {
  return { field: "target", operator: "exists", value: "" };
}

export function StepEditor({
  step,
  index,
  total,
  stepIds,
  snippets,
  onChange,
  onRemove,
  onMove,
}: StepEditorProps) {
  const [open, setOpen] = useState(index === 0);
  const [checklistDraft, setChecklistDraft] = useState("");
  const snippetOptions = useMemo(
    () =>
      snippets.filter(
        (snippet) => snippet.variables.length <= step.variables.length + 3,
      ),
    [snippets, step.variables.length],
  );

  const patch = (changes: Partial<PlaybookStep>) =>
    onChange({ ...step, ...changes });

  const setChecklist = (items: ChecklistItem[]) => patch({ checklist: items });

  const setConditions = (when: Condition[]) => patch({ when });

  const toggleDependency = (id: string) => {
    if (id === step.id) return;
    const dependsOn = step.depends_on.includes(id)
      ? step.depends_on.filter((item) => item !== id)
      : [...step.depends_on, id];
    patch({ depends_on: dependsOn });
  };

  const addChecklistItem = () => {
    const title = checklistDraft.trim();
    if (!title) return;
    const item = newChecklistItem(step.checklist.length);
    setChecklist([...step.checklist, { ...item, label: title }]);
    setChecklistDraft("");
  };

  return (
    <article className={`pb-step${open ? " pb-step--open" : ""}`}>
      <header className="pb-step__header">
        <button
          type="button"
          className="pb-step__toggle"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span className="pb-step__index">{index + 1}</span>
          <span className="pb-step__heading">
            <strong>{step.title || "Untitled step"}</strong>
            <span className="pb-step__meta">
              {stepKindLabel(step.kind)} · {step.checklist.length} checks ·{" "}
              {step.depends_on.length} dependencies
            </span>
          </span>
        </button>
        <div className="pb-step__actions">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onMove(-1)}
            disabled={index === 0}
          >
            Up
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onMove(1)}
            disabled={index === total - 1}
          >
            Down
          </Button>
          <Button size="sm" variant="danger" onClick={onRemove}>
            Remove
          </Button>
        </div>
      </header>

      {open ? (
        <div className="pb-step__body">
          <div className="pb-grid pb-grid--three">
            <Field
              label="Step id"
              value={step.id}
              onChange={(event) => patch({ id: event.target.value.trim() })}
            />
            <Field
              label="Title"
              value={step.title}
              onChange={(event) => patch({ title: event.target.value })}
            />
            <label className="pb-field">
              <span>Kind</span>
              <select
                value={step.kind}
                onChange={(event) =>
                  patch({ kind: event.target.value as StepKind })
                }
              >
                {KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {stepKindLabel(kind)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="pb-field">
            <span>Summary</span>
            <textarea
              rows={2}
              value={step.summary}
              onChange={(event) => patch({ summary: event.target.value })}
            />
          </label>

          <div className="pb-grid pb-grid--two">
            <label className="pb-field">
              <span>Snippet</span>
              <select
                value={step.snippet_key ?? ""}
                onChange={(event) => patch({ snippet_key: event.target.value })}
              >
                <option value="">No snippet</option>
                {snippetOptions.map((snippet) => (
                  <option key={snippet.key} value={snippet.key}>
                    {snippet.title} · {snippet.key}
                  </option>
                ))}
              </select>
            </label>
            <Field
              label="Estimated minutes"
              type="number"
              min={0}
              max={480}
              value={String(step.estimated_minutes)}
              onChange={(event) =>
                patch({
                  estimated_minutes: Math.max(
                    0,
                    Number(event.target.value) || 0,
                  ),
                })
              }
            />
          </div>

          <label className="pb-field">
            <span>Command template</span>
            <textarea
              rows={3}
              className="pb-code"
              value={step.command_template}
              placeholder="nmap -sV {{ target }}"
              onChange={(event) =>
                patch({ command_template: event.target.value })
              }
            />
          </label>

          <label className="pb-check">
            <input
              type="checkbox"
              checked={step.optional}
              onChange={(event) => patch({ optional: event.target.checked })}
            />
            Optional step
          </label>

          <fieldset className="pb-fieldset">
            <legend>Dependencies</legend>
            <div className="pb-chip-row">
              {stepIds.length === 0 ? (
                <span className="pb-list__muted">No other steps</span>
              ) : (
                stepIds.map((id) => (
                  <Button
                    key={id}
                    size="sm"
                    variant={step.depends_on.includes(id) ? "primary" : "ghost"}
                    onClick={() => toggleDependency(id)}
                    disabled={id === step.id}
                  >
                    {id}
                  </Button>
                ))
              )}
            </div>
          </fieldset>

          <fieldset className="pb-fieldset">
            <legend>Conditions</legend>
            <div className="pb-condition-list">
              {step.when.map((condition, conditionIndex) => (
                <div
                  className="pb-condition"
                  key={`${condition.field}-${conditionIndex}`}
                >
                  <span className="pb-condition__text">
                    {describeCondition(condition)}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setConditions(
                        step.when.filter((_, item) => item !== conditionIndex),
                      )
                    }
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setConditions([...step.when, newCondition()])}
            >
              Add condition
            </Button>
          </fieldset>

          <fieldset className="pb-fieldset">
            <legend>Checklist</legend>
            <div className="pb-checklist-editor">
              {step.checklist.map((item, itemIndex) => (
                <div className="pb-checklist-row" key={item.id}>
                  <Field
                    label={`Item ${itemIndex + 1}`}
                    value={item.label}
                    onChange={(event) => {
                      const items = [...step.checklist];
                      items[itemIndex] = { ...item, label: event.target.value };
                      setChecklist(items);
                    }}
                  />
                  <label className="pb-check">
                    <input
                      type="checkbox"
                      checked={item.required === true}
                      onChange={(event) => {
                        const items = [...step.checklist];
                        items[itemIndex] = {
                          ...item,
                          required: event.target.checked,
                        };
                        setChecklist(items);
                      }}
                    />
                    Required
                  </label>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setChecklist(
                        step.checklist.filter((_, row) => row !== itemIndex),
                      )
                    }
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
            <div className="pb-inline-form">
              <Field
                label="New checklist item"
                value={checklistDraft}
                onChange={(event) => setChecklistDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addChecklistItem();
                  }
                }}
              />
              <Button size="sm" variant="secondary" onClick={addChecklistItem}>
                Add item
              </Button>
            </div>
          </fieldset>
        </div>
      ) : null}
    </article>
  );
}
