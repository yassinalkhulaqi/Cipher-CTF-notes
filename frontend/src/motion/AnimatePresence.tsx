import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { motionDuration } from "./preferences";

interface PresenceEntry<T> {
  key: string;
  item: T;
  exiting: boolean;
}

interface AnimatePresenceProps<T> {
  items: readonly T[];
  getKey: (item: T) => string | number;
  children: (item: T, state: { exiting: boolean }) => ReactNode;
  exitMs?: number;
}

export function AnimatePresence<T>({
  items,
  getKey,
  children,
  exitMs = 220,
}: AnimatePresenceProps<T>) {
  const getKeyRef = useRef(getKey);
  getKeyRef.current = getKey;
  const [rendered, setRendered] = useState<PresenceEntry<T>[]>(() =>
    items.map((item) => ({
      key: String(getKey(item)),
      item,
      exiting: false,
    })),
  );
  const timers = useRef(new Map<string, number>());

  const remove = useCallback((key: string) => {
    timers.current.delete(key);
    setRendered((current) => current.filter((entry) => entry.key !== key));
  }, []);

  useEffect(() => {
    const keyOf = getKeyRef.current;
    const keys = new Set(items.map((item) => String(keyOf(item))));
    setRendered((current) => {
      const existing = new Map(current.map((entry) => [entry.key, entry]));
      const next: PresenceEntry<T>[] = [];
      for (const item of items) {
        const key = String(keyOf(item));
        const prior = existing.get(key);
        existing.delete(key);
        const timer = timers.current.get(key);
        if (timer !== undefined) {
          window.clearTimeout(timer);
          timers.current.delete(key);
        }
        next.push({
          key,
          item: prior ? prior.item : item,
          exiting: false,
        });
      }
      for (const stale of existing.values()) {
        next.push({ ...stale, exiting: true });
        if (!timers.current.has(stale.key)) {
          const timer = window.setTimeout(
            () => remove(stale.key),
            motionDuration(exitMs),
          );
          timers.current.set(stale.key, timer);
        }
      }
      return next;
    });
    for (const [key, timer] of timers.current) {
      if (!keys.has(key)) continue;
      window.clearTimeout(timer);
      timers.current.delete(key);
    }
  }, [items, exitMs, remove]);

  useEffect(() => {
    const store = timers.current;
    return () => {
      for (const timer of store.values()) window.clearTimeout(timer);
      store.clear();
    };
  }, []);

  return (
    <>
      {rendered.map((entry) => (
        <Fragment key={entry.key}>
          {children(entry.item, { exiting: entry.exiting })}
        </Fragment>
      ))}
    </>
  );
}
