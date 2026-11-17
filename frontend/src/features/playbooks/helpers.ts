import type {
  ChecklistItem,
  ChecklistProgress,
  ChecklistState,
  Condition,
  ConditionOperator,
  Issue,
  Playbook,
  PlaybookStatus,
  PlaybookStep,
  PlaybookSummary,
  PlaybookValue,
  PlaybookValues,
  PlannedStep,
  Recommendation,
  RunPlan,
  RunProgress,
  RunState,
  SnippetRecord,
  StepAdvice,
  StepStatus,
  TemplateRecord,
  VariableDefinition,
  VariableKind,
} from "./types";

const STATUS_ORDER: Record<PlaybookStatus, number> = {
  active: 0,
  draft: 1,
  archived: 2,
};

const SETTLED: readonly StepStatus[] = ["done", "skipped", "failed"];

const OPERATOR_LABELS: Record<ConditionOperator, string> = {
  eq: "equals",
  ne: "does not equal",
  gt: "is greater than",
  gte: "is at least",
  lt: "is less than",
  lte: "is at most",
  contains: "contains",
  not_contains: "does not contain",
  in: "is one of",
  not_in: "is not one of",
  exists: "exists",
  not_exists: "does not exist",
  matches: "matches",
};

export function normalizeQuery(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

export function splitTags(value: string): string[] {
  return unique(
    value
      .split(/[\s,]+/)
      .map((tag) => tag.trim().toLocaleLowerCase().replace(/^#+/, ""))
      .filter(Boolean),
  );
}

export function unique<T>(values: readonly T[]): T[] {
  return Array.from(new Set(values));
}

export function tagKey(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/^#+/, "");
}

export function hasAnyTag(
  tags: readonly string[],
  wanted: readonly string[],
): boolean {
  if (wanted.length === 0) return true;
  const available = new Set(tags.map(tagKey));
  return wanted.some((tag) => available.has(tagKey(tag)));
}

export function filterPlaybooks(
  playbooks: readonly Playbook[],
  options: {
    query?: string;
    tags?: readonly string[];
    status?: string;
    category?: string;
  } = {},
): Playbook[] {
  const query = normalizeQuery(options.query ?? "");
  const tags = options.tags ?? [];
  const status = options.status ?? "";
  const category = options.category ?? "";
  return playbooks.filter((playbook) => {
    if (status && playbook.status !== status) return false;
    if (
      category &&
      playbook.category.toLocaleLowerCase() !== category.toLocaleLowerCase()
    ) {
      return false;
    }
    if (!hasAnyTag(playbook.tags, tags)) return false;
    if (!query) return true;
    const haystack = [
      playbook.key,
      playbook.title,
      playbook.description,
      playbook.category,
      ...playbook.tags,
      ...playbook.steps.map(
        (step) => `${step.title} ${step.summary} ${step.command_template}`,
      ),
    ]
      .join(" ")
      .toLocaleLowerCase();
    return query.split(/\s+/).every((term) => haystack.includes(term));
  });
}

export function sortPlaybooks(
  playbooks: readonly Playbook[],
  sort: "title" | "status" | "steps" | "updated" | "version" = "title",
  direction: "asc" | "desc" = "asc",
): Playbook[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...playbooks].sort((left, right) => {
    let result = 0;
    if (sort === "title") result = left.title.localeCompare(right.title);
    if (sort === "status")
      result = STATUS_ORDER[left.status] - STATUS_ORDER[right.status];
    if (sort === "steps") result = left.steps.length - right.steps.length;
    if (sort === "updated")
      result = left.updated_at.localeCompare(right.updated_at);
    if (sort === "version")
      result = compareVersions(left.version, right.version);
    return result * factor || left.key.localeCompare(right.key);
  });
}

export function compareVersions(left: string, right: string): number {
  const leftParts = left
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
  const rightParts = right
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
  for (let index = 0; index < 3; index += 1) {
    const difference = (leftParts[index] ?? 0) - (rightParts[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

export function groupByCategory(
  playbooks: readonly Playbook[],
): Map<string, Playbook[]> {
  const groups = new Map<string, Playbook[]>();
  for (const playbook of playbooks) {
    const category = playbook.category || "general";
    const bucket = groups.get(category) ?? [];
    bucket.push(playbook);
    groups.set(category, bucket);
  }
  return new Map(
    Array.from(groups.entries()).sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
}

export function summarizePlaybook(playbook: Playbook): PlaybookSummary {
  const { steps: _steps, variables: _variables, ...summary } = playbook;
  return {
    ...summary,
    step_count: playbook.steps.length,
    checklist_count: playbook.steps.reduce(
      (total, step) => total + step.checklist.length,
      0,
    ),
  };
}

export function playbookStats(
  playbooks: readonly Playbook[],
): Record<string, number> {
  const steps = playbooks.flatMap((playbook) => playbook.steps);
  return {
    playbooks: playbooks.length,
    active: playbooks.filter((playbook) => playbook.status === "active").length,
    drafts: playbooks.filter((playbook) => playbook.status === "draft").length,
    steps: steps.length,
    checklists: steps.reduce((total, step) => total + step.checklist.length, 0),
    commands: steps.filter((step) => step.command_template || step.snippet_key)
      .length,
    variables: unique(
      playbooks.flatMap((playbook) =>
        playbook.variables.map((item) => item.key),
      ),
    ).length,
    tags: unique(playbooks.flatMap((playbook) => playbook.tags.map(tagKey)))
      .length,
  };
}

export function stepMap(playbook: Playbook): Map<string, PlaybookStep> {
  return new Map(playbook.steps.map((step) => [step.id, step]));
}

export function stepById(
  playbook: Playbook,
  stepId: string,
): PlaybookStep | undefined {
  return playbook.steps.find((step) => step.id === stepId);
}

export function dependencyDepth(playbook: Playbook): Map<string, number> {
  const steps = stepMap(playbook);
  const memo = new Map<string, number>();
  const visiting = new Set<string>();
  const depth = (id: string): number => {
    const cached = memo.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const step = steps.get(id);
    const value =
      step && step.depends_on.length > 0
        ? 1 + Math.max(...step.depends_on.map(depth))
        : 0;
    visiting.delete(id);
    memo.set(id, value);
    return value;
  };
  for (const step of playbook.steps) depth(step.id);
  return memo;
}

export function graphLayers(playbook: Playbook): string[][] {
  const depths = dependencyDepth(playbook);
  const maxDepth = Math.max(0, ...depths.values());
  const layers: string[][] = Array.from({ length: maxDepth + 1 }, () => []);
  for (const step of playbook.steps) {
    const depth = depths.get(step.id) ?? 0;
    layers[depth]?.push(step.id);
  }
  return layers.map((layer) => layer.sort());
}

export function ancestorsOf(playbook: Playbook, stepId: string): string[] {
  const steps = stepMap(playbook);
  const found = new Set<string>();
  const visit = (id: string): void => {
    const step = steps.get(id);
    if (!step) return;
    for (const parent of step.depends_on) {
      if (found.has(parent)) continue;
      found.add(parent);
      visit(parent);
    }
  };
  visit(stepId);
  return Array.from(found).sort();
}

export function descendantsOf(playbook: Playbook, stepId: string): string[] {
  const found = new Set<string>();
  const visit = (id: string): void => {
    for (const step of playbook.steps) {
      if (!step.depends_on.includes(id) || found.has(step.id)) continue;
      found.add(step.id);
      visit(step.id);
    }
  };
  visit(stepId);
  return Array.from(found).sort();
}

export function readySteps(
  playbook: Playbook,
  done: ReadonlySet<string>,
): PlaybookStep[] {
  return playbook.steps.filter(
    (step) =>
      !done.has(step.id) && step.depends_on.every((parent) => done.has(parent)),
  );
}

export function describeCondition(condition: Condition): string {
  const label = OPERATOR_LABELS[condition.operator] ?? condition.operator;
  if (condition.operator === "exists" || condition.operator === "not_exists") {
    return `${condition.field} ${label}`;
  }
  return `${condition.field} ${label} ${formatValue(condition.value)}`;
}

export function formatValue(value: PlaybookValue | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function coerceVariableInput(
  definition: VariableDefinition,
  input: string,
): PlaybookValue | null {
  const text = input.trim();
  if (!text) return null;
  if (definition.kind === "number") {
    const value = Number(text);
    return Number.isFinite(value) ? value : null;
  }
  if (definition.kind === "boolean") {
    if (["true", "yes", "1", "on"].includes(text.toLocaleLowerCase()))
      return true;
    if (["false", "no", "0", "off"].includes(text.toLocaleLowerCase()))
      return false;
    return null;
  }
  if (definition.kind === "list") {
    return text
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return text;
}

export function valuesFromInputs(
  definitions: readonly VariableDefinition[],
  inputs: Readonly<Record<string, string>>,
): PlaybookValues {
  const values: PlaybookValues = {};
  for (const definition of definitions) {
    const raw = inputs[definition.key];
    if (raw === undefined) continue;
    const value = coerceVariableInput(definition, raw);
    if (value !== null) values[definition.key] = value;
  }
  return values;
}

export function initialInputs(
  definitions: readonly VariableDefinition[],
  target = "",
): Record<string, string> {
  const inputs: Record<string, string> = {};
  for (const definition of definitions) {
    if (definition.key === "target" && target) {
      inputs[definition.key] = target;
      continue;
    }
    inputs[definition.key] = formatValue(definition.default);
  }
  return inputs;
}

export function missingVariables(
  definitions: readonly VariableDefinition[],
  values: PlaybookValues,
): VariableDefinition[] {
  return definitions.filter(
    (definition) =>
      definition.required &&
      (values[definition.key] === undefined ||
        values[definition.key] === "" ||
        values[definition.key] === null),
  );
}

export function referencedVariables(source: string): string[] {
  const matches = source.matchAll(/\{\{\s*([a-zA-Z_][\w.-]*)/g);
  return unique(Array.from(matches, (match) => match[1] ?? "").filter(Boolean));
}

export function unknownVariables(
  playbook: Playbook,
  values: PlaybookValues,
): string[] {
  const declared = new Set(playbook.variables.map((item) => item.key));
  const known = new Set([
    ...declared,
    "target",
    "domain",
    "host",
    "port",
    "user",
  ]);
  const referenced = playbook.steps.flatMap((step) =>
    referencedVariables(
      `${step.command_template} ${step.when.map((item) => item.value ?? "")}`,
    ),
  );
  return referenced.filter(
    (name) => !known.has(name) && values[name] === undefined,
  );
}

export function maskSecrets(
  definitions: readonly VariableDefinition[],
  values: PlaybookValues,
): PlaybookValues {
  const masked: PlaybookValues = { ...values };
  for (const definition of definitions) {
    if (!definition.secret && definition.kind !== "secret") continue;
    if (masked[definition.key] !== undefined) masked[definition.key] = "••••••";
  }
  return masked;
}

export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

export function relativeTime(iso: string): string {
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return iso || "unknown";
  const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(time).toLocaleDateString();
}

export function isSettled(status: StepStatus): boolean {
  return SETTLED.includes(status);
}

export function progressPercent(done: number, total: number): number {
  if (total <= 0) return 100;
  return Math.round((done / total) * 100);
}

export function summarizeRun(run: RunState, plan: RunPlan | null): RunProgress {
  const statuses = Object.values(run.step_status);
  const settled = statuses.filter(isSettled).length;
  const total = plan?.steps.length ?? Math.max(statuses.length, 0);
  return {
    run_id: run.id,
    status: run.status,
    total,
    settled,
    percent: progressPercent(settled, total),
    step_status: run.step_status,
    current_step: run.current_step,
  };
}

export function checklistProgress(
  run: RunState,
  plan: RunPlan | null,
): ChecklistProgress {
  const items: ChecklistProgress["items"] = [];
  const plans = plan?.steps ?? [];
  for (const planned of plans) {
    for (const item of planned.checklist) {
      items.push({
        id: item.id,
        step_id: planned.id,
        title: `${planned.title}: ${item.label}`,
        state: run.checklist[item.id] ?? "pending",
        required: item.required === true,
        note: run.notes[item.id] ?? "",
      });
    }
  }
  const done = items.filter((item) => item.state === "done").length;
  const required = items.filter((item) => item.required);
  return {
    total: items.length,
    done,
    required_total: required.length,
    required_done: required.filter((item) => item.state === "done").length,
    percent: progressPercent(done, items.length),
    items,
  };
}

export function nextAdvice(
  plan: RunPlan | null,
  run: RunState | null,
): StepAdvice | null {
  if (!plan || !run) return null;
  const done = new Set(
    Object.entries(run.step_status)
      .filter(([, status]) => status === "done" || status === "skipped")
      .map(([id]) => id),
  );
  const planned = plan.steps.find(
    (step) =>
      !done.has(step.id) && step.depends_on.every((parent) => done.has(parent)),
  );
  if (!planned) return null;
  return {
    run_id: run.id,
    step_id: planned.id,
    title: planned.title,
    command: planned.command,
    reason: planned.skipped
      ? (planned.reason ?? "Condition not met")
      : "Next ready step",
    checklist: planned.checklist,
    blocked_by: planned.depends_on.filter((parent) => !done.has(parent)),
  };
}

export function groupRecommendations(
  recommendations: readonly Recommendation[],
): Map<Recommendation["kind"], Recommendation[]> {
  const groups = new Map<Recommendation["kind"], Recommendation[]>();
  for (const recommendation of recommendations) {
    const bucket = groups.get(recommendation.kind) ?? [];
    bucket.push(recommendation);
    groups.set(recommendation.kind, bucket);
  }
  for (const bucket of groups.values()) {
    bucket.sort(
      (left, right) =>
        right.score - left.score || left.key.localeCompare(right.key),
    );
  }
  return groups;
}

export function filterSnippets(
  snippets: readonly SnippetRecord[],
  query: string,
  tags: readonly string[] = [],
  library = "",
): SnippetRecord[] {
  const needle = normalizeQuery(query);
  return snippets.filter((snippet) => {
    if (library && snippet.library !== library) return false;
    if (!hasAnyTag(snippet.tags, tags)) return false;
    if (!needle) return true;
    return needle
      .split(/\s+/)
      .every((term) =>
        `${snippet.key} ${snippet.title} ${snippet.command} ${snippet.description}`
          .toLocaleLowerCase()
          .includes(term),
      );
  });
}

export function snippetFamilies(
  snippets: readonly SnippetRecord[],
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const snippet of snippets) {
    const family = snippet.key.split(/[-_]/)[0] || "other";
    counts.set(family, (counts.get(family) ?? 0) + 1);
  }
  return new Map(
    Array.from(counts.entries()).sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
}

export function templateCategories(
  templates: readonly TemplateRecord[],
): string[] {
  return unique(
    templates.map((template) => template.category || "general"),
  ).sort();
}

export function previewTemplate(
  template: TemplateRecord,
  values: PlaybookValues,
): { content: string; unresolved: string[] } {
  const unresolved: string[] = [];
  const content = template.content.replace(
    /\{\{\s*([a-zA-Z_][\w.-]*)[^}]*\}\}/g,
    (match, name: string) => {
      const value = values[name];
      if (value === undefined) {
        unresolved.push(name);
        return match;
      }
      return formatValue(value);
    },
  );
  return { content, unresolved: unique(unresolved) };
}

export function issueText(issues: readonly Issue[]): string {
  if (issues.length === 0) return "No issues";
  return issues.map((issue) => `${issue.code}: ${issue.message}`).join(" · ");
}

export function errorIssues(issues: readonly Issue[]): Issue[] {
  return issues.filter((issue) => issue.severity === "error");
}

export function validateStepDraft(step: PlaybookStep): Issue[] {
  const issues: Issue[] = [];
  if (!step.id.trim())
    issues.push({
      code: "missing-id",
      message: "Step id is required",
      severity: "error",
    });
  if (!step.title.trim())
    issues.push({
      code: "missing-title",
      message: "Step title is required",
      severity: "error",
    });
  if (!step.command_template.trim() && !step.snippet_key) {
    issues.push({
      code: "empty-command",
      message: "Add a command or select a snippet",
      severity: "warning",
    });
  }
  for (const parent of step.depends_on) {
    if (parent === step.id) {
      issues.push({
        code: "self-dependency",
        message: "A step cannot depend on itself",
        severity: "error",
      });
    }
  }
  for (const item of step.checklist) {
    if (!item.label.trim()) {
      issues.push({
        code: "empty-checklist",
        message: `Checklist item ${item.id} has no label`,
        severity: "error",
      });
    }
  }
  return issues;
}

export function validateVariableDraft(definition: VariableDefinition): Issue[] {
  const issues: Issue[] = [];
  if (!definition.key.trim()) {
    issues.push({
      code: "missing-key",
      message: "Variable key is required",
      severity: "error",
    });
  }
  if (!definition.label.trim()) {
    issues.push({
      code: "missing-label",
      message: "Variable label is required",
      severity: "error",
    });
  }
  if (definition.kind === "choice" && definition.choices.length === 0) {
    issues.push({
      code: "missing-choices",
      message: "Choice variables need options",
      severity: "error",
    });
  }
  if (definition.pattern) {
    try {
      new RegExp(definition.pattern);
    } catch {
      issues.push({
        code: "invalid-pattern",
        message: "Pattern is not a valid regex",
        severity: "error",
      });
    }
  }
  return issues;
}

export function validatePlaybookDraft(playbook: Playbook): Issue[] {
  const issues: Issue[] = [];
  if (!playbook.key.trim())
    issues.push({
      code: "missing-key",
      message: "Key is required",
      severity: "error",
    });
  if (!playbook.title.trim())
    issues.push({
      code: "missing-title",
      message: "Title is required",
      severity: "error",
    });
  if (!/^\d+\.\d+\.\d+$/.test(playbook.version)) {
    issues.push({
      code: "invalid-version",
      message: "Use a semantic version",
      severity: "error",
    });
  }
  const ids = new Set<string>();
  for (const step of playbook.steps) {
    if (ids.has(step.id)) {
      issues.push({
        code: "duplicate-step",
        message: `Duplicate step id: ${step.id}`,
        severity: "error",
      });
    }
    ids.add(step.id);
    issues.push(...validateStepDraft(step));
  }
  for (const step of playbook.steps) {
    for (const parent of step.depends_on) {
      if (!ids.has(parent)) {
        issues.push({
          code: "unknown-parent",
          message: `${step.id} depends on unknown step ${parent}`,
          severity: "error",
        });
      }
    }
  }
  for (const definition of playbook.variables)
    issues.push(...validateVariableDraft(definition));
  return issues;
}

export function plannedCommand(
  step: PlannedStep,
  values: PlaybookValues,
): string {
  return referencedVariables(step.command).reduce((command, name) => {
    const value = values[name];
    if (value === undefined) return command;
    const pattern = new RegExp(
      `\\{\\{\\s*${escapeRegExp(name)}\\s*(?:\\|[^}]*)?\\}\\}`,
      "g",
    );
    return command.replace(pattern, formatValue(value));
  }, step.command);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function planWarnings(plan: RunPlan): Issue[] {
  return plan.steps.flatMap((step) => step.warnings);
}

export function planVariables(plan: RunPlan): string[] {
  return unique(plan.steps.flatMap((step) => step.variables)).sort();
}

export function variableKindLabel(kind: VariableKind): string {
  const labels: Record<VariableKind, string> = {
    text: "Text",
    number: "Number",
    boolean: "Boolean",
    choice: "Choice",
    secret: "Secret",
    list: "List",
  };
  return labels[kind];
}

export function stepKindLabel(kind: PlaybookStep["kind"]): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

export function statusLabel(status: PlaybookStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function checklistItemsForStep(
  checklist: readonly ChecklistItem[],
  state: Readonly<Record<string, ChecklistState>>,
): Array<ChecklistItem & { state: ChecklistState }> {
  return checklist.map((item) => ({
    ...item,
    state: state[item.id] ?? "pending",
  }));
}
