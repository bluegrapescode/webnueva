import React, { useEffect, useRef, useState } from "react";
import { motion, useAnimationControls } from "framer-motion";

// A swarm of creepy spiders that burst across the WHOLE site in different random
// directions (frantic!) every 2 minutes, then vanish off-screen. Mounted once,
// globally. Always pointer-events-none so it never blocks clicks.
const INTERVAL_MS = 2 * 60 * 1000; // cada 2 minutos
const FIRST_RUN_MS = 6000;         // primera oleada a los 6s
const MIN_SPIDERS = 2;
const MAX_SPIDERS = 3;

// Route builders -> {sx, sy, ex, ey} just off the viewport edges.
function buildRoutes(w, h) {
  const rx = () => 40 + Math.random() * (w - 80);
  const ry = () => 40 + Math.random() * (h - 80);
  const M = 70;
  return [
    () => ({ sx: -M, sy: ry(), ex: w + M, ey: ry() }),   // →
    () => ({ sx: w + M, sy: ry(), ex: -M, ey: ry() }),   // ←
    () => ({ sx: -M, sy: -M, ex: w + M, ey: h + M }),    // ↘
    () => ({ sx: w + M, sy: h + M, ex: -M, ey: -M }),    // ↖
    () => ({ sx: w + M, sy: -M, ex: -M, ey: h + M }),    // ↙
    () => ({ sx: -M, sy: h + M, ex: w + M, ey: -M }),    // ↗
    () => ({ sx: rx(), sy: -M, ex: rx(), ey: h + M }),   // ↓
    () => ({ sx: rx(), sy: h + M, ex: rx(), ey: -M }),   // ↑
  ];
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const Spider = ({ size = 44 }) => (
  <svg width={size} height={size} viewBox="-24 -24 48 48" aria-hidden>
    <g stroke="#0c110a" strokeWidth="2" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleA 0.14s ease-in-out infinite" }}>
      <path d="M-4 -8 L-14 -16 L-21 -11" />
      <path d="M-5 -3 L-16 -7 L-23 -2" />
      <path d="M-5 2 L-16 3 L-23 9" />
      <path d="M-4 6 L-13 12 L-19 19" />
    </g>
    <g stroke="#0c110a" strokeWidth="2" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleB 0.14s ease-in-out infinite" }}>
      <path d="M4 -8 L14 -16 L21 -11" />
      <path d="M5 -3 L16 -7 L23 -2" />
      <path d="M5 2 L16 3 L23 9" />
      <path d="M4 6 L13 12 L19 19" />
    </g>
    <ellipse cx="0" cy="7" rx="7.5" ry="9.5" fill="#0d120a" />
    <ellipse cx="0" cy="7" rx="3" ry="4.5" fill="#161d10" opacity="0.8" />
    <circle cx="0" cy="-6" r="5" fill="#12180d" />
    <circle cx="-2" cy="-7" r="1.1" fill="#c0392b" />
    <circle cx="2" cy="-7" r="1.1" fill="#c0392b" />
    <path d="M-2 -11 l-1.5 -3 M2 -11 l1.5 -3" stroke="#0c110a" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

function SpiderInstance({ route, delay, dur, size, onDone }) {
  const controls = useAnimationControls();
  useEffect(() => {
    let cancelled = false;
    const { sx, sy, ex, ey } = route;
    const rot = (Math.atan2(ey - sy, ex - sx) * 180) / Math.PI + 90;
    (async () => {
      try {
        await controls.set({ x: sx, y: sy, rotate: rot, opacity: 0 });
        await new Promise((r) => setTimeout(r, delay));
        if (cancelled) return;
        await controls.start({ opacity: 1, transition: { duration: 0.18 } });
        await controls.start({ x: ex, y: ey, transition: { duration: dur, ease: "linear" } });
        await controls.start({ opacity: 0, transition: { duration: 0.15 } });
      } catch (e) { /* interrupted */ }
      if (!cancelled) onDone();
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <motion.div
      data-testid="cemetery-spider"
      aria-hidden
      animate={controls}
      initial={{ x: route.sx, y: route.sy, opacity: 0 }}
      className="pointer-events-none fixed left-0 top-0 z-[60]"
      style={{ filter: "drop-shadow(0 3px 4px rgba(0,0,0,0.6))" }}
    >
      <Spider size={size} />
    </motion.div>
  );
}

export default function SpiderRunner() {
  const [runs, setRuns] = useState([]);
  const idRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const burst = () => {
      if (cancelled || typeof window === "undefined") return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      const routes = buildRoutes(w, h);
      const count = MIN_SPIDERS + Math.floor(Math.random() * (MAX_SPIDERS - MIN_SPIDERS + 1));
      const idxs = shuffle([...routes.keys()]).slice(0, count); // direcciones distintas
      const newRuns = idxs.map((i) => {
        const r = routes[i]();
        const dist = Math.hypot(r.ex - r.sx, r.ey - r.sy);
        const dur = Math.min(3.6, Math.max(1.6, dist / 520)); // frenéticas
        return { id: idRef.current++, route: r, delay: Math.random() * 700, dur, size: 34 + Math.floor(Math.random() * 20) };
      });
      setRuns((prev) => [...prev, ...newRuns]);
    };
    const first = setTimeout(burst, FIRST_RUN_MS);
    const interval = setInterval(burst, INTERVAL_MS);
    return () => { cancelled = true; clearTimeout(first); clearInterval(interval); };
  }, []);

  const remove = (id) => setRuns((prev) => prev.filter((r) => r.id !== id));

  return (
    <>
      {runs.map((r) => (
        <SpiderInstance key={r.id} route={r.route} delay={r.delay} dur={r.dur} size={r.size} onDone={() => remove(r.id)} />
      ))}
    </>
  );
}
