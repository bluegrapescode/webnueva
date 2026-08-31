import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { History, ArrowRight, Gem, Loader2, PackageOpen, User } from "lucide-react";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";

const RARITY_COLOR = {
  Common: "#8e9297", Uncommon: "#34D399", Rare: "#38bdf8", Epic: "#a855f7",
  Legendary: "#f59e0b", Mythic: "#ef4444", common: "#8e9297", rare: "#38bdf8",
  epic: "#a855f7", legendary: "#f59e0b", mythic: "#ef4444", uncommon: "#34D399",
};
const rc = (r) => RARITY_COLOR[r] || "#CAA968";

function fmtDate(iso) {
  try { return new Date(iso).toLocaleString("es", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

function OfferChips({ offer, tone }) {
  const items = offer.items || [];
  const empty = items.length === 0 && !offer.amber;
  return (
    <div className="flex flex-wrap gap-1.5">
      {empty && <span className="text-xs text-muted-foreground italic">Nada</span>}
      {items.map((it, i) => (
        <span key={i} className="inline-flex items-center gap-1.5 rounded-md pl-1 pr-2 py-1 text-xs font-semibold border"
          style={{ borderColor: `${rc(it.rarity)}55`, background: `${rc(it.rarity)}14` }}>
          <span className="w-5 h-5 rounded overflow-hidden bg-white/5 shrink-0">
            {it.image ? <img src={it.image} alt="" className="w-full h-full object-cover" /> : null}
          </span>
          {it.name} <b className="opacity-70">×{it.qty}</b>
        </span>
      ))}
      {offer.amber > 0 && (
        <span className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-bold text-gold border border-gold/40 bg-gold/10">
          <img src={MEDIA.coinVip} alt="Amberium" className="object-contain" style={{ width: 13, height: 13 }} /> {offer.amber}
        </span>
      )}
    </div>
  );
}

export default function TradeHistory() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.tradeHistory().then((r) => setRows(r.data.trades)).catch(() => setRows([])); }, []);

  if (rows === null) return <div className="py-20 text-center text-muted-foreground"><Loader2 className="mx-auto animate-spin" /></div>;
  if (rows.length === 0) return (
    <div className="text-center py-20 glass rounded-2xl border border-white/10" data-testid="trade-history-empty">
      <History size={44} className="mx-auto mb-3 opacity-40" />
      <p className="text-muted-foreground">Aún no has completado ningún intercambio.</p>
    </div>
  );

  return (
    <div className="space-y-3" data-testid="trade-history">
      {rows.map((t, idx) => (
        <motion.div key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.03 }}
          className="glass rounded-xl border border-white/10 p-4" data-testid={`history-row-${t.id}`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-sm">
              <div className="w-7 h-7 rounded-lg overflow-hidden bg-white/5">{t.partner_avatar ? <img src={t.partner_avatar} alt="" className="w-full h-full object-cover" /> : <User size={14} className="m-auto mt-1.5 opacity-50" />}</div>
              con <b>{t.partner_name}</b>
            </div>
            <span className="font-code text-[11px] text-muted-foreground">{fmtDate(t.created_at)}</span>
          </div>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-crimson mb-1.5">Diste</p>
              <OfferChips offer={t.gave} />
            </div>
            <ArrowRight size={18} className="text-gold shrink-0" />
            <div>
              <p className="text-[10px] uppercase tracking-wider text-emerald mb-1.5">Recibiste</p>
              <OfferChips offer={t.received} />
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
