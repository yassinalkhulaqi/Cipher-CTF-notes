import {
  forwardRef,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { cx, hashHue, initials, styleVars } from "./componentUtils";

export type AvatarSize = "xs" | "sm" | "md" | "lg";
export type AvatarStatus = "online" | "away" | "offline";

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  name: string;
  src?: string;
  size?: AvatarSize;
  status?: AvatarStatus;
  fallback?: ReactNode;
}

export const Avatar = forwardRef<HTMLSpanElement, AvatarProps>(function Avatar(
  { name, src, size = "md", status, fallback, className, style, ...rest },
  ref,
) {
  const mergedStyle = styleVars({
    ...style,
    "--avatar-hue": hashHue(name),
  }) as CSSProperties;

  return (
    <span
      {...rest}
      ref={ref}
      className={cx("ui-avatar", `ui-avatar--${size}`, className)}
      style={mergedStyle}
      title={name}
    >
      {src ? (
        <img className="ui-avatar__image" src={src} alt={name} />
      ) : (
        (fallback ?? (
          <span className="ui-avatar__initials" aria-hidden="true">
            {initials(name)}
          </span>
        ))
      )}
      {status ? (
        <span className={cx("ui-avatar__status", `is-${status}`)}>
          <span className="ui-avatar__status-label">{status}</span>
        </span>
      ) : null}
    </span>
  );
});

export interface AvatarGroupProps {
  names: string[];
  max?: number;
  size?: AvatarSize;
}

export function AvatarGroup({ names, max = 4, size = "sm" }: AvatarGroupProps) {
  const shown = names.slice(0, max);
  const remaining = names.length - shown.length;
  return (
    <div
      className="ui-avatar-group"
      role="group"
      aria-label={`${names.length} people`}
    >
      {shown.map((name) => (
        <Avatar key={name} name={name} size={size} />
      ))}
      {remaining > 0 ? (
        <span className="ui-avatar-group__overflow">+{remaining}</span>
      ) : null}
    </div>
  );
}
