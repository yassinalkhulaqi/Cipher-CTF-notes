/** Pure DAG algorithms used by the editor and the keyboard runner. */

import type { DagCompilation, StepDef, ValidationIssue } from "./types";
import { issue } from "./types";

export function dependencyGraph(steps: StepDef[]): Record<string, string[]> {
  const graph: Record<string, string[]> = {};
  for (const step of steps) {
    graph[step.id] = Array.from(
      new Set([...(graph[step.id] ?? []), ...(step.depends_on ?? [])]),
    )
      .filter((dependency) => dependency !== step.id)
      .sort();
  }
  return graph;
}

function visit(
  node: string,
  graph: Record<string, string[]>,
  color: Record<string, number>,
  stack: string[],
  found: Set<string>,
  cycles: string[][],
): void {
  color[node] = 1;
  stack.push(node);
  for (const dependency of graph[node] ?? []) {
    if (!(dependency in graph)) continue;
    const state = color[dependency] ?? 0;
    if (state === 0) {
      visit(dependency, graph, color, stack, found, cycles);
    } else if (state === 1) {
      const cycle = [...stack.slice(stack.indexOf(dependency)), dependency];
      const reversed = [cycle[0], ...cycle.slice(1).reverse()];
      const canonical =
        JSON.stringify(cycle) < JSON.stringify(reversed) ? cycle : reversed;
      const key = JSON.stringify(canonical);
      if (!found.has(key)) {
        found.add(key);
        cycles.push(cycle);
      }
    }
  }
  stack.pop();
  color[node] = 2;
}

export function detectCycles(graph: Record<string, string[]>): string[][] {
  const color: Record<string, number> = {};
  const stack: string[] = [];
  const found = new Set<string>();
  const cycles: string[][] = [];
  for (const node of Object.keys(graph).sort()) {
    if ((color[node] ?? 0) === 0)
      visit(node, graph, color, stack, found, cycles);
  }
  return cycles.sort((a, b) =>
    JSON.stringify(a).localeCompare(JSON.stringify(b)),
  );
}

export function topologicalOrder(graph: Record<string, string[]>): string[] {
  const nodes = Object.keys(graph);
  const dependents: Record<string, string[]> = Object.fromEntries(
    nodes.map((node) => [node, []]),
  );
  const indegree: Record<string, number> = Object.fromEntries(
    nodes.map((node) => [node, 0]),
  );
  for (const node of nodes) {
    for (const dependency of graph[node] ?? []) {
      if (dependency in indegree) {
        dependents[dependency].push(node);
        indegree[node] += 1;
      }
    }
  }
  const queue = nodes.filter((node) => indegree[node] === 0).sort();
  const order: string[] = [];
  while (queue.length) {
    const node = queue.shift() as string;
    order.push(node);
    for (const dependent of dependents[node].sort()) {
      indegree[dependent] -= 1;
      if (indegree[dependent] === 0) {
        queue.push(dependent);
        queue.sort();
      }
    }
  }
  if (order.length !== nodes.length)
    throw new Error("Step graph contains a cycle");
  return order;
}

export function parallelLayers(graph: Record<string, string[]>): string[][] {
  const remaining: Record<string, string[]> = { ...graph };
  const layers: string[][] = [];
  while (Object.keys(remaining).length) {
    const ready = Object.keys(remaining)
      .filter((node) =>
        (remaining[node] ?? []).every(
          (dependency) => !(dependency in remaining),
        ),
      )
      .sort();
    if (!ready.length) break;
    layers.push(ready);
    for (const node of ready) delete remaining[node];
  }
  return layers;
}

export function nextReady(
  order: string[],
  graph: Record<string, string[]>,
  completed: string[],
): string[] {
  const done = new Set(completed);
  return order.filter(
    (node) =>
      !done.has(node) &&
      (graph[node] ?? []).every((dependency) => done.has(dependency)),
  );
}

