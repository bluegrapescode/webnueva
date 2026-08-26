import React from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Check } from "lucide-react";
import { CURRENCY } from "@/lib/currency";
import { GOLD, fmtNum, rewardIcon, speciesName } from "@/components/battlepass/RewardCard";

function burstLabel(reward, nameBySlug) {
  if (!reward) return "";
  if (reward.name) return reward.name;
  if (reward.type === "coins") return `${fmtNum(reward.amount)} ${CURRENCY.normal.name}`;
  if (reward.type === "amber") return `${fmtNum(reward.amount)} ${CURRENCY.vip.name}`;
  if (reward.type === "token") {
    const kind = reward.token === "diet" ? "Token de Dieta" : "Token de Crecimiento";
    return reward.tier === "premium" ? `${kind} Premium` : kind;
  }
  if (reward.type === "skin") return reward.skin?.name || "Skin del pase";
  if (reward.type === "dino") return speciesName(reward.slug, nameBySlug);
  return "Recompensa";
}

/**
 * Full-screen claim celebration. Adapted from the owner's prototype: same
 * particle ring and pop-in, retuned to the site palette (`bg-charcoal` does not
 * exist here) and extended with the effect lines a token redeem returns.
 */
export function ClaimBurst({ show, reward, effects, title, nameBySlug }) {
  return createPortal(
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="pointer-events-none fixed inset-0 z-[1300] flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
          data-testid="bp-claim-burst"
        >
          {Array.from({ length: 36 }).map((_, i) => {
            const angle = (i / 36) * Math.PI * 2;
            const dist = 190 + (i % 7) * 30;
            return (
              <motion.div
                key={i}
                className="absolute h-2 w-2 rounded-full"
                style={{ background: i % 2 === 0 ? GOLD : "#7CA842", boxShadow: "0 0 8px currentColor" }}
                initial={{ x: 0, y: 0, scale: 1, opacity: 1 }}
                animate={{ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist, scale: 0, opacity: 0 }}
                transition={{ duration: 1.4, ease: "easeOut" }}
              />
            );
          })}

          <motion.div
            className="absolute h-40 w-40 rounded-full"
            style={{ background: `radial-gradient(circle, ${GOLD}e6, transparent 60%)` }}
            initial={{ scale: 0, opacity: 1 }}
            animate={{ scale: 6, opacity: 0 }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          />

          <motion.div
            initial={{ scale: 0.5, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.85, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            className="relative flex max-w-sm flex-col items-center gap-3 rounded-2xl border p-7 text-center"
            style={{ borderColor: `${GOLD}66`, background: "#0b0b0e", boxShadow: `0 0 60px ${GOLD}55` }}
          >
            {reward && rewardIcon(reward) ? (
              <motion.img
                src={rewardIcon(reward)}
                alt=""
                className="h-24 w-24 object-contain drop-shadow-[0_0_18px_rgba(234,179,8,0.6)] sm:h-28 sm:w-28"
                initial={{ scale: 0.4, opacity: 0, y: -20 }}
                animate={{ scale: [0.4, 1.15, 1], opacity: 1, y: 0 }}
                transition={{ duration: 0.55, times: [0, 0.6, 1], ease: [0.16, 1, 0.3, 1] }}
                onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
              />
            ) : (
              <Sparkles size={64} style={{ color: GOLD }} />
            )}

            <div className="label-overline text-[10px]" style={{ color: `${GOLD}b3` }}>
              {title || "Recompensa reclamada"}
            </div>
            {reward && (
              <div className="font-display text-xl font-extrabold tracking-tight sm:text-2xl" data-testid="bp-claim-burst-label">
                {burstLabel(reward, nameBySlug)}
              </div>
            )}

            {effects && effects.length > 0 && (
              <ul className="mt-1 w-full space-y-1.5 text-left" data-testid="bp-claim-burst-effects">
                {effects.map((e, i) => (
                  <li key={i} className="flex items-start gap-2 text-[13px] text-foreground/85">
                    <Check size={14} className="mt-0.5 shrink-0 text-emerald" />
                    <span>{e}</span>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default ClaimBurst;
