import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Copy, Check, Crown } from "lucide-react";
import { toast } from "sonner";
import { LevelBadge } from "./LevelBadge";
import { GlitchProx } from "@/components/common/GlitchProx";
import { RarityBadge } from "@/components/common/RarityBadge";
import { prizeCards } from "@/lib/leaderboardPrizes";

const SCOPES = [
  { key: "all",   label: "Histórico" },
  { key: "month", label: "Este Mes" },
];

// Purple / navy dark palette (matches PNL leaderboard reference)
const CARD_BG      = "#161225";
const CARD_BG_ALT  = "#1B1630";
const BORDER_SOFT  = "rgba(255,255,255,0.05)";
const ACCENT_PURPLE = "#8B5CF6";

function CopyCell({ value }) {
  const [copied, setCopied] = useState(false);
  const copy = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success("✓ Código copiado");
      setTimeout(() => setCopied(false), 1400);
    } catch (_) {}
  };
  return (
    <button onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.03] px-2 py-1 font-mono text-[11px] font-black tracking-widest text-white/80 hover:bg-white/[0.08] transition"
    >
      {value}
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} className="text-white/40" />}
    </button>
  );
}

function Avatar({ src, name, size = "sm", color }) {
  const sz = size === "lg" ? "h-11 w-11 text-sm" : "h-9 w-9 text-xs";
  return (
    <div className={`relative flex ${sz} shrink-0 items-center justify-center rounded-full border overflow-hidden font-black uppercase`}
      style={{
        borderColor: color ? color + "88" : "rgba(255,255,255,0.10)",
        background: color ? `linear-gradient(135deg, ${color}33, rgba(0,0,0,0.7))` : "rgba(255,255,255,0.04)",
        color: color || "#fff",
      }}>
      {src
        ? <img src={src} alt="" className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
        : (name || "?")[0]}
    </div>
  );
}

function Row({ entry, isMe, scope, isLast }) {
  const rank = entry.rank;
  const total = scope === "month" ? entry.monthly_referrals : entry.total_referrals;
  const podiumColor = rank === 1 ? "#D4AF37" : rank === 2 ? "#C0C6D0" : rank === 3 ? "#CD7F32" : null;

  return (
    <motion.div
      layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 6 }}
      transition={{ type: "spring", stiffness: 380, damping: 32 }}
      className={`grid grid-cols-[80px_minmax(180px,1.5fr)_1fr_1fr_1fr_1fr] items-center gap-4 px-6 py-4 transition-colors ${
        isMe ? "bg-purple-500/[0.08]" : "hover:bg-white/[0.02]"
      } ${isLast ? "" : "border-b border-white/[0.04]"}`}
      data-testid={`cp-lb-row-${entry.user_id}`}
    >
      {/* RANK */}
      <div className="font-mono text-lg font-black tabular-nums" style={{ color: podiumColor || "rgba(255,255,255,0.5)" }}>
        {rank}
      </div>
      {/* NAME */}
      <div className="flex items-center gap-3 min-w-0">
        <Avatar src={entry.avatar} name={entry.display_name} color={podiumColor} />
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-sm truncate text-white">{entry.display_name}</span>
            {rank === 1 && <Crown size={11} className="text-gold shrink-0" fill="#D4AF37" />}
            {isMe && <span className="rounded-sm bg-purple-500 px-1.5 py-0.5 text-[8px] font-black tracking-widest text-white">VOS</span>}
          </div>
          <div className="text-[11px] text-white/40 font-mono truncate">@{(entry.display_name || "creator").toLowerCase()}</div>
        </div>
      </div>
      {/* REFERRALS */}
      <div>
        <div className="text-[10px] font-black tracking-widest text-white/30">REFS</div>
        <div className="text-base font-black text-white tabular-nums">{Number(total || 0).toLocaleString()}</div>
      </div>
      {/* WIN RATE (calculated from level progression) */}
      <div className="text-emerald-400 text-sm font-black tabular-nums">
        {(entry.monthly_referrals && entry.total_referrals) ? ((entry.monthly_referrals / entry.total_referrals) * 100).toFixed(1) : "0.0"}%
      </div>
      {/* EARNED */}
      <div className="text-white text-sm font-black tabular-nums">
        {Math.round((entry.total_prime_meat_earned || 0) / 1000).toLocaleString()}K
      </div>
      {/* CODE */}
      <div className="text-right">
        <CopyCell value={entry.code} />
      </div>
    </motion.div>
  );
}

