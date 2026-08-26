import React from "react";
import { motion } from "framer-motion";
import { Trophy } from "lucide-react";
import { GlitchProx } from "@/components/common/GlitchProx";
import { prizeCards } from "@/lib/leaderboardPrizes";

// A cosmetic rider on a rank's prize (2026-08-16: 1º wins the "Supernova"
// glitch skin, owner order; 2026-08-18: 1º/2º/3º all wear it). Rendered as a
// NAME + the glitch family face, never a per-skin render (fleet order
// 2026-08-11) — `normalizeSkin` drops `image` before it can reach here at all.
//
// The thumb is a FIXED square that never grows: this strip is three columns even
// at 390px, where the 2026-08-12 ship already had to shrink the prize amount to
// stop it clipping. So everything below the amount is laid out to survive that
// width — a fixed 28/36px box, and a name that wraps to two lines and then
// truncates inside a `min-w-0` flex child (without which a long name pushes the
// card past its column).
function PrizeSkin({ skin, color }) {
  if (!skin) return null;
  return (
    <div className="mt-1.5 sm:mt-2 flex items-center gap-1.5 sm:gap-2 border-t pt-1.5 sm:pt-2"
      style={{ borderColor: color + "33" }}
      data-testid={`lb-prize-skin-${skin.glitch_id || "x"}`}>
      <div className="h-7 w-7 sm:h-9 sm:w-9 shrink-0 overflow-hidden rounded border"
        style={{ borderColor: color + "55" }}>
        <GlitchProx proximity={skin.proximity} accent={skin.accent} compact />
      </div>
      <div className="min-w-0">
        <div className="text-[9px] sm:text-[10px] font-bold leading-tight text-white/90 line-clamp-2 break-words">
          {skin.name}
        </div>
        <div className="text-[8px] sm:text-[9px] font-semibold tracking-wider text-white/40">
          SKIN
        </div>
      </div>
    </div>
  );
}

export function PrizeShowcase({ prizes, prizeSkins }) {
  const cards = prizeCards(prizes, prizeSkins);
  return (
    <div className="mt-4 sm:mt-5 grid grid-cols-3 gap-2 sm:gap-4" data-testid="lb-prizes">
      {cards.map((m, i) => (
        <motion.div
          key={m.rank}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 + i * 0.08, type: "spring", stiffness: 220, damping: 20 }}
          className="relative overflow-hidden rounded-md border p-2.5 sm:p-4 min-w-0"
          style={{
            borderColor: m.color + "55",
            background: `linear-gradient(135deg, ${m.color}12, rgba(0,0,0,0.5))`,
          }}
        >
          <div className="flex items-center gap-2">
            <span className="text-lg sm:text-2xl">{m.medal}</span>
            <div className="text-[9px] sm:text-[10px] font-black tracking-widest" style={{ color: m.color }}>
              PREMIO {m.label}
            </div>
          </div>
          <div className="mt-1 sm:mt-2 flex items-baseline gap-1">
            <img src="/coins/meat.png" alt="" className="h-4 w-4 sm:h-5 sm:w-5 object-contain" onError={(e) => e.currentTarget.style.display="none"} />
            <span className="text-sm sm:text-2xl font-black tabular-nums" style={{ color: m.color }}>
              {m.amount.toLocaleString()}
            </span>
          </div>
          <div className="text-[9px] sm:text-[10px] font-bold text-white/50 tracking-wider mt-0.5">PrimeMeat</div>
          <PrizeSkin skin={m.skin} color={m.color} />
        </motion.div>
      ))}
    </div>
  );
}