export function compileDag(steps: StepDef[]): DagCompilation {
  const ids = steps.map((step) => step.id);
  const counts = new Map<string, number>();
  for (const id of ids) counts.set(id, (counts.get(id) ?? 0) + 1);
  const duplicates = Array.from(counts.entries())
    .filter(([, count]) => count > 1)
    .map(([id]) => id)
    .sort();
  const graph = dependencyGraph(steps);
  const known = new Set(ids);
  const missing = Array.from(
    new Set(
      Object.values(graph)
        .flat()
        .filter((dependency) => !known.has(dependency)),
    ),
  ).sort();
  const selfDependencies = steps
    .filter((step) => (step.depends_on ?? []).includes(step.id))
    .map((step) => step.id)
    .sort();
  const cycles = detectCycles(graph);
  const problems: ValidationIssue[] = [];
  if (duplicates.length) {
    problems.push(
      issue(
        "duplicate_step",
        `Duplicate step ids: ${duplicates.join(", ")}`,
        "steps",
      ),
    );
  }
  if (missing.length) {
    problems.push(
      issue(
        "missing_dependency",
        `Unknown dependencies: ${missing.join(", ")}`,
        "steps",
      ),
    );
  }
  if (selfDependencies.length) {
    problems.push(
      issue(
        "self_dependency",
        `Steps cannot depend on themselves: ${selfDependencies.join(", ")}`,
        "steps",
      ),
    );
  }
  for (const cycle of cycles) {
    problems.push(
      issue(
        "cycle_detected",
        `Cycle: ${cycle.join(" -> ")}`,
        "steps.depends_on",
      ),
    );
  }
  const outputs = steps
    .map((step) => step.output)
    .filter((value): value is string => Boolean(value));
  const repeatedOutputs = Array.from(
    new Set(outputs.filter((value, index) => outputs.indexOf(value) !== index)),
  ).sort();
  if (repeatedOutputs.length) {
    problems.push(
      issue(
        "duplicate_output",
        `Output names must be unique: ${repeatedOutputs.join(", ")}`,
        "steps.output",
      ),
    );
  }
  const valid =
    !duplicates.length && !missing.length && !cycles.length && !problems.length;
  let order: string[] = [];
  let layers: string[][] = [];
  let criticalPath: string[] = [];
  const depth: Record<string, number> = {};
  if (valid) {
    order = topologicalOrder(graph);
    layers = parallelLayers(graph);
    for (const node of order) {
      depth[node] =
        1 +
        Math.max(
          0,
          ...(graph[node] ?? [])
            .filter((item) => item in depth)
            .map((item) => depth[item]),
        );
    }
    let end = order[0] ?? "";
    for (const node of order) {
      if ((depth[node] ?? 0) >= (depth[end] ?? 0)) end = node;
    }
    const chain: string[] = [];
    let cursor: string | undefined = end;
    while (cursor && !chain.includes(cursor)) {
      chain.unshift(cursor);
      const parents: string[] = (graph[cursor] ?? []).filter(
        (parent: string) => parent in depth,
      );
      cursor = parents.sort(
        (a: string, b: string) => (depth[b] ?? 0) - (depth[a] ?? 0),
      )[0];
    }
    criticalPath = chain;
  }
  return {
    order,
    layers,
    cycles,
    duplicates,
    missing,
    self_dependencies: selfDependencies,
    critical_path: criticalPath,
    depth,
    issues: problems,
    ok: valid,
  };
}

export interface ConnectResult {
  steps: StepDef[];
  accepted: boolean;
  problem: ValidationIssue | null;
}

/** Apply a drag-created dependency without mutating the input array. */
export function connectSteps(
  steps: StepDef[],
  source: string,
  target: string,
): ConnectResult {
  const reject = (code: string, message: string): ConnectResult => ({
    steps,
    accepted: false,
    problem: issue(code, message, `steps.${target}.depends_on`),
  });
  if (source === target)
    return reject("self_dependency", "A step cannot depend on itself");
  const ids = new Set(steps.map((step) => step.id));
  if (!ids.has(source) || !ids.has(target)) {
    return reject(
      "unknown_step",
      "Both ends of a connection must be existing steps",
    );
  }
  const updated = steps.map((step) =>
    step.id === target
      ? {
          ...step,
          depends_on: Array.from(new Set([...(step.depends_on ?? []), source])),
        }
      : step,
  );
  if (detectCycles(dependencyGraph(updated)).length) {
    return reject(
      "cycle_detected",
      `Connecting ${source} to ${target} would create a cycle`,
    );
  }
  return { steps: updated, accepted: true, problem: null };
}

export interface DagNodeLayout {
  step: StepDef;
  column: number;
  row: number;
  depth: number;
}

/** Deterministic column/row placement for the DAG editor canvas. */
export function layoutDag(steps: StepDef[]): DagNodeLayout[] {
  const compilation = compileDag(steps);
  const columns = new Map<string, number>();
  const rows = new Map<string, number>();
  for (const layer of compilation.layers) {
    const column = layersColumn(layer, columns);
    layer.forEach((node, index) => {
      columns.set(node, column);
      rows.set(node, index);
    });
  }
  return steps.map((step) => ({
    step,
    column: columns.get(step.id) ?? 0,
    row: rows.get(step.id) ?? 0,
    depth: compilation.depth[step.id] ?? 0,
  }));
}

function layersColumn(layer: string[], columns: Map<string, number>): number {
  if (!layer.length) return 0;
  const parents = layer
    .flatMap((node) => columns.get(node) ?? -1)
    .filter((value) => value >= 0);
  return parents.length
    ? Math.max(...parents) + 1
    : columns.size
      ? Math.max(...columns.values()) + 1
      : 0;
}

export function edgesFor(
  steps: StepDef[],
): Array<{ from: string; to: string }> {
  const edges: Array<{ from: string; to: string }> = [];
  for (const step of steps) {
    for (const dependency of step.depends_on ?? [])
      edges.push({ from: dependency, to: step.id });
  }
  return edges.sort((a, b) =>
    `${a.from}>${a.to}`.localeCompare(`${b.from}>${b.to}`),
  );
}
