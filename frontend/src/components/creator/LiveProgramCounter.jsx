import React, { useEffect, useState, useRef } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { Flame, Users } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Small live counter strip for the landing hero.
 * Shows: 🔥 X refs este mes · Y PrimeMeat repartida
 * Refresh: every 30s (also updates when a WS event bumps the leaderboard, but we don't wire that here).
 */

function AnimatedNumber({ value }) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 60, damping: 20 });
  const [display, setDisplay] = useState("0");
  useEffect(() => { mv.set(value); }, [value, mv]);
  useEffect(() => spring.on("change", (v) => setDisplay(Math.round(v).toLocaleString())), [spring]);
  return <span className="tabular-nums">{display}</span>;
}

export function LiveProgramCounter() {
  const [stats, setStats] = useState(null);
  const tRef = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await api.cpProgramStats();
        if (alive) setStats(r.data);
      } catch { /* ignore */ }
    };
    load();
    tRef.current = setInterval(load, 30_000);
    return () => { alive = false; if (tRef.current) clearInterval(tRef.current); };
  }, []);

  if (!stats || stats.monthly_refs === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="mx-auto max-w-3xl px-4 mt-8"
      data-testid="live-program-counter"
    >
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] px-5 py-3 sm:px-6 sm:py-4 backdrop-blur-md"
        style={{ background: "linear-gradient(135deg, rgba(27,22,48,0.75) 0%, rgba(22,18,37,0.9) 100%)" }}>
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400/50 to-transparent" />
        <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 h-24 w-64 rounded-full opacity-30 blur-2xl"
          style={{ background: "radial-gradient(circle, #ec4899, transparent 60%)" }} />

        <div className="relative flex items-center justify-center gap-6 sm:gap-10 flex-wrap">
          <div className="flex items-center gap-2">
            <motion.div animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 1.8, repeat: Infinity }}>
              <Flame size={16} className="text-orange-400" />
            </motion.div>
            <div className="text-left">
              <div className="text-[9px] font-black tracking-[0.3em] text-white/50">REFS ESTE MES</div>
              <div className="text-lg sm:text-xl font-black text-white">
                <AnimatedNumber value={stats.monthly_refs} />
              </div>
            </div>
          </div>

          <div className="hidden sm:block h-8 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <span className="text-lg">🥩</span>
            <div className="text-left">
              <div className="text-[9px] font-black tracking-[0.3em] text-white/50">PRIME MEAT REPARTIDA</div>
              <div className="text-lg sm:text-xl font-black text-emerald-400">
                <AnimatedNumber value={Math.round((stats.monthly_pm || 0) / 1000)} />K
              </div>
            </div>
          </div>

          <div className="hidden md:block h-8 w-px bg-white/10" />

          <div className="hidden md:flex items-center gap-2">
            <Users size={15} className="text-purple-400" />
            <div className="text-left">
              <div className="text-[9px] font-black tracking-[0.3em] text-white/50">CREATORS ACTIVOS</div>
              <div className="text-lg sm:text-xl font-black text-purple-400">
                <AnimatedNumber value={stats.active_creators} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
