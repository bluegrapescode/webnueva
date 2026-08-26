import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crown, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { GlitchProx } from "@/components/common/GlitchProx";

const RANK_META = {
  1: { color: "#D4AF37", label: "🥇 CAMPEÓN" },
  2: { color: "#C0C6D0", label: "🥈 SUB-CAMPEÓN" },
  3: { color: "#CD7F32", label: "🥉 TERCERO" },
};

function fmtMonth(m) {
  if (!m) return "";
  const [y, mm] = m.split("-");
  const name = new Date(Number(y), Number(mm) - 1, 1).toLocaleDateString("es-AR", { month: "long", year: "numeric" });
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function ChampionCard({ entry, skinByGlitchId }) {
  const meta = RANK_META[entry.rank] || {};
  // entry.prize_skin is just a glitch_id string (the month's config at close
  // time) — resolved against the CURRENT prize_skins cards passed down from
  // the dashboard payload. A month whose config has since changed (or a
  // retired design) simply has no match, and the block below omits itself
  // rather than showing a raw id or a broken card.
  const skin = entry.prize_skin ? skinByGlitchId?.[entry.prize_skin] : null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-xl p-4"
      style={{
        background: "linear-gradient(180deg, rgba(27,22,48,0.9) 0%, rgba(22,18,37,0.95) 100%)",
        border: `1px solid ${(meta.color || "#8B5CF6") + "55"}`,
      }}
    >
      <div className="pointer-events-none absolute -top-12 -right-10 h-28 w-28 rounded-full opacity-25"
        style={{ background: `radial-gradient(circle, ${meta.color}, transparent 65%)` }} />
      <div className="relative flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 overflow-hidden font-black uppercase"
          style={{ borderColor: meta.color, background: `${meta.color}22`, color: meta.color }}>
          {entry.avatar
            ? <img src={entry.avatar} alt="" className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
            : (entry.display_name || "?")[0]}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-black text-sm truncate text-white">{entry.display_name}</span>
            {entry.rank === 1 && <Crown size={12} className="text-gold shrink-0" fill="#D4AF37" />}
          </div>
          <div className="text-[10px] text-white/40 font-mono">{entry.code}</div>
        </div>
        <span className="shrink-0 text-[9px] font-black tracking-[0.3em] px-2 py-0.5 rounded"
          style={{ color: meta.color, background: `${meta.color}18`, border: `1px solid ${meta.color}55` }}>
          {meta.label}
        </span>
      </div>
      <div className="relative mt-3 grid grid-cols-2 gap-3 text-center">
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">REFS DEL MES</div>
          <div className="text-base font-black text-white tabular-nums">{(entry.monthly_referrals || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">PREMIO</div>
          <div className="text-base font-black text-emerald-400 tabular-nums">+{Math.round((entry.prize_pm || 0) / 1000)}K</div>
        </div>
      </div>
      {skin?.name && (
        <div className="relative mt-3 pt-3 border-t border-white/[0.06] flex items-center gap-2">
          <div className="h-7 w-7 shrink-0 overflow-hidden rounded border border-white/10">
            <GlitchProx proximity={skin.proximity} compact />
          </div>
          <div className="min-w-0 text-[10px] font-bold text-white/80 truncate">{skin.name}</div>
        </div>
      )}
    </motion.div>
  );
}

export function HallOfFame({ limit = 6, prizeSkins }) {
  const [months, setMonths] = useState(null);
  useEffect(() => {
    let alive = true;
    api.cpHallOfFame(limit).then((r) => alive && setMonths(r.data.months || []))
      .catch(() => alive && setMonths([]));
    return () => { alive = false; };
  }, [limit]);

  const active = (months || []).filter((m) => (m.top || []).length > 0);
  if (!months) return null;

  const skinByGlitchId = {};
  Object.values(prizeSkins || {}).forEach((c) => { if (c?.glitch_id) skinByGlitchId[c.glitch_id] = c; });

  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.05]" data-testid="hall-of-fame"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold/40 to-transparent" />
      <div className="pointer-events-none absolute -top-24 -left-16 h-56 w-56 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(212,175,55,0.6), transparent 65%)" }} />

      <div className="relative p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-1">
          <Trophy size={15} className="text-gold" />
          <span className="text-[10px] font-black tracking-[0.35em] text-gold/80">HALL OF FAME</span>
        </div>
        <h3 className="text-xl sm:text-2xl font-black tracking-tight text-white">
          Campeones inmortalizados
        </h3>
        <p className="text-xs text-white/50 mt-1">Los top 3 creators de cada mes cerrado quedan acá para siempre.</p>

        {active.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-white/10 bg-black/20 py-10 text-center">
            <Trophy size={24} className="mx-auto text-white/20" />
            <div className="mt-2 text-xs text-white/40">
              Todavía no hay ningún mes cerrado con top 3.
            </div>
            <div className="text-[10px] text-white/30 mt-1">
              Al terminar el mes actual, los campeones aparecerán acá.
            </div>
          </div>
        ) : (
          <div className="mt-6 space-y-5">
            <AnimatePresence>
              {active.map((m) => (
                <motion.div key={m.month}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-black tracking-[0.32em] text-white/50">{fmtMonth(m.month)}</span>
                    <span className="flex-1 h-px bg-white/[0.06]" />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {m.top.map((e) => <ChampionCard key={`${m.month}-${e.rank}`} entry={e} skinByGlitchId={skinByGlitchId} />)}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