// ============================================================================
// Featured top-3 cards (like the reference design)
// ============================================================================

// The monthly PrimeMeat prize + prize-skin card for one podium rank — never a
// picture (fleet order 2026-08-11): NAME + colour-proximity strip + rarity,
// same GlitchProx face + PrizeShowcase visual language the main Clasificación
// page uses (src/pages/Leaderboard.jsx + src/lib/leaderboardPrizes.js).
function PodiumPrize({ prize }) {
  if (!prize || (!prize.amount && !prize.skin)) return null;
  return (
    <div className="relative mt-4 pt-4 border-t border-white/[0.06]" data-testid={`cp-podium-prize-${prize.rank}`}>
      <div className="flex items-center gap-1.5 mb-2">
        <Trophy size={11} className="text-gold" />
        <span className="text-[9px] font-black tracking-[0.3em] text-white/40">PREMIO DEL MES</span>
      </div>
      {prize.amount > 0 && (
        <div className="flex items-center gap-1.5">
          <img src="/coins/meat.png" alt="" className="h-4 w-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
          <span className="text-lg font-black tabular-nums text-gold">{prize.amount.toLocaleString()}</span>
          <span className="text-[10px] font-bold text-white/40">PrimeMeat</span>
        </div>
      )}
      {prize.skin && (
        <div className="mt-2 flex items-center gap-2">
          <div className="h-9 w-9 shrink-0 overflow-hidden rounded border border-white/10">
            <GlitchProx proximity={prize.skin.proximity} compact />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-bold leading-tight text-white/90 truncate">{prize.skin.name}</div>
            {prize.rarity && <RarityBadge rarity={prize.rarity} className="mt-0.5" />}
          </div>
        </div>
      )}
    </div>
  );
}

function TopCard({ entry, rank, highlight, prize }) {
  const color = rank === 1 ? "#D4AF37" : rank === 2 ? "#C0C6D0" : "#CD7F32";
  const label = rank === 1 ? "1ST" : rank === 2 ? "2ND" : "3RD";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 + rank * 0.05, duration: 0.45, ease: [0.2, 0.9, 0.3, 1] }}
      className="relative overflow-hidden rounded-2xl p-5"
      style={{
        background: `linear-gradient(180deg, ${CARD_BG_ALT} 0%, ${CARD_BG} 100%)`,
        border: highlight ? `1.5px solid ${ACCENT_PURPLE}` : `1px solid ${BORDER_SOFT}`,
        boxShadow: highlight ? `0 0 40px rgba(139,92,246,0.28)` : "none",
      }}
    >
      {/* subtle inner top accent */}
      {highlight && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{ background: `linear-gradient(90deg, transparent, ${ACCENT_PURPLE}, transparent)` }} />
      )}
      <div className="pointer-events-none absolute -top-16 -right-12 h-40 w-40 rounded-full opacity-25"
        style={{ background: `radial-gradient(circle, ${color}, transparent 65%)` }} />

      {/* Header: avatar + name / rank + code */}
      <div className="relative flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Avatar src={entry.avatar} name={entry.display_name} size="lg" color={color} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-black text-base sm:text-lg truncate text-white">{entry.display_name}</span>
              {rank === 1 && <Crown size={12} className="text-gold shrink-0" fill="#D4AF37" />}
            </div>
            <div className="text-[11px] text-white/40 font-mono">@{(entry.display_name || "creator").toLowerCase()}</div>
          </div>
        </div>
        <span
          className="shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[9px] font-black tracking-[0.3em]"
          style={{ borderColor: color + "55", background: color + "18", color }}
        >
          {label}
        </span>
      </div>

      {/* Stats grid — like PNL/Followers/Win Rate/Profit */}
      <div className="relative mt-5 grid grid-cols-4 gap-3">
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">REFS</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Number(entry.total_referrals || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">MES</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Number(entry.monthly_referrals || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">TASA</div>
          <div className="mt-0.5 text-base font-black text-emerald-400 tabular-nums">
            {(entry.monthly_referrals && entry.total_referrals) ? ((entry.monthly_referrals / entry.total_referrals) * 100).toFixed(1) : "0.0"}%
          </div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">GANADO</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Math.round((entry.total_prime_meat_earned || 0) / 1000)}K</div>
        </div>
      </div>

      {/* Monthly PrimeMeat prize + prize-skin card for this rank */}
      <PodiumPrize prize={prize} />

      {/* Code + copy */}
      <div className="relative mt-4">
        <CopyCell value={entry.code} />
      </div>
    </motion.div>
  );
}

