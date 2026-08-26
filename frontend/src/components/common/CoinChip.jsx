import React from "react";
import { MEDIA } from "@/lib/media";
import { CURRENCY } from "@/lib/currency";

export function CoinChip({ type = "normal", amount, size = "md", className = "", showLabel = false }) {
  const icon = type === "vip" ? MEDIA.coinVip : MEDIA.coinNormal;
  const sizes = { sm: "w-4 h-4", md: "w-6 h-6", lg: "w-8 h-8", xl: "w-12 h-12" };
  const text = { sm: "text-sm", md: "text-base", lg: "text-xl", xl: "text-3xl" };
  const cur = type === "vip" ? CURRENCY.vip : CURRENCY.normal;
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold ${className}`} data-testid={`coin-chip-${type}`}>
      <img src={icon} alt={cur.name} className={`${sizes[size]} object-contain drop-shadow`} />
      {amount !== undefined && (
        <span className={`${text[size]} tabular-nums ${type === "vip" ? "text-gold" : "text-emerald"}`}>
          {Number(amount).toLocaleString()}
        </span>
      )}
      {showLabel && <span className="label-overline text-[10px] text-muted-foreground">{cur.name}</span>}
    </span>
  );
}
