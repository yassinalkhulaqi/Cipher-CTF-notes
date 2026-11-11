import { useEffect, useState } from "react";
import { api } from "../lib/api";

/**
 * Fetch the vault's tag list (names only) for autocomplete suggestions.
 * Shared by every tag-editing surface so they stay consistent and fetch once.
 */
export function useTagSuggestions(): string[] {
  const [tags, setTags] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .tagCounts()
      .then((items) => {
        if (!cancelled) setTags(items.map((item) => item.tag));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return tags;
}
