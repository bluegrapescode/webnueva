import React, { useEffect, useRef, useState } from "react";
import { motion, useAnimationControls } from "framer-motion";

// Occasional bats & moths that flutter across the cemetery with a WAVY flight
// (different from the spiders' straight scuttle). Cemetery-only, pointer-events-none.
const FIRST_MS = 14000;
const MIN_GAP = 40000;   // 40s
const MAX_GAP = 95000;   // ~1.5min

function rand(min, max) { return min + Math.random() * (max - min); }

const Bat = ({ size = 40 }) => (
  <svg width={size} height={size} viewBox="-26 -20 52 40" aria-hidden>
    <g style={{ transformOrigin: "0px 0px", animation: "batFlapL 0.22s ease-in-out infinite" }}>
      <path d="M0 -2 C -9 -9 -17 -6 -24 -1 C -18 -1 -13 1 -10 6 C -15 5 -20 7 -24 12 C -15 9 -6 6 0 4 Z" fill="#0c110a" />
    </g>
    <g style={{ transformOrigin: "0px 0px", animation: "batFlapR 0.22s ease-in-out infinite" }}>
      <path d="M0 -2 C 9 -9 17 -6 24 -1 C 18 -1 13 1 10 6 C 15 5 20 7 24 12 C 15 9 6 6 0 4 Z" fill="#0c110a" />
    </g>
    <ellipse cx="0" cy="0" rx="2.6" ry="6" fill="#0d120a" />
    <circle cx="0" cy="-6" r="3" fill="#12180d" />
    <path d="M-2 -8 l-2 -4 M2 -8 l2 -4" stroke="#12180d" strokeWidth="1.6" strokeLinecap="round" />
    <circle cx="-1.2" cy="-6" r="0.7" fill="#c0392b" />
    <circle cx="1.2" cy="-6" r="0.7" fill="#c0392b" />
  </svg>
);

const Moth = ({ size = 34 }) => (
  <svg width={size} height={size} viewBox="-22 -18 44 36" aria-hidden>
    <g style={{ transformOrigin: "0px 0px", animation: "mothFlapL 0.14s ease-in-out infinite" }}>
      <path d="M0 -1 C -12 -12 -20 -8 -18 0 C -20 8 -12 11 0 3 Z" fill="#8a7c5f" />
      <path d="M0 2 C -9 6 -13 12 -8 15 C -3 12 -1 8 0 5 Z" fill="#6f6249" />
      <circle cx="-11" cy="-2" r="2" fill="#3a3324" opacity="0.6" />
    </g>
    <g style={{ transformOrigin: "0px 0px", animation: "mothFlapR 0.14s ease-in-out infinite" }}>
      <path d="M0 -1 C 12 -12 20 -8 18 0 C 20 8 12 11 0 3 Z" fill="#8a7c5f" />
      <path d="M0 2 C 9 6 13 12 8 15 C 3 12 1 8 0 5 Z" fill="#6f6249" />
      <circle cx="11" cy="-2" r="2" fill="#3a3324" opacity="0.6" />
    </g>
    <ellipse cx="0" cy="1" rx="2.2" ry="6.5" fill="#4a4234" />
    <circle cx="0" cy="-6" r="2.2" fill="#5a4f3d" />
    <path d="M-1 -7 q-4 -4 -6 -9 M1 -7 q4 -4 6 -9" stroke="#4a4234" strokeWidth="1" fill="none" strokeLinecap="round" />
  </svg>
);

function CritterInstance({ run, onDone }) {
  const controls = useAnimationControls();
  useEffect(() => {
    let cancelled = false;
    const { sx, ex, baseY, amp, dur } = run;
    (async () => {
      try {
        await controls.set({ x: sx, y: baseY, opacity: 0 });
        await controls.start({ opacity: 1, transition: { duration: 0.35 } });
        await controls.start({
          x: ex,
          y: [baseY, baseY - amp, baseY + amp * 0.7, baseY - amp * 0.6, baseY + amp * 0.3, baseY],
          transition: { duration: dur, ease: "easeInOut" },
        });
        await controls.start({ opacity: 0, transition: { duration: 0.35 } });
      } catch (e) { /* interrupted */ }
      if (!cancelled) onDone();
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <motion.div
      data-testid="cemetery-critter"
      data-critter={run.type}
      aria-hidden
      animate={controls}
      initial={{ x: run.sx, y: run.baseY, opacity: 0 }}
      className="pointer-events-none fixed left-0 top-0 z-[59]"
      style={{ filter: "drop-shadow(0 3px 5px rgba(0,0,0,0.55))" }}
    >
      <div style={{ transform: run.dir < 0 ? "scaleX(-1)" : "none" }}>
        {run.type === "bat" ? <Bat size={run.size} /> : <Moth size={run.size} />}
      </div>
    </motion.div>
  );
}

export default function FlyingCritters() {
  const [runs, setRuns] = useState([]);
  const idRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const spawn = () => {
      if (cancelled || typeof window === "undefined") return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      const type = Math.random() < 0.6 ? "bat" : "moth";
      const leftToRight = Math.random() < 0.5;
      const M = 80;
      const sx = leftToRight ? -M : w + M;
      const ex = leftToRight ? w + M : -M;
      const baseY = rand(h * 0.15, h * 0.7);
      const amp = type === "bat" ? rand(40, 90) : rand(25, 55);
      const dur = type === "bat" ? rand(5, 7.5) : rand(7, 10);
      const size = type === "bat" ? 34 + Math.floor(Math.random() * 16) : 28 + Math.floor(Math.random() * 12);
      setRuns((prev) => [...prev, { id: idRef.current++, type, sx, ex, baseY, amp, dur, size, dir: leftToRight ? 1 : -1 }]);
    };
    const schedule = (ms) => {
      timer = setTimeout(() => {
        spawn();
        schedule(rand(MIN_GAP, MAX_GAP));
      }, ms);
    };
    schedule(FIRST_MS);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, []);

  const remove = (id) => setRuns((prev) => prev.filter((r) => r.id !== id));

  return (
    <>
      {runs.map((r) => <CritterInstance key={r.id} run={r} onDone={() => remove(r.id)} />)}
    </>
  );
}
