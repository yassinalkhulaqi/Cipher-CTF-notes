/** Graph canvas that projects nodes in idle chunks instead of one long frame. */

import { useEffect, useState } from "react";

import { DeferredQueue, graphNodeTask, scheduleDeferred, shouldDefer } from "./deferredGraph";

export interface DeferredGraphProps {
  nodes: readonly string[];
  ready?: boolean;
  maxCost?: number;
  threshold?: number;
  emptyLabel?: string;
}

export function DeferredGraph({
  nodes,
  ready = true,
  maxCost = 12,
  threshold = 120,
  emptyLabel = "Graph renders after the tree is interactive",
}: DeferredGraphProps) {
  const [rendered, setRendered] = useState<string[]>([]);
  const deferred = shouldDefer(nodes.length, threshold);

  useEffect(() => {
    setRendered([]);
    if (!ready || nodes.length === 0) return;
    const queue = new DeferredQueue<{ id: string }>(maxCost);
    queue.enqueueAll(nodes.map((node) => graphNodeTask(node)));
    let cancelled = false;
    let cancel: () => void = () => undefined;
    const step = () => {
      if (cancelled) return;
      const chunk = queue.take();
      if (!chunk) return;
      const ids = chunk.tasks.map((task) => task.payload.id);
      setRendered((current) => [...current, ...ids]);
      if (!queue.done) cancel = scheduleDeferred(step, 0);
    };
    cancel = scheduleDeferred(step, 0);
    return () => {
      cancelled = true;
      cancel();
    };
  }, [nodes, ready, maxCost]);

  const isReady = ready && (!deferred || rendered.length >= nodes.length);
  return (
    <div className="perf-deferred-graph" data-ready={isReady} data-deferred={deferred}>
      {!isReady ? (
        <span>{emptyLabel}</span>
      ) : (
        <div className="perf-deferred-graph__layer" aria-label="Deferred graph layer">
          {rendered.map((node) => (
            <span className="perf-deferred-graph__node" key={node} data-node={node} />
          ))}
        </div>
      )}
    </div>
  );
}
