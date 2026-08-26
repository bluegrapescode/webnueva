import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, CheckCircle2, Clock } from "lucide-react";

function relative(dt) {
  if (!dt) return "";
  const d = new Date(dt);
  const now = Date.now();
  const diff = Math.max(0, now - d.getTime());
  const m = Math.floor(diff / 60000);
  if (m < 1)     return "ahora";
  if (m < 60)    return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24)    return `hace ${h}h`;
  const days = Math.floor(h / 24);
  return `hace ${days}d`;
}

export function RecentActivity({ recent = [], creatorReward = 50_000 }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.05]" data-testid="recent-activity"
      style={{ background: "#161225" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400/40 to-transparent" />
      <div className="flex items-center gap-2 px-5 py-4 border-b border-white/[0.06]">
        <Activity size={13} className="text-purple-400" />
        <span className="text-[10px] font-black tracking-[0.35em] text-purple-400/80">ACTIVIDAD RECIENTE</span>
      </div>
      <AnimatePresence>
        {recent.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-white/40">
            Todavía no hay actividad. Compartí tu código para conseguir tu primer referido.
          </div>
        )}
        {recent.map((r) => {
          const rewarded = r.status === "REWARDED";
          return (
            <motion.div
              key={r.id}
              layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 8 }}
              transition={{ type: "spring", stiffness: 380, damping: 32 }}
              className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 last:border-b-0 hover:bg-white/[0.02]"
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${rewarded ? "bg-emerald-500/15 text-emerald-400" : "bg-white/5 text-white/60"}`}>
                {rewarded ? <CheckCircle2 size={14} /> : <Clock size={14} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-black truncate">
                  {rewarded ? "Nuevo referido validado" : "Referido pendiente"}
                </div>
                <div className="text-[11px] text-white/50 truncate">
                  {r.referred_name || "Hunter"} · {relative(r.validated_at || r.created_at)}
                </div>
              </div>
              {rewarded && (
                <div className="text-right shrink-0">
                  <div className="text-sm font-black text-gold tabular-nums whitespace-nowrap">
                    +{(r.reward_amount || creatorReward).toLocaleString()}
                  </div>
                  <div className="text-[9px] font-bold tracking-widest text-white/40">PRIME MEAT</div>
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
