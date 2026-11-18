import { V2Client, type V2ClientOptions } from "../../lib/apiClient";
import type {
  BundlePayload,
  GraphData,
  ImportReport,
  Page,
  Playbook,
  PlaybookSummary,
  Recommendation,
  RunPlan,
  RunProgress,
  RunState,
  SnippetRecord,
  SnippetUsage,
  StepAdvice,
  StepGraphData,
  TemplatePreview,
  TemplateRecord,
} from "./types";

export interface PlaybooksClientOptions extends V2ClientOptions {}

export interface ListOptions {
  query?: string;
  tags?: string[];
  status?: string;
  category?: string;
  library?: string;
  cursor?: string;
  limit?: number;
}

export interface ValidateResult {
  key: string;
  ok: boolean;
  issues: Array<Record<string, unknown>>;
}

export interface HistoryResult {
  key: string;
  versions: Array<Record<string, unknown>>;
}

export interface StatsResult {
  [key: string]: number | string | string[];
}

export interface OptionsResult {
  [key: string]: string[];
}

export interface PreviewResult {
  plan: RunPlan;
  markdown: string;
}

function compact(input: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === null || value === "") continue;
    result[key] = value;
  }
  return result;
}

export class PlaybooksClient {
  readonly client: V2Client;

  constructor(options: PlaybooksClientOptions | V2Client = {}) {
    this.client = options instanceof V2Client ? options : new V2Client(options);
  }

  private call<T>(
    route: string,
    body: Record<string, unknown> = {},
  ): Promise<T> {
    return this.client.call<T>(route, body);
  }

  listPlaybooks(options: ListOptions = {}): Promise<Page<PlaybookSummary>> {
    return this.call<Page<PlaybookSummary>>(
      "playbooks.list",
      compact({ ...options }),
    );
  }

  getPlaybook(key: string): Promise<Playbook> {
    return this.call<Playbook>("playbooks.get", { key });
  }

  createPlaybook(
    payload: Partial<Playbook> & { key: string; title: string },
  ): Promise<Playbook> {
    return this.call<Playbook>(
      "playbooks.create",
      payload as Record<string, unknown>,
    );
  }

  updatePlaybook(key: string, changes: Partial<Playbook>): Promise<Playbook> {
    return this.call<Playbook>("playbooks.update", { key, ...changes });
  }

  deletePlaybook(key: string): Promise<PlaybookSummary> {
    return this.call<PlaybookSummary>("playbooks.delete", { key });
  }

  clonePlaybook(key: string, newKey = "", title = ""): Promise<Playbook> {
    return this.call<Playbook>(
      "playbooks.clone",
      compact({ key, new_key: newKey, title }),
    );
  }

  validatePlaybook(key: string): Promise<ValidateResult> {
    return this.call<ValidateResult>("playbooks.validate", { key });
  }

  graph(key: string): Promise<GraphData> {
    return this.call<GraphData>("playbooks.graph", { key });
  }

  stepGraph(key: string, stepId: string): Promise<StepGraphData> {
    return this.call<StepGraphData>("playbooks.step_graph", {
      key,
      step_id: stepId,
    });
  }

  recommend(context: Record<string, unknown> = {}): Promise<Recommendation[]> {
    return this.call<Recommendation[]>("playbooks.recommend", context);
  }

  stats(): Promise<StatsResult> {
    return this.call<StatsResult>("playbooks.stats");
  }

  options(): Promise<OptionsResult> {
    return this.call<OptionsResult>("playbooks.options");
  }

  exportBundle(source = "redscribe"): Promise<BundlePayload> {
    return this.call<BundlePayload>("playbooks.export", { source });
  }

  importBundle(
    bundle: BundlePayload,
    strategy = "skip",
  ): Promise<ImportReport> {
    return this.call<ImportReport>("playbooks.import", { bundle, strategy });
  }

  reset(): Promise<StatsResult> {
    return this.call<StatsResult>("playbooks.reset");
  }

  addStep(
    key: string,
    step: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.call("steps.add", { key, step });
  }

  updateStep(
    key: string,
    stepId: string,
    step: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.call("steps.update", { key, step_id: stepId, step });
  }

  removeStep(key: string, stepId: string): Promise<Record<string, unknown>> {
    return this.call("steps.remove", { key, step_id: stepId });
  }

  moveStep(
    key: string,
    stepId: string,
    position: number,
  ): Promise<Record<string, unknown>> {
    return this.call("steps.move", { key, step_id: stepId, position });
  }

  linkSteps(
    key: string,
    stepId: string,
    dependsOn: string,
  ): Promise<Record<string, unknown>> {
    return this.call("steps.link", {
      key,
      step_id: stepId,
      depends_on: dependsOn,
    });
  }

  unlinkSteps(
    key: string,
    stepId: string,
    dependsOn: string,
  ): Promise<Record<string, unknown>> {
    return this.call("steps.unlink", {
      key,
      step_id: stepId,
      depends_on: dependsOn,
    });
  }

  setStepChecklist(
    key: string,
    stepId: string,
    items: unknown[],
  ): Promise<Record<string, unknown>> {
    return this.call("steps.checklist", { key, step_id: stepId, items });
  }

