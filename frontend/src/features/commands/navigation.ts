/** Navigation graph with deterministic shortest-path breadcrumbs. */

import type { CommandContext, NavNode, NavPath } from "./types";

export class NavigationGraph {
  private readonly nodes = new Map<string, NavNode>();
  private readonly edges: Array<{
    source: string;
    target: string;
    cost: number;
  }> = [];

  addNode(node: NavNode): NavNode {
    this.nodes.set(node.id, node);
    return node;
  }

  addEdge(source: string, target: string, cost = 1): void {
    if (!this.nodes.has(source) || !this.nodes.has(target)) {
      throw new Error("Navigation edge endpoints must exist");
    }
    if (source === target)
      throw new Error("Navigation edge cannot be self-referential");
    if (cost <= 0) throw new Error("Navigation edge cost must be positive");
    this.edges.push({ source, target, cost });
  }

  has(id: string): boolean {
    return this.nodes.has(id);
  }

  node(id: string): NavNode {
    const node = this.nodes.get(id);
    if (!node) throw new Error(`Unknown navigation node: ${id}`);
    return node;
  }

  children(id: string): NavNode[] {
    this.node(id);
    const targets = new Set(
      this.edges
        .filter((edge) => edge.source === id)
        .map((edge) => edge.target),
    );
    return Array.from(targets)
      .map((target) => this.node(target))
      .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  }

  parents(id: string): NavNode[] {
    this.node(id);
    const sources = new Set(
      this.edges
        .filter((edge) => edge.target === id)
        .map((edge) => edge.source),
    );
    return Array.from(sources)
      .map((source) => this.node(source))
      .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  }

  path(start: string, goal: string): NavPath {
    this.node(start);
    this.node(goal);
    if (start === goal) return { nodes: [start], cost: 0 };
    const distances = new Map<string, number>([[start, 0]]);
    const previous = new Map<string, string>();
    const queue: Array<[number, string]> = [[0, start]];
    while (queue.length) {
      queue.sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
      const [distance, current] = queue.shift() as [number, string];
      if (distance > (distances.get(current) ?? Infinity)) continue;
      if (current === goal) break;
      for (const edge of this.edges
        .filter((item) => item.source === current)
        .sort((a, b) => a.target.localeCompare(b.target))) {
        const candidate = distance + edge.cost;
        if (candidate < (distances.get(edge.target) ?? Infinity)) {
          distances.set(edge.target, candidate);
          previous.set(edge.target, current);
          queue.push([candidate, edge.target]);
        }
      }
    }
    if (!distances.has(goal))
      throw new Error(`No path from '${start}' to '${goal}'`);
    const nodes = [goal];
    while (nodes[0] !== start) {
      const parent = previous.get(nodes[0]);
      if (!parent) throw new Error(`No path from '${start}' to '${goal}'`);
      nodes.unshift(parent);
    }
    return { nodes, cost: distances.get(goal) as number };
  }

  breadcrumbs(goal: string, root = "vault"): NavNode[] {
    return this.path(root, goal).nodes.map((id) => this.node(id));
  }

  subtree(id: string): NavNode[] {
    this.node(id);
    const seen = new Set<string>([id]);
    const ordered: NavNode[] = [];
    const queue = [id];
    while (queue.length) {
      const current = queue.shift() as string;
      for (const child of this.children(current)) {
        if (seen.has(child.id)) continue;
        seen.add(child.id);
        ordered.push(child);
        queue.push(child.id);
      }
    }
    return ordered;
  }

  neighbors(id: string, limit = 8): NavNode[] {
    if (limit < 1) throw new Error("limit must be positive");
    const related = new Set(
      [...this.parents(id), ...this.children(id)].map((node) => node.id),
    );
    return Array.from(related)
      .map((target) => this.node(target))
      .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
      .slice(0, limit);
  }

  forContext(context: CommandContext): NavNode[] {
    const refs = [
      context.entity?.ref,
      ...context.selection.map((item) => item.ref),
    ].filter((ref): ref is string => Boolean(ref));
    return refs.filter((ref) => this.has(ref)).map((ref) => this.node(ref));
  }
}

export function defaultNavigation(): NavigationGraph {
  const graph = new NavigationGraph();
  const nodes: NavNode[] = [
    {
      id: "vault",
      label: "Vault",
      kind: "place",
      parent: "",
      order: 0,
      entity: null,
    },
    {
      id: "pane:main",
      label: "Main workspace",
      kind: "place",
      parent: "vault",
      order: 10,
      entity: null,
    },
    {
      id: "pane:secondary",
      label: "Secondary workspace",
      kind: "place",
      parent: "vault",
      order: 20,
      entity: null,
    },
    {
      id: "folder:engagements",
      label: "Engagements",
      kind: "folder",
      parent: "vault",
      order: 30,
      entity: null,
    },
    {
      id: "findings",
      label: "Findings",
      kind: "place",
      parent: "vault",
      order: 40,
      entity: null,
    },
    {
      id: "evidence",
      label: "Evidence",
      kind: "place",
      parent: "vault",
      order: 50,
      entity: null,
    },
    {
      id: "reports",
      label: "Reports",
      kind: "place",
      parent: "vault",
      order: 60,
      entity: null,
    },
  ];
  nodes.forEach((node) => graph.addNode(node));
  for (const child of nodes.slice(1)) graph.addEdge("vault", child.id);
  graph.addEdge("folder:engagements", "findings");
  return graph;
}
