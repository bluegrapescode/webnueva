import React from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { rarityOf } from "./shopRarity";

// Catalog gallery card — clean showcase tile (NO cart button). Click opens the
// detail/preview modal. Themed with the rarity accent + site glass aesthetic.
export function GalleryCard({ skin, onClick, play, view = "grid", index = 0 }) {
  const r = rarityOf(skin.rarity);
  const delay = Math.min(index * 0.035, 0.45);
  if (view === "list") {
    return (
      <motion.button layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ delay }}
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
    <motion.button layout initial={{ opacity: 0, y: 22, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -6 }} transition={{ type: "spring", stiffness: 320, damping: 24, delay }}
      onMouseEnter={() => play?.("hover")} onClick={() => onClick?.(skin)} data-testid={`skin-card-${skin.id}`}
      className="group relative w-full block text-left rounded-2xl overflow-hidden border transition-[border-color,box-shadow] duration-300"
      style={{ borderColor: `${r.color}55`, background: "#0a0c07", boxShadow: `0 18px 50px -24px ${r.color}` }}>
      <span className="pointer-events-none absolute inset-0 z-[5] rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ boxShadow: `inset 0 0 0 2px ${r.color}, 0 0 34px -6px ${r.color}` }} aria-hidden />
      <div className="relative aspect-[3/4] overflow-hidden">
        {/* rarity gradient base (Fortnite-style colour wash) */}
        <div className="absolute inset-0" style={{ background: `linear-gradient(155deg, ${r.color}dd 0%, ${r.color}55 42%, #0a0c07 100%)` }} />
        <div className="absolute inset-0" style={{ background: `radial-gradient(75% 55% at 50% 8%, ${r.color}66, transparent 75%)` }} />
        {/* item render */}
        <img src={skin.image_url} alt={skin.name} loading="lazy"
          className={`absolute inset-0 w-full h-full object-cover transition-transform duration-[700ms] ease-out group-hover:scale-[1.14] ${skin.owned ? "grayscale opacity-70" : ""}`} />
        {/* rarity tint + depth */}
        <div className="absolute inset-0 mix-blend-soft-light opacity-45" style={{ background: r.color }} />
        <div className="absolute inset-0 bg-gradient-to-t from-black/92 via-black/25 to-transparent" />
        {/* diagonal shine sweep on hover */}
        <span className="pointer-events-none absolute top-[-40%] bottom-[-40%] left-[-30%] w-1/3 rotate-[18deg] bg-white/25 blur-md z-[3] -translate-x-[220%] group-hover:translate-x-[520%] transition-transform duration-[800ms] ease-out" aria-hidden />
        {/* top chips */}
        <div className="absolute top-2.5 left-2.5 right-2.5 flex items-start justify-between gap-2 z-[4]">
          <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md backdrop-blur-sm"
            style={{ color: "#0a0c07", background: r.color, boxShadow: `0 2px 10px -2px ${r.color}` }}>{r.label}</span>
          {skin.owned && <span className="inline-flex items-center gap-1 text-[9px] font-bold px-2 py-1 rounded-md bg-emerald-500/30 text-emerald-100 border border-emerald-400/60 backdrop-blur-sm"><Check size={10} /> Tuya</span>}
        </div>
        {/* name slab (Fortnite footer) */}
        <div className="absolute bottom-0 inset-x-0 z-[4] px-3 pt-6 pb-3">
          <span className="block h-[3px] w-10 rounded-full mb-2" style={{ background: r.color, boxShadow: `0 0 10px ${r.color}` }} />
          <p className="font-display font-black uppercase tracking-tight text-[17px] leading-none truncate" style={{ textShadow: "0 2px 8px rgba(0,0,0,.8)" }}>{skin.name}</p>
          <div className="flex items-center justify-between gap-2 mt-1.5">
            <p className="text-[11px] font-semibold text-white/70 truncate">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
            <span className="shrink-0 font-code font-black tabular-nums text-xs px-2 py-0.5 rounded-full text-white" style={{ background: `${r.color}cc`, boxShadow: `inset 0 0 0 1px ${r.color}` }}>${skin.price_usd.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </motion.button>
  );
}
