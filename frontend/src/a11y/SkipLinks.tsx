import { type MouseEvent } from "react";

export interface SkipLinkTarget {
  id: string;
  label: string;
}

const hiddenStyle = {
  position: "absolute",
  left: 0,
  top: 0,
  transform: "translateY(-150%)",
  zIndex: 1000,
} as const;

/** Keyboard-first skip navigation that moves focus to the target region. */
export function SkipLinks({ targets }: { targets: SkipLinkTarget[] }) {
  const activate = (event: MouseEvent<HTMLAnchorElement>, id: string): void => {
    event.preventDefault();
    const target = document.getElementById(id);
    if (!target) return;
    target.setAttribute("tabindex", "-1");
    target.focus();
    target.scrollIntoView({ block: "start" });
  };

  return (
    <nav aria-label="Skip links" className="a11y-skip-links">
      {targets.map((target) => (
        <a
          key={target.id}
          href={`#${target.id}`}
          className="a11y-skip-link"
          style={hiddenStyle}
          onClick={(event) => activate(event, target.id)}
        >
          {target.label}
        </a>
      ))}
    </nav>
  );
}
