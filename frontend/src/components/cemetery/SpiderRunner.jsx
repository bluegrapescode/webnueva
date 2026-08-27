import React, { useEffect, useRef, useState } from "react";
import { motion, useAnimationControls } from "framer-motion";

// A creepy spider that scuttles across the whole screen in a DIFFERENT random
// direction every few minutes, then vanishes off-screen until the next run.
const INTERVAL_MS = 6 * 60 * 1000; // cada 6 minutos
const FIRST_RUN_MS = 8000;         // primera aparición a los 8s

// Route builders -> {sx, sy, ex, ey} just off the viewport edges.
function buildRoutes(w, h) {
  const rx = () => 40 + Math.random() * (w - 80);
  const ry = () => h * 0.18 + Math.random() * h * 0.6;
  const M = 70;
  return [
    () => ({ sx: -M, sy: ry(), ex: w + M, ey: ry() }),               // →
    () => ({ sx: w + M, sy: ry(), ex: -M, ey: ry() }),               // ←
    () => ({ sx: -M, sy: -M, ex: w + M, ey: h + M }),                // ↘
    () => ({ sx: w + M, sy: h + M, ex: -M, ey: -M }),                // ↖
    () => ({ sx: w + M, sy: -M, ex: -M, ey: h + M }),                // ↙
    () => ({ sx: -M, sy: h + M, ex: w + M, ey: -M }),                // ↗
    () => ({ sx: rx(), sy: -M, ex: rx(), ey: h + M }),               // ↓
    () => ({ sx: rx(), sy: h + M, ex: rx(), ey: -M }),               // ↑
  ];
}

const Spider = () => (
  <svg width="46" height="46" viewBox="-24 -24 48 48" aria-hidden>
    {/* legs — two groups scuttling out of phase */}
    <g stroke="#0c110a" strokeWidth="2" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleA 0.18s ease-in-out infinite" }}>
      <path d="M-4 -8 L-14 -16 L-21 -11" />
      <path d="M-5 -3 L-16 -7 L-23 -2" />
      <path d="M-5 2 L-16 3 L-23 9" />
      <path d="M-4 6 L-13 12 L-19 19" />
    </g>
    <g stroke="#0c110a" strokeWidth="2" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleB 0.18s ease-in-out infinite" }}>
      <path d="M4 -8 L14 -16 L21 -11" />
      <path d="M5 -3 L16 -7 L23 -2" />
      <path d="M5 2 L16 3 L23 9" />
      <path d="M4 6 L13 12 L19 19" />
    </g>
    {/* body */}
    <ellipse cx="0" cy="7" rx="7.5" ry="9.5" fill="#0d120a" />
    <ellipse cx="0" cy="7" rx="3" ry="4.5" fill="#161d10" opacity="0.8" />
    <circle cx="0" cy="-6" r="5" fill="#12180d" />
    {/* eyes */}
    <circle cx="-2" cy="-7" r="1.1" fill="#c0392b" />
    <circle cx="2" cy="-7" r="1.1" fill="#c0392b" />
    {/* fangs */}
    <path d="M-2 -11 l-1.5 -3 M2 -11 l1.5 -3" stroke="#0c110a" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

export default function SpiderRunner() {
  const controls = useAnimationControls();
  const lastIdx = useRef(-1);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(true);
    let cancelled = false;

    const runOnce = async () => {
      if (cancelled || typeof window === "undefined") return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      const routes = buildRoutes(w, h);
      let idx = Math.floor(Math.random() * routes.length);
      if (idx === lastIdx.current) idx = (idx + 1) % routes.length; // dirección distinta cada vez
      lastIdx.current = idx;
      const { sx, sy, ex, ey } = routes[idx]();
      const rot = (Math.atan2(ey - sy, ex - sx) * 180) / Math.PI + 90;
      const dist = Math.hypot(ex - sx, ey - sy);
      const dur = Math.min(7, Math.max(2.8, dist / 320)); // velocidad de escape

      try {
        await controls.set({ x: sx, y: sy, rotate: rot, opacity: 0 });
        await controls.start({ opacity: 1, transition: { duration: 0.25 } });
        await controls.start({ x: ex, y: ey, transition: { duration: dur, ease: "linear" } });
        await controls.start({ opacity: 0, transition: { duration: 0.2 } });
      } catch (e) { /* animation interrupted on unmount */ }
    };

    const first = setTimeout(runOnce, FIRST_RUN_MS);
    const interval = setInterval(runOnce, INTERVAL_MS);
    return () => { cancelled = true; clearTimeout(first); clearInterval(interval); };
  }, [controls]);

  if (!ready) return null;
  return (
    <motion.div
      data-testid="cemetery-spider"
      aria-hidden
      animate={controls}
      initial={{ x: -80, y: -80, opacity: 0 }}
      className="pointer-events-none fixed left-0 top-0 z-[60]"
      style={{ filter: "drop-shadow(0 3px 4px rgba(0,0,0,0.6))" }}
    >
      <Spider />
    </motion.div>
  );
}
