/** Digest card with jumpable highlights. */

import { digestCardData, formatCount } from "../format";
import type { Digest, JumpTarget } from "../types";

export interface DigestCardProps {
  digest: Digest;
  onJump: (target: JumpTarget) => void;
  onSelect: (sequence: number) => void;
}

export function DigestCard({ digest, onJump, onSelect }: DigestCardProps) {
  const card = digestCardData(digest);
  return (
    <article className="activity-digest" data-period={digest.period}>
      <header className="activity-digest__header">
        <h3>{card.title}</h3>
        <span className="activity-digest__count">{card.count} events</span>
      </header>
      <p className="activity-digest__subtitle">{card.subtitle || "No kinds recorded"}</p>
      <div className="activity-digest__actors">
        {Object.keys(digest.actor_counts)
          .sort((left, right) => digest.actor_counts[right] - digest.actor_counts[left])
          .slice(0, 4)
          .map((actor) => (
            <span key={actor} className="activity-digest__actor">
              {actor} · {formatCount(digest.actor_counts[actor])}
            </span>
          ))}
      </div>
      <ul className="activity-digest__highlights">
        {card.highlights.map((entry) => (
          <li key={entry.sequence}>
            <button type="button" className="activity-digest__highlight" onClick={() => onSelect(entry.sequence)}>
              <span className="activity-digest__severity">{entry.severity}</span>
              {entry.title}
            </button>
            {entry.jump?.resolvable && (
              <button
                type="button"
                className="activity-digest__jump"
                onClick={() => onJump(entry.jump as JumpTarget)}
              >
                Jump
              </button>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}
