import React, { memo, useState } from "react";
import { motion } from "framer-motion";
import { Check, Lock, Crown, Palette, Ban } from "lucide-react";
import { CURRENCY } from "@/lib/currency";
import { pickIconSlug } from "@/lib/bpPickIcon";
import { HudCorners } from "@/components/common/Hud";

// The tailwind `gold` token on this site is the brand GREEN (#7CA842). Real
// gold-yellow — used only for premium / Amberium accents — is this constant,
// same convention as PatreonTiers.jsx.
export const GOLD = "#EAB308";

// One fixed locale for every figure on this page: the hardcoded copy already
// writes dot-grouped Spanish numbers ("2.000.000"), so a visitor's en-US
// browser must not render the track cells with commas beside them.
export const fmtNum = (n) => Number(n || 0).toLocaleString("es-AR");

const META = {
  coins: { color: "#A3C96B", ring: "rgba(124,168,66,0.35)" },
  amber: { color: GOLD, ring: "rgba(234,179,8,0.35)" },
  token: { color: "#34D399", ring: "rgba(52,211,153,0.35)" },
  skin: { color: "#A855F7", ring: "rgba(168,85,247,0.35)" },
  dino: { color: "#E24A4A", ring: "rgba(226,74,74,0.35)" },
  empty: { color: "#6B7280", ring: "rgba(107,114,128,0.0)" },
};

const RARITY_COLOR = {
  Legendary: "#F97316",
  Epic: "#A855F7",
  Rare: "#3B82F6",
  Uncommon: "#22C55E",
  Common: "#9CA3AF",
};

export const BAND_LABEL = { low: "Bajo", mid: "Medio", high: "Alto", apex: "Ápex", all: "Todas + Ápex" };

export function speciesName(slug, nameBySlug) {
  if (!slug) return "";
  const found = nameBySlug && nameBySlug[slug];
  if (found) return found;
  return String(slug).charAt(0).toUpperCase() + String(slug).slice(1);
}

// v2: there is NO free row and NO halving — two paid rows, every figure literal.
export function displayAmount(cell) {
  return Number(cell.amount || 0);
}

// Diet restores 150% on a basic token and 300% on a premium one; the flavor is
// fixed per ROW now (regular row = basic, premium row = premium) and the
// backend sends it on the cell. Growth always grows to 70%.
export function tokenDetail(cell, track) {
  if (cell.token === "growth") return "70%";
  const flavor = cell.tier || (track === "premium" ? "premium" : "basic");
  return flavor === "premium" ? "300%" : "150%";
}

// A PICK cell carries a band and no species yet, so it used to fall through to
// the generic crown badge while the fixed level-100 cell showed real dino art.
// Owner order 2026-08-08: a dino cell shows a DINO either way — the stand-in
// species per band lives in lib/bpPickIcon.
export function rewardIcon(cell) {
  if (!cell) return null;
  if (cell.type === "token") return cell.token === "diet" ? "/tokens/diet.png" : "/tokens/growth.png";
  if (cell.type === "coins") return "/coins/meat.png";
  if (cell.type === "amber") return "/coins/amber.png";
  if (cell.type === "dino") {
    if (cell.slug) return `/dinos/${cell.slug}.png`;
    const stand = pickIconSlug(cell);
    return stand ? `/dinos/${stand}.png` : null;
  }
  return null;
}

// Two short lines so every card is the same height and nothing is truncated
// into nonsense on a phone.
export function rewardLines(cell, track, viewerTier, nameBySlug) {
  if (cell.type === "coins") return [fmtNum(displayAmount(cell)), CURRENCY.normal.short];
  if (cell.type === "amber") return [fmtNum(displayAmount(cell)), CURRENCY.vip.short];
  if (cell.type === "token") {
    return [cell.token === "diet" ? "DIETA" : "CRECIMIENTO", tokenDetail(cell, track)];
  }
  if (cell.type === "skin") return [cell.skin?.name || "SKIN", cell.skin?.rarity || "Skin"];
  if (cell.type === "dino") {
    if (cell.slug) return [speciesName(cell.slug, nameBySlug), "75%"];
    return ["ELIGE DINO", `${BAND_LABEL[cell.band] || "Banda"} · 75%`];
  }
  return ["Sin", "recompensa"];
}

