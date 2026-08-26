import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Timer, Crown, Gift, Swords, Target, Clock3, Loader2 } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { HudCorners } from "@/components/common/Hud";
import { GOLD, fmtNum } from "@/components/battlepass/RewardCard";

const TIER_CHIP = {
  free: { label: "SIN PASE", color: "#9CA3AF" },
  regular: { label: "REGULAR", color: "#7CA842" },
  premium_plus: { label: "PREMIUM+", color: GOLD },
};

const SOURCE_NOTE = {
  gift: "regalado por el staff",
  gifted: "regalado por el staff",
  purchase: null,
  stripe: null,
};

// The season end is an absolute instant from the server, so the remaining time
// is derived from it on every tick — a counter that only decrements drifts.
export function msLeft(endsAt) {
  if (!endsAt) return null;
  const t = new Date(endsAt).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, t - Date.now());
}

export function fmtLeft(ms) {
  if (ms == null) return "—";
  if (ms <= 0) return "TEMPORADA TERMINADA";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  return `${h}h ${m}m ${sec}s`;
}

function XpChip({ icon: Icon, title, detail, testid }) {
  return (
    <div
      className="inline-flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2"
      data-testid={testid}
    >
      <Icon size={14} className="shrink-0 text-gold" />
      <span className="label-overline text-[9px] text-foreground/85">{title}</span>
      <span className="text-[11px] font-semibold text-muted-foreground">{detail}</span>
    </div>
  );
}

export function SeasonHeader({ season, level, xp, tier, tierSource, claimableCount, claimingAll, onClaimAll, onOpenPurchase }) {
  const { play } = useSound();
  const [left, setLeft] = useState(() => msLeft(season?.ends_at));

  useEffect(() => {
    setLeft(msLeft(season?.ends_at));
    const t = setInterval(() => setLeft(msLeft(season?.ends_at)), 1000);
    return () => clearInterval(t);
  }, [season?.ends_at]);

  const chip = TIER_CHIP[tier] || TIER_CHIP.free;
  const note = SOURCE_NOTE[tierSource] || null;
  const maxLevel = xp?.max_level || 100;
  const atMax = level >= maxLevel;
  const pct = atMax ? 100 : Math.max(0, Math.min(100, Number(xp?.percent || 0)));
  const inLevel = Number(xp?.xp_in_level || 0);
  const span = Number(xp?.xp_span || 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="relative overflow-hidden rounded-2xl border p-5 sm:p-7"
      style={{ borderColor: `${GOLD}33`, background: "#0b0b0e", boxShadow: `0 0 45px ${GOLD}12` }}
      data-testid="bp-season-header"
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: `radial-gradient(120% 100% at 100% 0%, ${GOLD}12, transparent 55%)` }}
      />
      <HudCorners color={`${GOLD}88`} />

      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="label-overline text-[10px]" style={{ color: GOLD }}>
            Temporada · {maxLevel} niveles
          </p>
          <h2
            className="mt-1 truncate font-display text-2xl font-extrabold tracking-tight sm:text-4xl"
            data-testid="bp-season-name"
          >
            {season?.name || "Pase de Batalla"}
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Sube de nivel jugando y reclama las recompensas de las dos filas. El pase se reinicia el 1º de cada mes.
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2.5">
          <span
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 font-mono text-xs font-bold"
            style={{ color: GOLD, borderColor: `${GOLD}44`, background: `${GOLD}0f` }}
            data-testid="bp-countdown"
          >
            <Timer size={13} /> TERMINA EN {fmtLeft(left)}
          </span>

          <span
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2"
            data-testid="bp-current-level"
          >
            <span className="label-overline text-[9px] text-muted-foreground">Tu nivel</span>
            <span className="font-mono text-lg font-extrabold leading-none" style={{ color: GOLD }}>{level}</span>
          </span>

          <span
            className="inline-flex flex-col items-center rounded-lg border px-3 py-1.5"
            style={{ color: chip.color, borderColor: `${chip.color}55`, background: `${chip.color}12` }}
            data-testid={`bp-tier-chip-${tier}`}
          >
            <span className="label-overline text-[10px] leading-tight">{chip.label}</span>
            {note && <span className="text-[9px] font-semibold text-muted-foreground">{note}</span>}
          </span>
        </div>
      </div>

      {/* XP bar */}
      <div className="relative mt-6">
        <div className="mb-1.5 flex items-end justify-between gap-3">
          <span className="label-overline text-[10px] text-foreground/85">Nivel {level}</span>
          <span className="font-mono text-xs font-bold" style={{ color: GOLD }} data-testid="bp-xp-readout">
            {atMax ? "NIVEL MÁXIMO" : `${fmtNum(inLevel)} / ${fmtNum(span)} XP`}
          </span>
        </div>
        <div className="relative h-3 w-full overflow-hidden rounded-full bg-white/[0.06]" data-testid="bp-xp-bar">
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ background: `linear-gradient(90deg, #b98a06, ${GOLD})`, boxShadow: `0 0 12px ${GOLD}88` }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
      </div>

      {/* how XP is earned */}
      <div className="relative mt-4 flex flex-wrap gap-2" data-testid="bp-xp-sources">
        <XpChip icon={Clock3} title="Tiempo en juego" detail="+60 XP / 4 min" testid="bp-xp-source-playtime" />
        <XpChip icon={Target} title="Misiones" detail="120–2.000 XP (por rareza)" testid="bp-xp-source-quests" />
        <XpChip icon={Swords} title="Bajas" detail="80–500 XP" testid="bp-xp-source-kills" />
      </div>

      {/* actions */}
      <div className="relative mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => { play("click"); onClaimAll(); }}
          disabled={claimingAll || !claimableCount}
          data-testid="bp-claim-all"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-gold px-5 py-2.5 text-sm font-bold text-background transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {claimingAll ? <Loader2 size={16} className="animate-spin" /> : <Gift size={16} />}
          Reclamar todas{claimableCount ? ` (${claimableCount})` : ""}
        </button>

        {tier !== "premium_plus" && (
          <button
            type="button"
            onClick={() => { play("open"); onOpenPurchase(); }}
            data-testid="bp-open-purchase"
            className="inline-flex items-center justify-center gap-2 rounded-lg border px-5 py-2.5 text-sm font-bold transition-all hover:brightness-110"
            style={{ color: GOLD, borderColor: `${GOLD}88`, background: `${GOLD}12` }}
          >
            <Crown size={16} />
            {tier === "regular" ? "Mejorar a Premium+" : "Desbloquear el pase"}
          </button>
        )}
      </div>
    </motion.div>
  );
}

export default SeasonHeader;
