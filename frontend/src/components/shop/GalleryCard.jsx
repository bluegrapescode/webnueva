import React from "react";
import { motion } from "framer-motion";
import { Check, Crown, Gem } from "lucide-react";
import { rarityOf } from "./shopRarity";

const GOLD = "#F59E0B";

// Tarjeta coleccionable de lujo (oscuro + dorado). El color de rareza se
// superpone sobre la base obsidiana; legendarias/míticas suman holograma y aura.
export function GalleryCard({ skin, onClick, play, view = "grid", index = 0 }) {
  const r = rarityOf(skin.rarity);
  const holo = skin.rarity === "legendary" || skin.rarity === "mythic";
  const mythic = skin.rarity === "mythic";
  const delay = Math.min(index * 0.035, 0.4);

  if (view === "list") {
    return (
      <motion.button layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ delay }}
        onMouseEnter={() => play?.("hover")} onClick={() => onClick?.(skin)} data-testid={`skin-card-${skin.id}`}
        className="group relative w-full flex items-center gap-4 rounded-xl overflow-hidden border border-amber-500/20 bg-[#0d0f14]/80 hover:bg-[#12151f] transition-colors text-left p-2.5"
        style={{ boxShadow: `inset 3px 0 0 ${r.color}` }}>
        <div className="relative h-16 w-24 shrink-0 rounded-lg overflow-hidden border border-white/5">
          <div className="absolute inset-0" style={{ background: `radial-gradient(80% 80% at 50% 40%, ${r.color}44, #07080a 90%)` }} />
          <img src={skin.image_url} alt={skin.name} loading="lazy" className={`absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-110 ${skin.owned ? "grayscale opacity-70" : ""}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-display font-bold text-sm truncate text-white">{skin.name}</p>
          <p className="text-[11px] text-white/45 truncate">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
        </div>
        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shrink-0" style={{ color: r.color, background: `${r.color}1a`, border: `1px solid ${r.color}44` }}>{r.label}</span>
        <span className="font-code font-black tabular-nums text-sm shrink-0 pr-2 text-amber-300">${skin.price_usd.toFixed(2)}</span>
        {skin.owned && <span className="absolute top-1.5 right-1.5 inline-flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/25 text-emerald-200"><Check size={9} /> Tuya</span>}
      </motion.button>
    );
  }

  return (
    <motion.button layout initial={{ opacity: 0, y: 22, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -8 }} transition={{ type: "spring", stiffness: 320, damping: 24, delay }}
      onMouseEnter={() => play?.("hover")} onClick={() => onClick?.(skin)} data-testid={`skin-card-${skin.id}`}
      className={`group relative w-full block text-left rounded-2xl overflow-hidden border transition-[border-color,box-shadow] duration-300 ${mythic ? "lux-mythic-aura" : ""}`}
      style={{ borderColor: `${r.color}55`, background: "#0a0b0f", boxShadow: mythic ? undefined : `0 22px 60px -28px ${r.color}, inset 0 0 0 1px rgba(245,158,11,0.06)` }}>

      {/* marco dorado giratorio en hover (legendaria/mítica) */}
      {holo && <span className="lux-conic pointer-events-none absolute -inset-8 z-0 opacity-0 group-hover:opacity-60 transition-opacity duration-300" style={{ "--rc": r.color }} aria-hidden />}
      {/* borde de brillo en hover */}
      <span className="pointer-events-none absolute inset-0 z-[6] rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ boxShadow: `inset 0 0 0 1.5px ${r.color}, inset 0 0 0 3px rgba(245,158,11,0.25), 0 0 38px -6px ${r.color}` }} aria-hidden />

      <div className="relative z-[1] m-[1px] rounded-2xl overflow-hidden bg-[#0a0b0f]">
        <div className="relative aspect-[4/5] overflow-hidden">
          {/* base de rareza + luz cenital dorada */}
          <div className="absolute inset-0" style={{ background: `linear-gradient(160deg, ${r.color}d0 0%, ${r.color}44 40%, #07080a 100%)` }} />
          <div className="absolute inset-0" style={{ background: `radial-gradient(72% 50% at 50% 6%, ${r.color}66, transparent 72%)` }} />
          <div className="absolute inset-x-0 top-0 h-1/2" style={{ background: "radial-gradient(60% 90% at 50% 0%, rgba(245,158,11,0.22), transparent 70%)" }} />

          {/* render de la skin */}
          <img src={skin.image_url} alt={skin.name} loading="lazy"
            className={`absolute inset-0 w-full h-full object-cover transition-transform duration-[720ms] ease-out group-hover:scale-[1.14] ${skin.owned ? "grayscale opacity-70" : ""}`} />

          {/* tinte de rareza + profundidad */}
          <div className="absolute inset-0 mix-blend-soft-light opacity-40" style={{ background: r.color }} />
          <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/25 to-transparent" />

          {/* holograma continuo (legendaria/mítica) */}
          {holo && <span className="lux-holo pointer-events-none absolute inset-0 z-[3] opacity-70" aria-hidden />}
          {/* barrido diagonal en hover */}
          <span className="pointer-events-none absolute top-[-40%] bottom-[-40%] left-[-30%] w-1/3 rotate-[18deg] bg-white/25 blur-md z-[4] -translate-x-[220%] group-hover:translate-x-[560%] transition-transform duration-[850ms] ease-out" aria-hidden />

          {/* chips superiores */}
          <div className="absolute top-2.5 left-2.5 right-2.5 flex items-start justify-between gap-2 z-[5]">
            <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md backdrop-blur-sm"
              style={{ color: "#0a0b0f", background: r.color, boxShadow: `0 2px 12px -2px ${r.color}` }}>
              {holo ? <Crown size={10} /> : <Gem size={10} />} {r.label}
            </span>
            {skin.owned && <span className="inline-flex items-center gap-1 text-[9px] font-bold px-2 py-1 rounded-md bg-emerald-500/30 text-emerald-100 border border-emerald-400/60 backdrop-blur-sm"><Check size={10} /> Tuya</span>}
          </div>

          {/* placa inferior con nombre */}
          <div className="absolute bottom-0 inset-x-0 z-[5] px-3.5 pt-7 pb-3.5">
            <span className="block h-[3px] w-12 rounded-full mb-2" style={{ background: "linear-gradient(90deg,#FEF08A,#F59E0B)", boxShadow: "0 0 10px rgba(245,158,11,0.8)" }} />
            <p className="font-display font-black uppercase tracking-tight text-[18px] leading-none truncate text-white" style={{ textShadow: "0 2px 10px rgba(0,0,0,.85)" }}>{skin.name}</p>
            <div className="flex items-center justify-between gap-2 mt-2">
              <p className="text-[11px] font-semibold text-white/60 truncate">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
              <span className="shrink-0 font-code font-black tabular-nums text-xs px-2.5 py-1 rounded-full text-black" style={{ background: "linear-gradient(135deg,#FCD34D,#F59E0B)", boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.35)` }}>${skin.price_usd.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </motion.button>
  );
}
