import { useCallback, useEffect, useRef, useState } from "react";

export type AnnouncementPoliteness = "polite" | "assertive";

export interface UseAnnouncer {
  message: string;
  politeness: AnnouncementPoliteness;
  announce: (message: string, politeness?: AnnouncementPoliteness) => void;
  clear: () => void;
}

/**
 * Produces screen-reader announcements through a live region. The message is
 * cleared first so repeated, identical strings are still spoken.
 */
export function useAnnouncer(): UseAnnouncer {
  const [message, setMessage] = useState("");
  const [politeness, setPoliteness] =
    useState<AnnouncementPoliteness>("polite");
  const timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clear = useCallback((): void => {
    if (timeout.current !== undefined) {
      clearTimeout(timeout.current);
      timeout.current = undefined;
    }
    setMessage("");
  }, []);

  const announce = useCallback(
    (next: string, level: AnnouncementPoliteness = "polite"): void => {
      if (timeout.current !== undefined) clearTimeout(timeout.current);
      setPoliteness(level);
      setMessage("");
      timeout.current = setTimeout(() => {
        setMessage(next);
        timeout.current = undefined;
      }, 50);
    },
    [],
  );

  useEffect(() => clear, [clear]);

  return { message, politeness, announce, clear };
}