  addVariable(
    key: string,
    variable: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.call("variables.add", { key, variable });
  }

  removeVariable(key: string, name: string): Promise<Record<string, unknown>> {
    return this.call("variables.remove", { key, name });
  }

  resolveVariables(
    key: string,
    values: Record<string, unknown>,
    target = "",
    strict = false,
  ): Promise<Record<string, unknown>> {
    return this.call("variables.resolve", { key, values, target, strict });
  }

  listSnippets(options: ListOptions = {}): Promise<Page<SnippetRecord>> {
    return this.call<Page<SnippetRecord>>(
      "snippets.list",
      compact({ ...options }),
    );
  }

  getSnippet(key: string): Promise<SnippetRecord> {
    return this.call<SnippetRecord>("snippets.get", { key });
  }

  createSnippet(payload: Record<string, unknown>): Promise<SnippetRecord> {
    return this.call<SnippetRecord>("snippets.create", payload);
  }

  updateSnippet(
    key: string,
    changes: Record<string, unknown>,
  ): Promise<SnippetRecord> {
    return this.call<SnippetRecord>("snippets.update", { key, ...changes });
  }

  deleteSnippet(key: string): Promise<SnippetRecord> {
    return this.call<SnippetRecord>("snippets.delete", { key });
  }

  useSnippet(
    key: string,
    values: Record<string, unknown> = {},
  ): Promise<SnippetUsage> {
    return this.call<SnippetUsage>("snippets.use", { key, values });
  }

  composeSnippets(
    keys: string[],
    values: Record<string, unknown> = {},
  ): Promise<SnippetUsage> {
    return this.call<SnippetUsage>("snippets.compose", { keys, values });
  }

  snippetStats(): Promise<StatsResult> {
    return this.call<StatsResult>("snippets.stats");
  }

  listTemplates(options: ListOptions = {}): Promise<Page<TemplateRecord>> {
    return this.call<Page<TemplateRecord>>(
      "templates.list",
      compact({ ...options }),
    );
  }

  getTemplate(key: string): Promise<TemplateRecord> {
    return this.call<TemplateRecord>("templates.get", { key });
  }

  renderTemplate(
    key: string,
    values: Record<string, unknown> = {},
    target = "",
    strict = false,
  ): Promise<TemplatePreview> {
    return this.call<TemplatePreview>(
      "templates.render",
      compact({ key, values, target, strict }),
    );
  }

  templateHistory(key: string): Promise<HistoryResult> {
    return this.call<HistoryResult>("templates.history", { key });
  }

  registerTemplate(payload: Record<string, unknown>): Promise<TemplateRecord> {
    return this.call<TemplateRecord>("templates.register", payload);
  }

  deleteTemplate(key: string): Promise<TemplateRecord> {
    return this.call<TemplateRecord>("templates.delete", { key });
  }

  planRun(
    key: string,
    values: Record<string, unknown> = {},
    target = "",
    strict = false,
  ): Promise<RunPlan> {
    return this.call<RunPlan>(
      "runs.plan",
      compact({ key, values, target, strict }),
    );
  }

  previewRun(
    key: string,
    values: Record<string, unknown> = {},
    target = "",
    strict = false,
  ): Promise<PreviewResult> {
    return this.call<PreviewResult>(
      "runs.preview",
      compact({ key, values, target, strict }),
    );
  }

  startRun(
    key: string,
    values: Record<string, unknown> = {},
    target = "",
    strict = false,
  ): Promise<RunState> {
    return this.call<RunState>(
      "runs.start",
      compact({ key, values, target, strict }),
    );
  }

  getRun(id: number): Promise<RunState> {
    return this.call<RunState>("runs.get", { id });
  }

  listRuns(
    playbookKey = "",
    options: ListOptions = {},
  ): Promise<Page<RunState>> {
    return this.call<Page<RunState>>(
      "runs.list",
      compact({ playbook_key: playbookKey, ...options }),
    );
  }

  nextStep(id: number): Promise<StepAdvice> {
    return this.call<StepAdvice>("runs.next", { id });
  }

  advanceRun(
    id: number,
    stepId: string,
    status = "done",
    message = "",
    output = "",
    values: Record<string, unknown> = {},
  ): Promise<RunState> {
    return this.call<RunState>("runs.advance", {
      id,
      step_id: stepId,
      status,
      message,
      output,
      variables: values,
    });
  }

  cancelRun(id: number, reason = ""): Promise<RunState> {
    return this.call<RunState>("runs.cancel", compact({ id, reason }));
  }

  runProgress(id: number): Promise<RunProgress> {
    return this.call<RunProgress>("runs.progress", { id });
  }

  runChecklist(id: number): Promise<Record<string, unknown>> {
    return this.call<Record<string, unknown>>("runs.checklist", { id });
  }

  setRunChecklist(
    id: number,
    itemId: string,
    state: string,
    note = "",
  ): Promise<Record<string, unknown>> {
    return this.call(
      "runs.set_checklist",
      compact({ id, item_id: itemId, state, note }),
    );
  }
}

export function createPlaybooksClient(
  options?: PlaybooksClientOptions,
): PlaybooksClient {
  return new PlaybooksClient(options ?? {});
}
