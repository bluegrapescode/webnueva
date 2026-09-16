import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Crosshair, Users, Radio } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { fmtNum, dinoGlyph } from "@/lib/bountyMeta";

const RED = "#E11D2A";
const GOLD = "#F0B429";
const MEAT = "#22C55E";

// Cuadrícula de tarjetas cuadradas de jugadores online para elegir a quién cazar.
export function TargetList({ targets, onHunt, disabledHunt }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return targets;
    return targets.filter((t) => (t.name || "").toLowerCase().includes(s) || (t.species || "").toLowerCase().includes(s));
  }, [targets, q]);

  return (
    <div data-testid="bounty-target-list">
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
        <input
          data-testid="bounty-target-search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre o dinosaurio…"
          className="w-full bg-black/40 border border-white/10 rounded-xl pl-10 pr-3 py-2.5 text-sm text-white placeholder-white/30 focus:border-[#E11D2A]/50 outline-none transition-colors"
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <AnimatePresence initial={false}>
          {filtered.map((t, i) => {
            const has = t.bounty && t.bounty.primeMeat > 0;
            const accent = has ? RED : "rgba(255,255,255,0.1)";
            return (
              <motion.div
                key={t.sid}
                layout
                initial={{ opacity: 0, y: 14, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.32 }}
                whileHover={{ y: -3 }}
                className="relative flex flex-col rounded-xl border overflow-hidden"
                style={{
                  borderColor: has ? "rgba(225,29,42,0.4)" : "rgba(255,255,255,0.08)",
                  background: has ? "linear-gradient(165deg, rgba(225,29,42,0.08), rgba(10,10,12,0.6))" : "linear-gradient(165deg, rgba(255,255,255,0.03), rgba(10,10,12,0.5))",
                  boxShadow: has ? "0 0 26px -16px rgba(225,29,42,0.7)" : "0 8px 24px -18px rgba(0,0,0,0.9)",
                }}
                data-testid={`bounty-target-${t.sid}`}
              >
                {has && <div className="absolute inset-0 pointer-events-none opacity-[0.06]" style={{ backgroundImage: `radial-gradient(${RED} 1px, transparent 1px)`, backgroundSize: "14px 14px" }} />}

                {/* estado + tú */}
                <div className="relative flex items-center justify-between px-3 pt-2.5">
                  <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-wider font-semibold text-emerald-400/90">
                    <Radio className="w-2.5 h-2.5" /> En línea
                  </span>
                  {t.isMe && <span className="text-[8px] uppercase tracking-wider text-white/40 border border-white/15 rounded px-1 py-0.5">Tú</span>}
                  {has && !t.isMe && <span className="text-[8px] uppercase tracking-wider font-bold text-[#ff6b74] border border-[#E11D2A]/40 rounded px-1 py-0.5">En la mira</span>}
                </div>

                {/* avatar */}
                <div className="relative flex justify-center pt-2 pb-1">
                  <div className="relative w-16 h-16 rounded-full flex items-center justify-center"
                    style={{ background: `radial-gradient(circle at 50% 35%, ${has ? "rgba(225,29,42,0.18)" : "rgba(255,255,255,0.06)"}, transparent 70%)`, border: `1px solid ${accent}` }}>
                    <span className="text-3xl">{dinoGlyph(t.slug)}</span>
                    {has && <span className="absolute -top-0.5 -right-0.5 w-3 h-3 rounded-full bg-[#E11D2A] animate-pulse ring-2 ring-[#0b0b0d]" />}
                  </div>
                </div>

                {/* identidad */}
                <div className="relative px-3 text-center">
                  <p className="text-sm font-black uppercase tracking-tight text-white truncate leading-none">{t.name}</p>
                  <p className="text-[10px] text-white/45 mt-1 truncate">{t.species} • Adulto</p>
                </div>

                {/* recompensa sobre su cabeza */}
                <div className="relative px-3 mt-2.5">
                  {has ? (
                    <div className="rounded-lg px-2 py-1.5 flex items-center justify-center gap-2" style={{ background: "rgba(225,29,42,0.1)", border: "1px solid rgba(225,29,42,0.25)" }}>
                      <span className="flex items-center gap-1 text-xs font-bold font-mono" style={{ color: MEAT }}><img src={MEDIA.coinNormal} alt="" className="w-3.5 h-3.5" />{fmtNum(t.bounty.primeMeat)}</span>
                      {t.bounty.amberium > 0 && <span className="flex items-center gap-1 text-xs font-bold font-mono" style={{ color: GOLD }}><img src={MEDIA.coinVip} alt="" className="w-3.5 h-3.5" />{fmtNum(t.bounty.amberium)}</span>}
                    </div>
                  ) : (
                    <div className="rounded-lg px-2 py-1.5 text-center" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                      <span className="text-[10px] uppercase tracking-wider text-white/35">Sin recompensa</span>
                    </div>
                  )}
                  <div className="flex items-center justify-center gap-1 mt-1.5 text-[9px] uppercase tracking-wider text-white/35">
                    <Users className="w-2.5 h-2.5" /> {has ? `${t.bounty.count} contratista${t.bounty.count > 1 ? "s" : ""}` : "libre"}
                  </div>
                </div>

                {/* acción */}
                <div className="relative px-3 pb-3 pt-2.5 mt-auto">
                  <button
                    data-testid={`bounty-hunt-${t.sid}`}
                    disabled={t.isMe || disabledHunt || !t.alive}
                    onClick={() => onHunt(t)}
                    className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                    style={{ background: "linear-gradient(180deg, #E11D2A, #a10f1a)", color: "#fff", boxShadow: "0 6px 18px -8px rgba(225,29,42,0.8)" }}
                  >
                    <Crosshair className="w-3.5 h-3.5" /> {has ? "Subir bote" : "Cazar"}
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {filtered.length === 0 && (
        <p className="text-sm text-white/30 py-8 text-center" data-testid="bounty-target-empty">No hay jugadores que coincidan.</p>
      )}
    </div>
  );
}

export default TargetList;
