import React from "react";
import { motion } from "framer-motion";
import { Target, MousePointerClick, Ticket } from "lucide-react";

/**
 * Small conversion metric card shown in the Creator Dashboard.
 * Data comes from dashboard.conversion = { visits_total, visits_month, applies_month, applies_total, rate_pct }
 */
export function ConversionCard({ conversion }) {
  if (!conversion) return null;
  const rate = Number(conversion.rate_pct || 0);
  const visits = Number(conversion.visits_total || 0);
  const applies = Number(conversion.applies_total || 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border border-white/[0.05] p-5"
      data-testid="conversion-card"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />
      <div className="pointer-events-none absolute -top-14 -right-12 h-36 w-36 rounded-full opacity-20"
        style={{ background: "radial-gradient(circle, rgba(6,182,212,0.6), transparent 65%)" }} />

      <div className="relative flex items-center gap-2 mb-4">
        <Target size={13} className="text-cyan-400" />
        <span className="text-[10px] font-black tracking-[0.35em] text-cyan-400/80">TASA DE CONVERSIÓN</span>
      </div>

      <div className="relative flex items-baseline gap-2">
        <div className="text-4xl sm:text-5xl font-black tabular-nums text-white">{rate.toFixed(1)}<span className="text-cyan-400">%</span></div>
        <div className="text-xs text-white/40">
          de visitas → códigos aplicados
        </div>
      </div>

      <div className="relative mt-5 grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2 rounded-lg bg-black/25 border border-white/[0.05] p-3">
          <MousePointerClick size={16} className="text-white/50" />
          <div>
            <div className="text-[9px] font-black tracking-widest text-white/40">VISITAS TOTALES</div>
            <div className="text-base font-black text-white tabular-nums">{visits.toLocaleString()}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-black/25 border border-white/[0.05] p-3">
          <Ticket size={16} className="text-emerald-400" />
          <div>
            <div className="text-[9px] font-black tracking-widest text-white/40">CÓDIGOS APLICADOS</div>
            <div className="text-base font-black text-emerald-400 tabular-nums">{applies.toLocaleString()}</div>
          </div>
        </div>
      </div>

      {visits === 0 && (
        <div className="relative mt-3 text-[10px] text-white/40">
          Compartí tu <b>/ref/{"{código}"}</b> — cada visita se cuenta en vivo.
        </div>
      )}
    </motion.div>
  );
}
