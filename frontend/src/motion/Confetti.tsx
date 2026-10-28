import { useEffect, useRef } from "react";
import { useMotion } from "./MotionProvider";

interface ConfettiProps {
  fire: number;
  origin?: { x: number; y: number } | null;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  rotation: number;
  spin: number;
  color: string;
  life: number;
  maxLife: number;
  shape: "rect" | "circle";
}

const COLORS = [
  "#f05248",
  "#e7a354",
  "#52c9a0",
  "#78a7f7",
  "#b59df7",
  "#e6b450",
];

export function Confetti({ fire, origin }: ConfettiProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { enabled, scale } = useMotion();

  useEffect(() => {
    if (!fire || !enabled) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const startX = origin?.x ?? window.innerWidth / 2;
    const startY = origin?.y ?? window.innerHeight * 0.28;
    const total = Math.round(52 * Math.max(scale, 0.5));
    const particles: Particle[] = Array.from({ length: total }, () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2.2 + Math.random() * 5.4;
      return {
        x: startX + (Math.random() - 0.5) * 24,
        y: startY + (Math.random() - 0.5) * 14,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 2.4,
        size: 3 + Math.random() * 5,
        rotation: Math.random() * Math.PI,
        spin: (Math.random() - 0.5) * 0.24,
        color: COLORS[(Math.random() * COLORS.length) | 0] ?? COLORS[0],
        life: 0,
        maxLife: 58 + Math.random() * 36,
        shape: Math.random() > 0.35 ? "rect" : "circle",
      };
    });

    const started = performance.now();
    const duration = 1500;
    let frame = 0;

    const tick = (now: number) => {
      const elapsed = now - started;
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
      for (const particle of particles) {
        particle.life += 1;
        particle.vy += 0.14;
        particle.vx *= 0.992;
        particle.vy *= 0.992;
        particle.x += particle.vx;
        particle.y += particle.vy;
        particle.rotation += particle.spin;
        const alpha = Math.max(0, 1 - particle.life / particle.maxLife);
        context.save();
        context.globalAlpha = alpha;
        context.translate(particle.x, particle.y);
        context.rotate(particle.rotation);
        context.fillStyle = particle.color;
        if (particle.shape === "circle") {
          context.beginPath();
          context.arc(0, 0, particle.size / 2, 0, Math.PI * 2);
          context.fill();
        } else {
          context.fillRect(
            -particle.size / 2,
            -particle.size / 4,
            particle.size,
            particle.size / 2,
          );
        }
        context.restore();
      }
      if (elapsed < duration) {
        frame = window.requestAnimationFrame(tick);
      } else {
        context.clearRect(0, 0, window.innerWidth, window.innerHeight);
      }
    };

    frame = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    };
  }, [fire, enabled, origin, scale]);

  return <canvas ref={canvasRef} className="confetti-canvas" aria-hidden="true" />;
}
