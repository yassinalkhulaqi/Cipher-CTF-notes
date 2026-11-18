import { PlaybooksClient } from "./client";
import { PlaybookDetail } from "./PlaybookDetail";
import { PlaybookList } from "./PlaybookList";
import { usePlaybooks } from "./usePlaybooks";

export interface PlaybooksFeatureProps {
  client?: PlaybooksClient;
}

export function PlaybooksFeature({ client }: PlaybooksFeatureProps) {
  const controller = usePlaybooks(client ?? new PlaybooksClient());
  return (
    <div className="pb-feature">
      <aside className="pb-feature__sidebar">
        {controller.loading ? (
          <p className="pb-muted">Loading playbooks…</p>
        ) : null}
        <PlaybookList controller={controller} />
      </aside>
      <main className="pb-feature__main">
        <PlaybookDetail controller={controller} />
      </main>
    </div>
  );
}
