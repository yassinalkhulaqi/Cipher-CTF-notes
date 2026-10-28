import { useMotion } from "./MotionProvider";

export function Aurora() {
  const { enabled } = useMotion();
  if (!enabled) return null;
  return (
    <div className="aurora-field" aria-hidden="true">
      <span className="aurora-orb aurora-orb-a" />
      <span className="aurora-orb aurora-orb-b" />
      <span className="aurora-orb aurora-orb-c" />
    </div>
  );
}
