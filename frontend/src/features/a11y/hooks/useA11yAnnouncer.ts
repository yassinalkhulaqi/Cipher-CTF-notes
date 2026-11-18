import { useCallback } from "react";
import { useA11yStore } from "../store";
import type { Politeness } from "../types";

export function useA11yAnnouncer() {
  const announcements = useA11yStore((state) => state.announcements);
  const announceAction = useA11yStore((state) => state.announce);
  const dismissAction = useA11yStore((state) => state.dismissAnnouncement);
  const clearAction = useA11yStore((state) => state.clearAnnouncements);

  const announce = useCallback(
    (message: string, politeness: Politeness = "polite") =>
      announceAction(message, politeness),
    [announceAction],
  );
  const dismiss = useCallback(
    (id: string) => dismissAction(id),
    [dismissAction],
  );
  const clear = useCallback(() => clearAction(), [clearAction]);

  return { announcements, announce, dismiss, clear };
}
