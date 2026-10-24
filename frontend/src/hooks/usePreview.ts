import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface PreviewState {
  html: string;
  pending: boolean;
}

export function usePreview(content: string, enabled: boolean): PreviewState {
  const [state, setState] = useState<PreviewState>({
    html: "",
    pending: false,
  });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((current) => ({ ...current, pending: true }));
    const timer = setTimeout(() => {
      api
        .renderPreview(content)
        .then((result) => {
          if (!cancelled) setState({ html: result.html, pending: false });
        })
        .catch(() => {
          if (!cancelled)
            setState((current) => ({ ...current, pending: false }));
        });
    }, 320);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [content, enabled]);

  return state;
}
