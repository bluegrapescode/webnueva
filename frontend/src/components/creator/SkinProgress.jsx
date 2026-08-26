import React, { useEffect, useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { Crown, Sparkles } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { GlitchProx } from "@/components/common/GlitchProx";
import { RarityBadge } from "@/components/common/RarityBadge";

/**
 * Skin unlock progress — navy/purple palette matching the new design.
 *
 * The exclusive is a real catalog glitch design: NAME + COLOUR PROXIMITY,
 * never a picture (fleet order 2026-08-11) — `settings.skin.card` carries
 * that shape ({glitch_id, name, subtitle, accent_hex, proximity, rarity}),
 * rendered here through the same GlitchProx face the leaderboard prize cards
 * use, instead of the old skin.image_url render.
 */
export function SkinProgress({ progress, settings }) {
  const target    = progress?.target ?? 100;
  const current   = Math.min(progress?.current ?? 0, target);
  const remaining = progress?.remaining ?? Math.max(0, target - current);
  const unlocked  = progress?.unlocked || current >= target;
  const pct       = Math.min(100, (current / Math.max(1, target)) * 100);
  const skin      = settings?.skin || {};
  const card      = progress?.card || skin?.card || null;
  const { play } = useSound();
  const wasUnlockedRef = useRef(unlocked);

  useEffect(() => {
    if (!wasUnlockedRef.current && unlocked) {
      play("skinUnlocked");
      wasUnlockedRef.current = true;
    }
  }, [unlocked, play]);

  const width = useMotionValue(0);
  const springWidth = useSpring(width, { stiffness: 90, damping: 22 });
  useEffect(() => { width.set(pct); }, [pct, width]);
  const widthStr = useTransform(springWidth, (v) => `${v}%`);

  return (
    <div className="relative overflow-hidden rounded-3xl" data-testid="creator-skin-progress"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)", border: "1px solid rgba(139,92,246,0.25)" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400 to-transparent" />
      <div className="pointer-events-none absolute -top-20 left-1/4 h-60 w-60 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(139,92,246,0.6), transparent 65%)" }} />

      <div className="relative p-6 sm:p-8 grid gap-6 md:grid-cols-[auto_1fr_auto] md:items-center">
        <div className="relative mx-auto md:mx-0">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
            className="absolute inset-[-6px] rounded-2xl pointer-events-none"
            style={{
              background: "conic-gradient(from 0deg, transparent 0%, rgba(167,139,250,0.6) 20%, transparent 40%, transparent 60%, rgba(236,72,153,0.4) 80%, transparent 100%)",
              maskImage: "linear-gradient(#000,#000) content-box, linear-gradient(#000,#000)",
              WebkitMaskImage: "linear-gradient(#000,#000) content-box, linear-gradient(#000,#000)",
              WebkitMaskComposite: "xor", maskComposite: "exclude",
              padding: "1px",
            }}
          />
          <div className="relative flex h-24 w-24 sm:h-28 sm:w-28 items-center justify-center rounded-2xl border overflow-hidden"
            style={{ borderColor: "rgba(167,139,250,0.5)", background: "linear-gradient(135deg, rgba(139,92,246,0.2), rgba(0,0,0,0.7))" }}>
            {card?.proximity?.length ? (
              <GlitchProx proximity={card.proximity} accent={card.accent_hex} compact />
            ) : (
              <Crown size={36} className="text-purple-400" fill="#A78BFA" />
            )}
            {unlocked && (
              <motion.div initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }}
                className="absolute inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                <Sparkles className="text-purple-400 drop-shadow-[0_0_10px_rgba(167,139,250,0.9)]" size={28} />
              </motion.div>
            )}
          </div>
        </div>

        <div className="min-w-0 text-center md:text-left">
          <div className="text-[10px] font-black tracking-[0.35em] text-purple-400">SKIN EXCLUSIVA</div>
          <div className="mt-1 text-2xl sm:text-3xl font-black tracking-tight leading-tight text-white">
            {skin.name || card?.name || "Skin Legendaria de Creator"}
          </div>
          <p className="mt-2 text-xs sm:text-sm text-white/50 max-w-md mx-auto md:mx-0">
            {skin.description || "Desbloqueá una skin exclusiva permanente alcanzando 100 referidos validados."}
          </p>
          {card?.rarity && (
            <div className="mt-2 flex justify-center md:justify-start">
              <RarityBadge rarity={card.rarity} />
            </div>
          )}
        </div>

        <div className="text-center md:text-right shrink-0">
          <div className="text-[9px] font-black tracking-[0.35em] text-purple-400">PROGRESO</div>
          <div className="mt-1 font-black tabular-nums leading-none">
            <span className="text-5xl sm:text-6xl text-white">{current}</span>
            <span className="text-white/30 text-2xl"> / {target}</span>
          </div>
          <div className="mt-1.5 text-[10px] font-mono tracking-wider text-white/40">{pct.toFixed(1).replace(/\.0$/, "")}%</div>
        </div>
      </div>

      <div className="relative mx-6 sm:mx-8 h-1.5 rounded-full overflow-hidden border border-white/[0.06]" style={{ background: "rgba(0,0,0,0.5)" }}>
        <motion.div className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: widthStr,
                   background: "linear-gradient(90deg, #8B5CF6 0%, #A78BFA 50%, #EC4899 100%)",
                   boxShadow: "0 0 14px rgba(139,92,246,0.7)" }}
        />
        <motion.div className="absolute inset-0 pointer-events-none"
          animate={{ backgroundPositionX: ["-100%", "220%"] }}
          transition={{ duration: 3.5, repeat: Infinity, ease: "linear" }}
          style={{
            backgroundImage: "linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.32) 50%, transparent 70%)",
            backgroundSize: "50% 100%", backgroundRepeat: "no-repeat",
          }}
        />
      </div>

      <div className="relative p-6 sm:px-8 sm:pb-8 sm:pt-4 flex items-center justify-between gap-3 flex-wrap">
        {unlocked ? (
          <motion.div initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 18 }}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-black tracking-widest text-white"
            style={{ background: "#8B5CF6" }}>
            <Sparkles size={12} /> ✓ SKIN DESBLOQUEADA
          </motion.div>
        ) : (
          <div className="text-xs sm:text-sm text-white/70">
            <span className="text-purple-400 font-black">🔥 {remaining}</span> referidos validados más para desbloquear tu skin exclusiva.
          </div>
        )}
      </div>
    </div>
  );
}
