import React from "react";

// Colors matched exactly to the DNA SkinIcon palette (see SkinIcon.jsx).
const RARITY_STYLES = {
  Apex: "text-crimson border-crimson/40 bg-crimson/10",
  Legendary: "text-[#f97316] border-[#f97316]/40 bg-[#f97316]/10",
  Epic: "text-[#a855f7] border-[#a855f7]/40 bg-[#a855f7]/10",
  Rare: "text-[#3b82f6] border-[#3b82f6]/40 bg-[#3b82f6]/10",
  Uncommon: "text-[#22c55e] border-[#22c55e]/40 bg-[#22c55e]/10",
  Common: "text-muted-foreground border-border bg-secondary",
};

export function RarityBadge({ rarity = "Common", className = "" }) {
  const style = RARITY_STYLES[rarity] || RARITY_STYLES.Common;
  return (
    <span className={`inline-flex items-center label-overline text-[10px] px-2 py-0.5 rounded-full border ${style} ${className}`}>
      {rarity}
    </span>
  );
}

export const TYPE_COLORS = {
  Carnivore: "text-crimson",
  Herbivore: "text-emerald",
  Omnivore: "text-gold",
};
