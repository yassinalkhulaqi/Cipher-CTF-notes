import { useEffect, useMemo, useState } from "react";
import { Banner } from "../../ui/Banner";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Tabs } from "../../ui/Tabs";
import { ChecklistRunner } from "./ChecklistRunner";
import { DryRunPanel } from "./DryRunPanel";
import { SnippetBrowser } from "./SnippetBrowser";
import { StepEditor } from "./StepEditor";
import { TemplatePicker } from "./TemplatePicker";
import { VariableForm } from "./VariableForm";
import {
  graphLayers,
  initialInputs,
  issueText,
  stepKindLabel,
  validatePlaybookDraft,
  valuesFromInputs,
} from "./helpers";
import type {
  ChecklistState,
  Playbook,
  SnippetUsage,
  TemplatePreview,
} from "./types";
import type { PlaybooksController } from "./usePlaybooks";

export interface PlaybookDetailProps {
  controller: PlaybooksController;
}

const TAB_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "steps", label: "Steps" },
  { id: "variables", label: "Variables" },
  { id: "checklist", label: "Checklist" },
  { id: "snippets", label: "Snippets" },
  { id: "templates", label: "Templates" },
  { id: "dryrun", label: "Dry run" },
];

function blankStep(index: number): Playbook["steps"][number] {
  return {
    id: `step_${index + 1}`,
    title: `Step ${index + 1}`,
    kind: "action",
    summary: "",
    command_template: "",
    snippet_key: "",
    checklist: [],
    depends_on: [],
    when: [],
    variables: [],
    optional: false,
    estimated_minutes: 5,
    tags: [],
    note: "",
  };
}