// ============================================================================
// Main component
// ============================================================================
export function CreatorLeaderboard({ boards, currentUserId, defaultScope = "all", prizeSkins, monthlyPrizes }) {
  const [scope, setScope] = useState(defaultScope);
  const board = boards?.[scope] || [];
  const top3 = board.slice(0, 3);
  const rest = board.slice(3, 30);

  // Same normaliser the main Clasificación page uses (src/lib/leaderboardPrizes.js):
  // safe amounts, a card only when it actually has a name, `image` always dropped.
  // monthly_prizes arrives as a plain [1st,2nd,3rd] array from the backend, so it's
  // reshaped into the {"1":amount,...} object prizeCards expects.
  const prizeByRank = {};
  prizeCards(
    { 1: monthlyPrizes?.[0], 2: monthlyPrizes?.[1], 3: monthlyPrizes?.[2] },
    prizeSkins
  ).forEach((c) => {
    prizeByRank[c.rank] = { ...c, rarity: prizeSkins?.[String(c.rank)]?.rarity || null };
  });

  return (
    <div className="space-y-6" data-testid="creator-leaderboard">
      {/* Header: title + time filter tabs */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-display font-black text-2xl sm:text-3xl tracking-tight">Leaderboard de Creators</h2>
        <div className="inline-flex rounded-full border border-white/[0.06] bg-black/30 p-1">
          {SCOPES.map((s) => {
            const active = scope === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setScope(s.key)}
                data-testid={`cp-lb-scope-${s.key}`}
                className={`inline-flex items-center rounded-full px-4 py-1.5 text-xs font-bold transition ${
                  active ? "bg-white text-black" : "text-white/60 hover:text-white"
                }`}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Top 3 podium cards (center highlighted) */}
      {top3.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5">
          {/* Order: 2, 1, 3 to visually center the champion */}
          {top3[1] && <TopCard entry={top3[1]} rank={2} highlight={false} prize={prizeByRank[2]} />}
          {top3[0] && <TopCard entry={top3[0]} rank={1} highlight={true} prize={prizeByRank[1]} />}
          {top3[2] && <TopCard entry={top3[2]} rank={3} highlight={false} prize={prizeByRank[3]} />}
        </div>
      )}

      {/* Table */}
      <div className="relative overflow-hidden rounded-2xl"
        style={{ background: CARD_BG, border: `1px solid ${BORDER_SOFT}` }}>
        {/* Column headers */}
        <div className="grid grid-cols-[80px_minmax(180px,1.5fr)_1fr_1fr_1fr_1fr] items-center gap-4 px-6 py-3 border-b border-white/[0.06]">
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40">RANK</div>
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40">CREATOR</div>
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40">REFERIDOS</div>
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40">TASA MENSUAL</div>
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40">GANADO</div>
          <div className="text-[10px] font-black tracking-[0.3em] text-white/40 text-right">CÓDIGO</div>
        </div>
        <div className="max-h-[560px] overflow-y-auto">
          <AnimatePresence>
            {rest.length === 0 ? (
              <div className="px-6 py-14 text-center text-xs text-white/40">No hay más creators en este scope.</div>
            ) : (
              rest.map((entry, i) => (
                <Row key={entry.user_id} entry={entry} isMe={entry.user_id === currentUserId} scope={scope} isLast={i === rest.length - 1} />
              ))
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
