import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { List, CheckCircle2, Clock, XCircle } from "lucide-react";
import { api } from "@/lib/api";

const STATUS_STYLE = {
  REWARDED:  { icon: <CheckCircle2 size={12} />, label: "Recompensado", color: "#10B981" },
  VALIDATED: { icon: <CheckCircle2 size={12} />, label: "Validado",     color: "#7CA842" },
  PENDING:   { icon: <Clock size={12} />,         label: "Pendiente",   color: "#F59E0B" },
  CANCELLED: { icon: <XCircle size={12} />,       label: "Cancelado",   color: "#6B7280" },
};

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MyReferrals({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.cpReferrals().then((r) => { if (alive) setRows(r.data.referrals || []); })
      .catch(() => {}).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [refreshKey]);

  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.05]" data-testid="my-referrals"
      style={{ background: "#161225" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-pink-400/40 to-transparent" />
      <div className="flex items-center gap-2 px-5 py-4 border-b border-white/[0.06]">
        <List size={13} className="text-pink-400" />
        <span className="text-[10px] font-black tracking-[0.35em] text-pink-400/80">MIS REFERIDOS</span>
        <span className="ml-auto text-[10px] font-bold tracking-widest text-white/30 tabular-nums">{rows.length}</span>
      </div>

      {loading ? (
        <div className="px-4 py-8 text-center text-xs text-white/40">Cargando…</div>
      ) : rows.length === 0 ? (
        <div className="px-4 py-8 text-center text-xs text-white/40">Todavía no tenés referidos. ¡Compartí tu código!</div>
      ) : (
        <div className="divide-y divide-white/5 max-h-[420px] overflow-y-auto">
          <AnimatePresence>
            {rows.map((r) => {
              const st = STATUS_STYLE[r.status] || STATUS_STYLE.PENDING;
              return (
                <motion.div
                  key={r.id}
                  layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
                  className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black truncate">{r.referred_name}</div>
                    <div className="text-[10px] text-white/45">{fmtDate(r.created_at)}</div>
                  </div>
                  <span
                    className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-black tracking-widest"
                    style={{ borderColor: st.color + "55", background: st.color + "12", color: st.color }}
                  >
                    {st.icon}
                    {st.label.toUpperCase()}
                  </span>
                  <div className="text-right w-16 tabular-nums text-[11px]">
                    {r.reward_amount ? (
                      <span className="text-gold font-black">+{Math.round(r.reward_amount / 1000)}K</span>
                    ) : (
                      <span className="text-white/30">—</span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
