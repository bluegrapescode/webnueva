import React from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { rarityOf } from "./shopRarity";

// Catalog gallery card — clean showcase tile (NO cart button). Click opens the
// detail/preview modal. Themed with the rarity accent + site glass aesthetic.
export function GalleryCard({ skin, onClick, play, view = "grid" }) {
  const r = rarityOf(skin.rarity);
  if (view === "list") {
    return (
      <motion.button layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
        onMouseEnter={() => play?.("hover")} onClick={() => onClick?.(skin)} data-testid={`skin-card-${skin.id}`}
        className="group relative w-full flex items-center gap-4 rounded-xl overflow-hidden border border-white/10 bg-white/[0.02] hover:bg-white/[0.05] transition-colors text-left p-2.5"
        style={{ boxShadow: `inset 3px 0 0 ${r.color}` }}>
        <div className="relative h-16 w-24 shrink-0 rounded-lg overflow-hidden">
          <img src={skin.image_url} alt={skin.name} loading="lazy" className={`absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-110 ${skin.owned ? "grayscale opacity-70" : ""}`} />
          <div className="absolute inset-0" style={{ background: `linear-gradient(90deg, transparent, ${r.color}22)` }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-display font-bold text-sm truncate">{skin.name}</p>
          <p className="text-[11px] text-muted-foreground truncate">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
        </div>
        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0" style={{ color: r.color, background: `${r.color}1a`, border: `1px solid ${r.color}44` }}>{r.label}</span>
        <span className="font-code font-black tabular-nums text-sm shrink-0 pr-2" style={{ color: r.color }}>${skin.price_usd.toFixed(2)}</span>
        {skin.owned && <span className="absolute top-1.5 right-1.5 inline-flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/25 text-emerald-200"><Check size={9} /> Tuya</span>}
      </motion.button>
    );
  }
  return (
    <motion.button layout initial={{ opacity: 0, y: 18, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -5 }} transition={{ type: "spring", stiffness: 320, damping: 24 }}
      onMouseEnter={() => play?.("hover")} onClick={() => onClick?.(skin)} data-testid={`skin-card-${skin.id}`}
      className="group relative w-full block text-left rounded-2xl overflow-hidden border transition-colors"
      style={{ borderColor: `${r.color}33`, background: "#0c0f0a", boxShadow: `0 14px 40px -22px ${r.color}` }}>
      <div className="relative aspect-[16/10] overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-2/3 z-[1]" style={{ background: `radial-gradient(60% 90% at 50% 0%, ${r.color}44, transparent 70%)` }} />
        <img src={skin.image_url} alt={skin.name} loading="lazy"
          className={`absolute inset-0 w-full h-full object-cover transition-transform duration-[650ms] ease-out group-hover:scale-[1.1] ${skin.owned ? "grayscale opacity-70" : ""}`} />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
        <div className="absolute left-0 top-0 h-full w-[3px]" style={{ background: `linear-gradient(to bottom, ${r.color}, transparent)` }} />
        <div className="absolute top-2.5 left-2.5 right-2.5 flex items-start justify-between gap-2 z-[2]">
          <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide px-2 py-1 rounded-md backdrop-blur-sm"
            style={{ color: r.color, borderColor: `${r.color}66`, border: "1px solid", background: `${r.color}22` }}>{r.label}</span>
          {skin.owned && <span className="inline-flex items-center gap-1 text-[9px] font-bold px-2 py-1 rounded-md bg-emerald-500/25 text-emerald-200 border border-emerald-400/50 backdrop-blur-sm"><Check size={10} /> Tuya</span>}
        </div>
      </div>
      <div className="px-3.5 py-3 flex items-end justify-between gap-2 border-t border-white/5">
        <div className="min-w-0">
          <p className="font-display font-bold text-[15px] leading-tight truncate">{skin.name}</p>
          <p className="text-[11px] text-muted-foreground truncate">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
        </div>
        <span className="font-code font-black tabular-nums text-sm shrink-0" style={{ color: r.color }}>${skin.price_usd.toFixed(2)}</span>
      </div>
    </motion.button>
  );
}
