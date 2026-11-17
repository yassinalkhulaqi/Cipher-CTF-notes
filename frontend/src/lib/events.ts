/**
 * Typed cross-component events for the Aurora shell.
 *
 * The app previously scattered stringly-typed `window.dispatchEvent` /
 * `addEventListener` pairs across six files. This module is the single
 * source of truth for the event names and their payload types.
 */

export const APP_EVENTS = {
  snippetsChanged: "redscribe:snippets-changed",
  insertSnippet: "redscribe:insert-snippet",
  focusFilter: "redscribe:focus-filter",
} as const;

export type AppEventName = (typeof APP_EVENTS)[keyof typeof APP_EVENTS];

interface InsertSnippetDetail {
  text: string;
}

export function snippetsChanged(): void {
  window.dispatchEvent(new Event(APP_EVENTS.snippetsChanged));
}

export function insertSnippet(text: string): void {
  window.dispatchEvent(
    new CustomEvent<InsertSnippetDetail>(APP_EVENTS.insertSnippet, {
      detail: { text },
    }),
  );
}

export function focusFilter(): void {
  window.dispatchEvent(new Event(APP_EVENTS.focusFilter));
}

export function onSnippetsChanged(handler: () => void): () => void {
  window.addEventListener(APP_EVENTS.snippetsChanged, handler);
  return () => window.removeEventListener(APP_EVENTS.snippetsChanged, handler);
}

export function onInsertSnippet(handler: (text: string) => void): () => void {
  const listener = (event: Event) => {
    const detail = (event as CustomEvent<InsertSnippetDetail>).detail;
    if (detail && typeof detail.text === "string") handler(detail.text);
  };
  window.addEventListener(APP_EVENTS.insertSnippet, listener);
  return () => window.removeEventListener(APP_EVENTS.insertSnippet, listener);
}

export function onFocusFilter(handler: () => void): () => void {
  window.addEventListener(APP_EVENTS.focusFilter, handler);
  return () => window.removeEventListener(APP_EVENTS.focusFilter, handler);
}
