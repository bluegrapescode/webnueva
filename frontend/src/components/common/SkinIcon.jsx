import React from "react";
import { Dna } from "lucide-react";

// DNA-strand visual for skins, colored by rarity (per design request).
export const DNA_COLORS = {
  Common: "#8b8b94",
  Uncommon: "#22c55e",   // green
  Rare: "#3b82f6",       // blue
  Epic: "#a855f7",       // purple
  Legendary: "#f97316",  // orange
  Mythic: "#f97316",
  Apex: "#f97316",
};

// Owner-made rarity medallions (glowing dino-claw emblems) shown in place of
// the generic DNA icon for the tiers he supplied art for. Colours line up with
// DNA_COLORS (green/purple/gold). Any other rarity keeps the DNA fallback, and
// if a medallion fails to load it falls back too, so the card never breaks.
const RARITY_MEDALLION = {
  Uncommon: "/skins/rarity/uncommon.png",
  Epic: "/skins/rarity/epic.png",
  Legendary: "/skins/rarity/legendary.png",
};

export function SkinIcon({ rarity = "Common", color, className = "", iconClass = "w-1/2 h-1/2" }) {
  const c = color || DNA_COLORS[rarity] || DNA_COLORS.Common;
  const medallion = RARITY_MEDALLION[rarity];
  const [imgOk, setImgOk] = React.useState(true);
  return (
    <div
      className={`w-full h-full flex items-center justify-center ${className}`}
      style={{ background: `radial-gradient(circle at 50% 38%, ${c}33, #0b0b0e 75%)` }}
    >
      {medallion && imgOk ? (
        <img
          src={medallion}
          alt={`Skin ${rarity}`}
          loading="lazy"
          className="w-[92%] h-[92%] object-contain"
          style={{ filter: `drop-shadow(0 0 8px ${c}aa)` }}
          onError={() => setImgOk(false)}
        />
      ) : (
        <Dna className={iconClass} style={{ color: c, filter: `drop-shadow(0 0 10px ${c}cc)` }} strokeWidth={1.6} />
      )}
    </div>
  );
}
