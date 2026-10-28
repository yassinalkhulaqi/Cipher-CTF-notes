import { useState } from "react";
import {
  Activity,
  Feather,
  Monitor,
  Play,
  Power,
  RotateCcw,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import { AnimatedNumber } from "../../motion/AnimatedNumber";
import { Collapse } from "../../motion/Collapse";
import { Confetti } from "../../motion/Confetti";
import { useMotion } from "../../motion/MotionProvider";
import {
  MOTION_MODE_DETAIL,
  MOTION_MODE_LABEL,
  type MotionMode,
} from "../../motion/preferences";
import { Modal } from "./Modal";

const MODES: { mode: MotionMode; icon: typeof Zap }[] = [
  { mode: "system", icon: Monitor },
  { mode: "full", icon: Sparkles },
  { mode: "subtle", icon: Feather },
  { mode: "off", icon: Power },
];

export function MotionLab() {
  const { mode, setMode, enabled } = useMotion();
  const [replay, setReplay] = useState(0);
  const [count, setCount] = useState(128);
  const [expanded, setExpanded] = useState(true);
  const [burst, setBurst] = useState(0);

  return (
    <Modal
      title="Motion lab"
      subtitle="Feel how the interface moves"
      icon={<Activity />}
      size="wide"
      className="motion-lab"
      label="Motion lab"
      footer={
        <>
          <span className="modal-hint">
            <Timer /> Every animation respects reduced motion
          </span>
          <span className="grow" />
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              setReplay((value) => value + 1);
              setBurst((value) => value + 1);
            }}
          >
            <RotateCcw /> Replay everything
          </button>
        </>
      }
    >
      <div className="motion-lab-body">
        <section className="settings-section">
          <div className="settings-head">
            <h3>Intensity</h3>
            <p>{MOTION_MODE_DETAIL[mode]}</p>
          </div>
          <div className="motion-mode-grid">
            {MODES.map(({ mode: value, icon: Icon }) => (
              <button
                key={value}
                type="button"
                className={`motion-mode ${mode === value ? "selected" : ""}`}
                onClick={() => setMode(value)}
              >
                <span className="motion-mode-icon">
                  <Icon />
                </span>
                <strong>{MOTION_MODE_LABEL[value]}</strong>
                <small>{MOTION_MODE_DETAIL[value]}</small>
              </button>
            ))}
          </div>
          {!enabled ? (
            <div className="motion-paused">
              <Power />
              Motion is paused. Demos below show their final state.
            </div>
          ) : null}
        </section>

        <div className="motion-demo-grid">
          <section className="motion-demo" data-tilt>
            <header>
              <div>
                <h3>Spring stagger</h3>
                <span>Orchestrated entrances</span>
              </div>
              <Zap />
            </header>
            <div key={replay} className="demo-stagger">
              {Array.from({ length: 6 }, (_, index) => (
                <span key={index} className="demo-pill">
                  {String(index + 1).padStart(2, "0")}
                </span>
              ))}
            </div>
            <button
              type="button"
              className="btn ghost tiny"
              onClick={() => setReplay((value) => value + 1)}
            >
              <Play /> Replay
            </button>
          </section>

          <section className="motion-demo" data-tilt>
            <header>
              <div>
                <h3>Counter</h3>
                <span>Spring-interpolated numbers</span>
              </div>
              <Activity />
            </header>
            <div className="demo-counter">
              <AnimatedNumber value={count} />
              <span>findings</span>
            </div>
            <div className="demo-counter-actions">
              <button
                type="button"
                className="btn ghost tiny"
                onClick={() => setCount((value) => Math.max(0, value - 17))}
              >
                −17
              </button>
              <button
                type="button"
                className="btn primary tiny"
                onClick={() => setCount((value) => value + 17)}
              >
                +17
              </button>
            </div>
          </section>

          <section className="motion-demo" data-tilt>
            <header>
              <div>
                <h3>Collapse</h3>
                <span>Height that breathes</span>
              </div>
              <Feather />
            </header>
            <button
              type="button"
              className="btn ghost tiny"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Collapse panel" : "Expand panel"}
            </button>
            <Collapse open={expanded}>
              <p className="demo-copy">
                Layout changes should feel physical. This panel interpolates its
                height on the compositor-friendly grid track rhythm.
              </p>
            </Collapse>
          </section>

          <section className="motion-demo" data-tilt>
            <header>
              <div>
                <h3>Confetti burst</h3>
                <span>Celebrate captured flags</span>
              </div>
              <Sparkles />
            </header>
            <p className="demo-copy">
              A short, GPU-friendly particle burst with gravity and fade. Press
              the button to fire.
            </p>
            <button
              type="button"
              className="btn primary tiny"
              onClick={() => setBurst((value) => value + 1)}
            >
              <Sparkles /> Fire
            </button>
          </section>
        </div>

        <p className="motion-lab-note">
          Motion is tuned with spring physics, then scaled down for subtle mode
          and removed entirely for reduced motion. The preference is stored on
          this machine only.
        </p>
      </div>
      <Confetti fire={burst} />
    </Modal>
  );
}
