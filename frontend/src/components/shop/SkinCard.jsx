import React from "react";
import { motion } from "framer-motion";
import { Check, Clock, Zap } from "lucide-react";
import { rarityOf } from "./shopRarity";
import { Countdown } from "./Countdown";

// Legendary, aggressive Fortnite-style card: notched geometry, rotating conic
// rarity frame on hover, rarity light-beam, holo sheen on legendary/mythic.
export function SkinCard({ skin, onClick, play, featured = false }) {
  const r = rarityOf(skin.rarity);
  const holo = skin.rarity === "legendary" || skin.rarity === "mythic";
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 24, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      whileHover={{ y: -6, scale: 1.02 }}
      transition={{ type: "spring", stiffness: 320, damping: 22 }}
      onMouseEnter={() => play?.("hover")}
      onClick={() => onClick?.(skin)}
      data-testid={`skin-card-${skin.id}`}
      className="skin-card clip-notch group relative w-full h-full block text-left"
      style={{ "--rc": r.color, boxShadow: `0 0 0 1px ${r.color}44, 0 20px 55px -20px ${r.color}` }}
    >
      <span className="skin-card__frame" aria-hidden />
      <div className="skin-card__inner clip-notch">
        {/* rarity beam */}
        <div className="absolute inset-x-0 top-0 h-2/3" style={{ background: `radial-gradient(60% 90% at 50% 0%, ${r.color}55, transparent 70%)` }} />
        <img
          src={skin.image_url}
          alt={skin.name}
          loading="lazy"
          className={`absolute inset-0 w-full h-full object-cover transition-transform duration-[650ms] ease-out group-hover:scale-[1.12] ${skin.owned ? "grayscale opacity-70" : ""}`}
        />
        {holo && !skin.owned && <div className="skin-card__holo" aria-hidden />}
        <div className="absolute inset-0 bg-gradient-to-t from-black/92 via-black/25 to-black/10" />
        {/* diagonal accent line */}
        <div className="absolute left-0 top-0 h-full w-[3px]" style={{ background: `linear-gradient(to bottom, ${r.color}, transparent)` }} />

        {/* top badges */}
        <div className="absolute top-3 left-3 right-3 flex items-start justify-between gap-2">
          <span className="inline-flex items-center gap-1 label-overline text-[9px] px-2 py-1 border backdrop-blur-sm clip-notch-sm"
            style={{ color: r.color, borderColor: `${r.color}77`, background: `${r.color}22` }}>
            <Zap size={9} /> {r.label}
          </span>
          {skin.owned && (
            <span className="inline-flex items-center gap-1 text-[9px] font-bold px-2 py-1 bg-emerald-500/25 text-emerald-200 border border-emerald-400/50 backdrop-blur-sm clip-notch-sm">
              <Check size={10} /> Tuya
            </span>
          )}
        </div>

        {/* bottom info */}
        <div className="absolute inset-x-0 bottom-0 p-3.5">
          <div className="flex items-center gap-1.5 text-[10px] font-code text-white/55 mb-1">
            <Clock size={10} /> <Countdown endAt={skin.end_at} />
          </div>
          <p className={`font-display font-black uppercase tracking-tight text-white leading-none drop-shadow ${featured ? "text-2xl sm:text-3xl" : "text-base"}`}>
            {skin.name}
          </p>
          {skin.dino_species && (
            <p className="text-[10px] text-white/45 truncate mt-0.5">{skin.dino_species}</p>
          )}
          <div className="mt-2.5 inline-flex items-center gap-1.5 price-tag px-3 py-1"
            style={{ background: `${r.color}`, color: "#0b0d09" }}>
            <span className="font-code font-black tabular-nums" style={{ fontSize: featured ? 16 : 13 }}>
              ${skin.price_usd.toFixed(2)}
            </span>
          </div>
        </div>

        <span className="skin-card__sheen" aria-hidden />
      </div>
    </motion.button>
  );
}
