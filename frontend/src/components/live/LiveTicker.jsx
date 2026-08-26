import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Radio, ChevronUp, X, Skull, LogIn, LogOut, Coins, Dices, TrendingUp,
  Target, Sparkles, Egg, Trophy, Users,
} from "lucide-react";
import { useLiveSim } from "@/context/LiveSimContext";
import { useSound } from "@/context/SoundContext";

const KIND = {
  kill:   { Icon: Skull,      color: "#E2574A" },
  join:   { Icon: LogIn,      color: "#3FB960" },
  leave:  { Icon: LogOut,     color: "#8A8F98" },
  sale:   { Icon: Coins,      color: "#E9C83D" },
  win:    { Icon: Dices,      color: "#E9C83D" },
  growth: { Icon: TrendingUp, color: "#4D9FE8" },
  quest:  { Icon: Target,     color: "#8B5CF6" },
  skin:   { Icon: Sparkles,   color: "#3EC1E8" },
  nest:   { Icon: Egg,        color: "#E0812F" },
  record: { Icon: Trophy,     color: "#E9C83D" },
};

const relTime = (ts, now) => {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 3) return "ahora";
  if (s < 60) return `hace ${s}s`;
  return `hace ${Math.floor(s / 60)}m`;
};

// Smoothly counts from the previous value to the next one.
function AnimatedNumber({ value }) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    if (from === to) return;
    const start = performance.now();
    const dur = 600;
    let raf;
    const step = (t) => {
      const p = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(from + (to - from) * eased));
      if (p < 1) raf = requestAnimationFrame(step);
      else fromRef.current = to;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="tabular-nums">{display}</span>;
}

export function LiveTicker() {
  const { players, maxPlayers, events, now, registerToast, live } = useLiveSim();
  const { play } = useSound();
  const [open, setOpen] = useState(false);

  // Let the simulation raise toasts for "hot" events.
  useEffect(() => {
    registerToast((e) => {
      const { Icon, color } = KIND[e.kind] || KIND.join;
      toast.custom(() => (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl glass-strong border border-white/10 shadow-2xl min-w-[280px]">
          <span className="grid place-items-center w-9 h-9 rounded-lg flex-shrink-0" style={{ background: `${color}22`, color }}>
            <Icon size={18} />
          </span>
          <div className="min-w-0">
            <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color }}>En vivo</p>
            <p className="text-sm text-foreground leading-tight truncate">{e.text}</p>
          </div>
        </div>
      ), { duration: 4200 });
    });
  }, [registerToast]);

  if (!live) return null;
  const latest = events[0];

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[80] w-[min(92vw,440px)] pointer-events-none" data-testid="live-hud">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
            className="pointer-events-auto mb-2 glass-strong rounded-2xl border border-white/10 shadow-2xl overflow-hidden"
            data-testid="live-feed"
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5">
              <span className="flex items-center gap-2 text-sm font-bold">
                <Radio size={15} className="text-emerald" /> Actividad en vivo
              </span>
              <button onClick={() => { setOpen(false); play("menuClose"); }} data-testid="live-feed-close" className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="max-h-[46vh] overflow-y-auto px-2 py-2 space-y-0.5">
              <AnimatePresence initial={false}>
                {events.slice(0, 24).map((e) => {
                  const { Icon, color } = KIND[e.kind] || KIND.join;
                  return (
                    <motion.div
                      key={e.id}
                      layout
                      initial={{ opacity: 0, x: -12, height: 0 }}
                      animate={{ opacity: 1, x: 0, height: "auto" }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                      className="flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-white/5"
                      data-testid={`live-event-${e.id}`}
                    >
                      <span className="grid place-items-center w-8 h-8 rounded-lg flex-shrink-0" style={{ background: `${color}1f`, color }}>
                        <Icon size={15} />
                      </span>
                      <span className="text-sm text-foreground/90 leading-tight flex-1 min-w-0 truncate">{e.text}</span>
                      <span className="text-[10px] text-muted-foreground tabular-nums flex-shrink-0">{relTime(e.ts, now)}</span>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Collapsed pill — always visible on every page. */}
      <button
        onClick={() => { setOpen((o) => !o); play(open ? "menuClose" : "menu"); }}
        data-testid="live-hud-toggle"
        className="pointer-events-auto w-full flex items-center gap-3 pl-3 pr-2 py-2 glass-strong rounded-full border border-white/10 shadow-2xl hover:border-emerald/40 transition-colors"
      >
        <span className="flex items-center gap-1.5 flex-shrink-0">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-crimson opacity-75 animate-ping" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-crimson" />
          </span>
          <span className="text-[11px] font-bold tracking-widest text-crimson">EN VIVO</span>
        </span>

        <span className="flex items-center gap-1.5 flex-shrink-0 text-xs font-semibold text-foreground/90 border-l border-white/10 pl-3">
          <Users size={13} className="text-emerald" />
          <AnimatedNumber value={players} data-testid="live-hud-count" />
          <span className="text-muted-foreground">/{maxPlayers}</span>
        </span>

        <span className="flex-1 min-w-0 overflow-hidden border-l border-white/10 pl-3 text-left">
          <AnimatePresence mode="wait">
            {latest && (
              <motion.span
                key={latest.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="block text-xs text-muted-foreground truncate"
              >
                {latest.text}
              </motion.span>
            )}
          </AnimatePresence>
        </span>

        <ChevronUp size={16} className={`text-muted-foreground flex-shrink-0 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
      </button>
    </div>
  );
}