// Full sentence for screen readers and the aria-label — the two-line card text
// is deliberately terse.
export function rewardSpoken(cell, track, viewerTier, nameBySlug) {
  if (cell.type === "coins") return `${fmtNum(displayAmount(cell))} ${CURRENCY.normal.name}`;
  if (cell.type === "amber") return `${fmtNum(displayAmount(cell))} ${CURRENCY.vip.name}`;
  if (cell.type === "token") {
    const kind = cell.token === "diet" ? "Token de Dieta" : "Token de Crecimiento";
    return `${kind} ${tokenDetail(cell, track)}`;
  }
  if (cell.type === "skin") return `Skin ${cell.skin?.name || ""} ${cell.skin?.rarity || ""}`.trim();
  if (cell.type === "dino") {
    if (cell.slug) return `${speciesName(cell.slug, nameBySlug)} al 75%`;
    if (cell.band === "all") return "Elige cualquier especie, ápex incluidos, al 75%";
    return `Elige un dino de banda ${BAND_LABEL[cell.band] || cell.band} al 75%`;
  }
  return "Sin recompensa";
}

function RewardCardBase({ cell, track, currentLevel, claimed, viewerTier, nameBySlug, busy, onClaim }) {
  const level = cell.level;
  // v2: two PAID rows. The regular row needs any pass; the premium row needs
  // Premium+. Nobody claims anything without buying (or a staff gift).
  const isPremiumRow = track === "premium";
  const meta = META[cell.type] || META.empty;
  const icon = rewardIcon(cell);
  // A picture that 404s used to leave a hole in the card (visibility:hidden).
  // Remember the src that failed instead, so the badge below takes over and the
  // cell still reads as a reward. Keyed by src: a re-rendered cell that swapped
  // to a different picture gets a fresh try.
  const [badIcon, setBadIcon] = useState(null);
  const showIcon = !!icon && badIcon !== icon;
  const [line1, line2] = rewardLines(cell, track, viewerTier, nameBySlug);

  const hasAnyPass = viewerTier === "regular" || viewerTier === "premium_plus";
  const lock =
    cell.type === "empty" ? "empty"
      : claimed ? "claimed"
        : level > currentLevel ? "level"
          : !hasAnyPass ? "pass"
            : isPremiumRow && viewerTier !== "premium_plus" ? "premium"
              : null;
  const eligible = !lock && !busy;
  const primeBadge = isPremiumRow && cell.type === "dino";

  const fire = () => { if (eligible && onClaim) onClaim(track, cell); };
  const onKeyDown = (e) => {
    if ((e.key === "Enter" || e.key === " ") && eligible) { e.preventDefault(); fire(); }
  };

  const stateWord =
    lock === "claimed" ? " (reclamado)"
      : lock === "level" ? ` (bloqueado, requiere nivel ${level})`
        : lock === "pass" ? " (requiere el pase)"
          : lock === "premium" ? " (solo Premium+)"
            : "";

  return (
    <motion.div
      role={eligible ? "button" : undefined}
      tabIndex={eligible ? 0 : -1}
      data-level={level}
      data-testid={`bp-reward-${track}-${level}`}
      aria-label={`Nivel ${level}, ${isPremiumRow ? "fila premium" : "fila regular"}: ${rewardSpoken(cell, track, viewerTier, nameBySlug)}${stateWord}`}
      whileHover={eligible ? { y: -4, scale: 1.03 } : undefined}
      whileTap={eligible ? { scale: 0.97 } : undefined}
      transition={{ type: "spring", stiffness: 400, damping: 24 }}
      onClick={fire}
      onKeyDown={onKeyDown}
      // Skipped off-screen work without a virtualization library: the box is
      // fully sized by CSS, so nothing shifts when a card comes back into view.
      style={{ contentVisibility: "auto" }}
      className={`relative shrink-0 select-none snap-start w-[86px] sm:w-[110px] h-[125px] sm:h-[150px]
        ${eligible ? "cursor-pointer" : ""} focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 rounded-md`}
    >
      <div
        className={`relative flex h-full w-full flex-col items-center justify-between overflow-hidden rounded-md border p-1.5 sm:p-2 pt-3
          ${isPremiumRow ? "border-[#EAB308]/40" : "border-white/12"}
          ${cell.type === "empty" ? "bg-white/[0.02]" : eligible ? "bg-gradient-to-br from-black/60 to-black/25" : "bg-black/40"}
          ${lock === "pass" || lock === "premium" ? "opacity-55" : ""}`}
        style={{
          boxShadow: eligible
            ? `0 0 18px ${meta.ring}, inset 0 0 26px rgba(0,0,0,0.5)`
            : "inset 0 0 18px rgba(0,0,0,0.55)",
        }}
      >
        <HudCorners color={isPremiumRow ? "#EAB30888" : "#6b728088"} size={12} thickness={1} />

        {/* level number */}
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 rounded-b px-1.5 sm:px-2 py-[1px] font-mono text-[9px] sm:text-[10px] font-extrabold tracking-wider"
          style={{
            background: isPremiumRow ? "linear-gradient(180deg,#EAB308,#8a6b12)" : "rgba(255,255,255,0.08)",
            color: isPremiumRow ? "#0a0a0a" : "#d1d5db",
          }}
        >
          {level}
        </div>

        {cell.type === "empty" ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 px-1">
            <Ban size={16} className="text-white/20" />
            <span className="text-[9px] sm:text-[10px] leading-tight text-center text-muted-foreground/70">Sin recompensa</span>
          </div>
        ) : (
          <>
            <div className="mt-3 flex flex-1 items-center justify-center">
              {showIcon ? (
                <img
                  src={icon}
                  alt=""
                  loading="lazy"
                  draggable={false}
                  className="h-9 w-9 sm:h-12 sm:w-12 object-contain drop-shadow-[0_0_10px_rgba(0,0,0,0.6)] pointer-events-none"
                  onError={() => setBadIcon(icon)}
                />
              ) : cell.type === "skin" ? (
                <div
                  className="flex h-9 w-9 sm:h-12 sm:w-12 items-center justify-center rounded-full"
                  style={{ background: `radial-gradient(circle, ${RARITY_COLOR[cell.skin?.rarity] || meta.color} 0%, transparent 70%)` }}
                >
                  <Palette size={20} className="text-white/90" />
                </div>
              ) : (
                <div
                  className="flex h-9 w-9 sm:h-12 sm:w-12 items-center justify-center rounded-full"
                  style={{ background: `radial-gradient(circle, ${meta.color}55 0%, transparent 70%)` }}
                >
                  <Crown size={18} style={{ color: meta.color }} />
                </div>
              )}
            </div>

            <div className="w-full px-0.5 text-center">
              <p
                className="truncate font-display text-[10px] sm:text-[11px] font-extrabold leading-tight"
                style={{ color: cell.type === "skin" ? (RARITY_COLOR[cell.skin?.rarity] || meta.color) : meta.color }}
              >
                {line1}
              </p>
              <p className="truncate text-[9px] sm:text-[10px] leading-tight text-muted-foreground">{line2}</p>
            </div>
          </>
        )}

        {primeBadge && (
          <div className="absolute right-1 top-1 rounded-sm px-1 py-[1px] text-[7px] sm:text-[8px] font-extrabold text-black" style={{ background: GOLD }}>
            PRIME
          </div>
        )}
        {cell.bonus_skin && (
          <div className="absolute left-1 bottom-1 rounded-sm px-1 py-[1px] text-[7px] sm:text-[8px] font-extrabold text-black truncate max-w-[90%]"
            style={{ background: cell.bonus_skin.accent_hex || GOLD }}
            data-testid="bp-apex-bonus-skin">
            + {cell.bonus_skin.name}
          </div>
        )}

        {lock === "claimed" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70">
            <div className="flex h-9 w-9 sm:h-12 sm:w-12 items-center justify-center rounded-full border-2 border-emerald bg-emerald/20">
              <Check size={18} className="text-emerald" />
            </div>
          </div>
        )}
        {lock === "level" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <Lock size={16} className="text-white/35" />
          </div>
        )}
        {(lock === "pass" || lock === "premium") && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/60">
            <Crown size={16} style={{ color: GOLD }} />
            <span className="text-[8px] font-extrabold tracking-wide" style={{ color: GOLD }}>
              {lock === "premium" ? "PREMIUM+" : "PASE"}
            </span>
          </div>
        )}
        {eligible && (
          <motion.div
            className="pointer-events-none absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.15, 0.35, 0.15] }}
            transition={{ duration: 2.2, repeat: Infinity }}
            style={{ background: `radial-gradient(ellipse at center, ${meta.ring} 0%, transparent 60%)` }}
          />
        )}
      </div>
    </motion.div>
  );
}

// 200 cells live in one scroller — without this comparator every card re-renders
// on each parent tick (the 1 s season countdown alone would do it).
export const RewardCard = memo(RewardCardBase, (a, b) =>
  a.cell === b.cell &&
  a.track === b.track &&
  a.currentLevel === b.currentLevel &&
  a.claimed === b.claimed &&
  a.viewerTier === b.viewerTier &&
  a.nameBySlug === b.nameBySlug &&
  a.busy === b.busy &&
  a.onClaim === b.onClaim
);

export default RewardCard;