export function PlaybookDetail({ controller }: PlaybookDetailProps) {
  const [draft, setDraft] = useState<Playbook | null>(controller.selected);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [tab, setTab] = useState("overview");
  const [snippetUsage, setSnippetUsage] = useState<SnippetUsage | null>(null);
  const [templatePreview, setTemplatePreview] =
    useState<TemplatePreview | null>(null);

  useEffect(() => {
    setDraft(controller.selected);
    setInputs(initialInputs(controller.selected?.variables ?? []));
    setSnippetUsage(null);
    setTemplatePreview(null);
  }, [controller.selected]);

  const values = useMemo(
    () => valuesFromInputs(draft?.variables ?? [], inputs),
    [draft?.variables, inputs],
  );
  const issues = useMemo(
    () => (draft ? validatePlaybookDraft(draft) : []),
    [draft],
  );
  const layers = useMemo(() => (draft ? graphLayers(draft) : []), [draft]);

  if (!draft) {
    return (
      <div className="pb-detail pb-detail--empty">
        <Banner tone="info" title="Select a playbook">
          Choose a playbook from the library to inspect its steps, variables,
          and run previews.
        </Banner>
      </div>
    );
  }

  const patch = (changes: Partial<Playbook>) =>
    setDraft({ ...draft, ...changes });

  const patchStep = (index: number, step: Playbook["steps"][number]) => {
    const steps = [...draft.steps];
    steps[index] = step;
    patch({ steps });
  };

  const moveStep = (index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= draft.steps.length) return;
    const steps = [...draft.steps];
    const [step] = steps.splice(index, 1);
    if (!step) return;
    steps.splice(target, 0, step);
    patch({ steps });
  };

  const addStep = () => {
    patch({ steps: [...draft.steps, blankStep(draft.steps.length)] });
  };

  const useSnippet = async (key: string) => {
    try {
      setSnippetUsage(await controller.client.useSnippet(key, values));
    } catch (caught) {
      controller.setNotice(
        caught instanceof Error ? caught.message : String(caught),
      );
    }
  };

  const composeSnippets = async (keys: string[]) => {
    try {
      setSnippetUsage(await controller.client.composeSnippets(keys, values));
    } catch (caught) {
      controller.setNotice(
        caught instanceof Error ? caught.message : String(caught),
      );
    }
  };

  const renderTemplate = async (key: string) => {
    try {
      setTemplatePreview(await controller.client.renderTemplate(key, values));
    } catch (caught) {
      controller.setNotice(
        caught instanceof Error ? caught.message : String(caught),
      );
    }
  };

  const setChecklist = async (
    itemId: string,
    state: ChecklistState,
    note: string,
  ) => {
    if (!controller.run) return;
    try {
      await controller.client.setRunChecklist(
        controller.run.id,
        itemId,
        state,
        note,
      );
      controller.setNotice(`Checklist item ${itemId} is ${state}`);
    } catch (caught) {
      controller.setNotice(
        caught instanceof Error ? caught.message : String(caught),
      );
    }
  };

  const tabItems = TAB_ITEMS.map((item) => ({
    ...item,
    content: undefined,
  }));

  return (
    <div className="pb-detail">
      <header className="pb-detail__header">
        <div>
          <div className="pb-detail__eyebrow">
            <code>{draft.key}</code>
            <span className={`pb-chip pb-chip--${draft.status}`}>
              {draft.status}
            </span>
            <span className="pb-chip pb-chip--muted">v{draft.version}</span>
          </div>
          <h2>{draft.title}</h2>
          <p className="pb-section-subtitle">{draft.description}</p>
        </div>
        <div className="pb-detail__actions">
          <Button
            variant="secondary"
            onClick={() => void controller.duplicate(draft.key)}
          >
            Clone
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm(`Delete ${draft.key}?`))
                void controller.remove(draft.key);
            }}
          >
            Delete
          </Button>
          <Button
            variant="primary"
            loading={controller.saving}
            onClick={() => void controller.savePlaybook(draft)}
          >
            Save changes
          </Button>
        </div>
      </header>

      {issues.length > 0 ? (
        <Banner tone="warning" title="Draft validation">
          {issueText(issues)}
        </Banner>
      ) : null}

      <Tabs
        items={tabItems}
        label="Playbook sections"
        value={tab}
        onChange={setTab}
      />

      <div className="pb-detail__body">
        {tab === "overview" ? (
          <div className="pb-overview">
            <div className="pb-grid pb-grid--two">
              <Field
                label="Title"
                value={draft.title}
                onChange={(event) => patch({ title: event.target.value })}
              />
              <Field
                label="Category"
                value={draft.category}
                onChange={(event) => patch({ category: event.target.value })}
              />
            </div>
            <label className="pb-field">
              <span>Description</span>
              <textarea
                rows={4}
                value={draft.description}
                onChange={(event) => patch({ description: event.target.value })}
              />
            </label>
            <Field
              label="Tags"
              value={draft.tags.join(", ")}
              onChange={(event) =>
                patch({
                  tags: event.target.value
                    .split(/[\s,]+/)
                    .map((tag) => tag.trim())
                    .filter(Boolean),
                })
              }
            />
            <label className="pb-field">
              <span>Status</span>
              <select
                value={draft.status}
                onChange={(event) =>
                  patch({ status: event.target.value as Playbook["status"] })
                }
              >
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
              </select>
            </label>
            <div className="pb-overview__dag">
              <h3>Dependency layers</h3>
              {layers.length === 0 ? (
                <p className="pb-muted">No steps yet.</p>
              ) : (
                layers.map((layer, index) => (
                  <div className="pb-dag-layer" key={`layer-${index}`}>
                    <span className="pb-dag-layer__label">
                      Layer {index + 1}
                    </span>
                    <div className="pb-chip-row">
                      {layer.map((stepId) => (
                        <span className="pb-chip" key={stepId}>
                          {stepId}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : null}

        {tab === "steps" ? (
          <div className="pb-steps">
            {draft.steps.map((step, index) => (
              <StepEditor
                key={step.id}
                step={step}
                index={index}
                total={draft.steps.length}
                stepIds={draft.steps.map((item) => item.id)}
                snippets={controller.snippets}
                onChange={(next) => patchStep(index, next)}
                onRemove={() =>
                  patch({
                    steps: draft.steps.filter((_, item) => item !== index),
                  })
                }
                onMove={(offset) => moveStep(index, offset)}
              />
            ))}
            <Button variant="secondary" onClick={addStep}>
              Add step
            </Button>
          </div>
        ) : null}

        {tab === "variables" ? (
          <VariableForm
            definitions={draft.variables}
            values={values}
            inputs={inputs}
            onChange={(variables) => patch({ variables })}
            onInputChange={(key, value) =>
              setInputs({ ...inputs, [key]: value })
            }
            onValuesChange={() => undefined}
          />
        ) : null}

        {tab === "checklist" ? (
          <ChecklistRunner
            plan={controller.plan}
            run={controller.run}
            onSet={(itemId, state, note) =>
              void setChecklist(itemId, state, note)
            }
          />
        ) : null}

        {tab === "snippets" ? (
          <SnippetBrowser
            snippets={controller.snippets}
            usage={snippetUsage}
            onUse={(key) => void useSnippet(key)}
            onCompose={(keys) => void composeSnippets(keys)}
          />
        ) : null}

        {tab === "templates" ? (
          <TemplatePicker
            templates={controller.templates}
            values={values}
            preview={templatePreview}
            onRender={(key) => void renderTemplate(key)}
          />
        ) : null}

        {tab === "dryrun" ? (
          <div className="pb-dryrun-tab">
            <div className="pb-dryrun-tab__controls">
              <Button
                variant="secondary"
                loading={controller.saving}
                onClick={() => void controller.makePlan(draft.key, values)}
              >
                Build dry run
              </Button>
              <Button
                variant="primary"
                loading={controller.saving}
                onClick={() => void controller.start(draft.key, values)}
              >
                Start run
              </Button>
              {controller.run ? (
                <Button variant="ghost" onClick={controller.clearRun}>
                  Clear run
                </Button>
              ) : null}
            </div>
            <DryRunPanel
              plan={controller.plan}
              run={controller.run}
              saving={controller.saving}
              onStart={() => void controller.start(draft.key, values)}
              onAdvance={(stepId, status) =>
                void controller.advance(stepId, status)
              }
              onCancel={() => {
                if (controller.run)
                  void controller.client.cancelRun(controller.run.id);
              }}
            />
          </div>
        ) : null}
      </div>

      <footer className="pb-detail__footer">
        <span>{draft.steps.length} steps</span>
        <span>
          {draft.steps.reduce(
            (total, step) => total + step.checklist.length,
            0,
          )}{" "}
          checks
        </span>
        <span>{draft.variables.length} variables</span>
        <span>
          {draft.steps.map((step) => stepKindLabel(step.kind)).join(" · ") ||
            "No steps"}
        </span>
      </footer>
    </div>
  );
}
