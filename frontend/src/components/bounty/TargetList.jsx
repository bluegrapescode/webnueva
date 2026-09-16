import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Crosshair, Skull, Users } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { fmtNum, dinoGlyph } from "@/lib/bountyMeta";

// Lista de jugadores online para elegir a quién cazar (filas, esquinas cuadradas).
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
          className="w-full bg-black/40 border border-white/10 rounded-md pl-10 pr-3 py-2.5 text-sm text-white placeholder-white/30 focus:border-[#E11D2A]/50 outline-none transition-colors"
        />
      </div>
      <div className="grid gap-2">
        <AnimatePresence initial={false}>
          {filtered.map((t, i) => {
            const has = t.bounty && t.bounty.primeMeat > 0;
            return (
              <motion.div
                key={t.sid}
                layout
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.35 }}
                whileHover={{ scale: 1.01 }}
                className="group flex flex-col gap-2.5 p-3 rounded-md border transition-colors"
                style={{ borderColor: has ? "rgba(225,29,42,0.35)" : "rgba(255,255,255,0.08)", background: has ? "rgba(225,29,42,0.05)" : "rgba(255,255,255,0.02)" }}
                data-testid={`bounty-target-${t.sid}`}
              >
                <div className="flex items-center gap-3 w-full min-w-0">
                  <div className="relative w-11 h-11 shrink-0 rounded-md flex items-center justify-center overflow-hidden"
                    style={{ background: "radial-gradient(circle, rgba(225,29,42,0.14), transparent 70%)", border: "1px solid rgba(255,255,255,0.08)" }}>
                    <span className="text-2xl">{dinoGlyph(t.slug)}</span>
                    {has && <span className="absolute -top-0.5 -right-0.5 w-3 h-3 rounded-full bg-[#E11D2A] animate-pulse ring-2 ring-[#0b0b0d]" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-white truncate">{t.name}</p>
                      {t.isMe && <span className="text-[9px] uppercase tracking-wider text-white/40 border border-white/15 rounded px-1.5 py-0.5 shrink-0">Tú</span>}
                      {has && !t.isMe && <span className="text-[9px] uppercase tracking-wider font-bold text-[#ff6b74] border border-[#E11D2A]/40 rounded px-1.5 py-0.5 shrink-0">En la mira</span>}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 min-w-0">
                      <p className="text-[11px] text-white/45 truncate">{t.species} • Adulto</p>
                      <span className="inline-flex items-center gap-1 text-[10px] text-white/35 shrink-0"><Users className="w-2.5 h-2.5" /> {has ? `${t.bounty.count}` : "0"}</span>
                    </div>
                    {has && (
                      <div className="flex items-center gap-2 mt-1 text-xs font-mono font-bold">
                        <span className="inline-flex items-center gap-1 text-[#22C55E]"><img src={MEDIA.coinNormal} alt="" className="w-3 h-3" />{fmtNum(t.bounty.primeMeat)}</span>
                        {t.bounty.amberium > 0 && <span className="inline-flex items-center gap-1 text-[#F0B429]"><img src={MEDIA.coinVip} alt="" className="w-3 h-3" />{fmtNum(t.bounty.amberium)}</span>}
                      </div>
                    )}
                  </div>
                </div>
                <button
                  data-testid={`bounty-hunt-${t.sid}`}
                  disabled={t.isMe || disabledHunt || !t.alive}
                  onClick={() => onHunt(t)}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                  style={{ background: "linear-gradient(180deg, #E11D2A, #a10f1a)", color: "#fff", boxShadow: "0 6px 20px -8px rgba(225,29,42,0.8)" }}
                >
                  <Crosshair className="w-3.5 h-3.5" /> {has ? "Subir bote" : "Cazar"}
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {filtered.length === 0 && (
          <p className="text-sm text-white/30 py-8 text-center" data-testid="bounty-target-empty">No hay jugadores que coincidan.</p>
        )}
      </div>
    </div>
  );
}

export default TargetList;
