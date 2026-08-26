import React, { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Gift, X, Check, Star, Lock, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { MEDIA } from "@/lib/media";
import { HudCorners, HudGrid } from "@/components/common/Hud";

const fmt = (n) => Number(n || 0).toLocaleString();

// Reward chips for a schedule row.
function RewardChips({ d }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      {d.coins > 0 && (
        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400 tabular-nums">
          <img src={MEDIA.coinNormal} alt="PrimeMeat" className="w-3.5 h-3.5 object-contain" />{fmt(d.coins)}
        </span>
      )}
      {d.vip > 0 && (
        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-gold tabular-nums">
          <img src={MEDIA.coinVip} alt="Amberium" className="w-3.5 h-3.5 object-contain" />{fmt(d.vip)}
        </span>
      )}
      <span className="inline-flex items-center gap-0.5 text-[11px] font-bold text-sky-400 tabular-nums">
        <Star size={11} className="fill-sky-400/40" />{d.xp}
      </span>
      {d.special && (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-fuchsia-400 uppercase tracking-wide">
          <Sparkles size={11} />{d.special}
        </span>
      )}
    </div>
  );
}

export function LoginGift() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState(null);
  const [claiming, setClaiming] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.giftStatus();
      setStatus(data);
    } catch { /* ignore transient errors */ }
  }, []);

  useEffect(() => {
    if (!user) return;
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [user?.id, load]);

  if (!user) return null;
  const canClaim = status?.can_claim;

  const claim = async () => {
    if (claiming) return;
    setClaiming(true);
    try {
      const { data } = await api.giftClaim();
      play?.("purchase");
      const parts = [];
      if (data.reward.coins) parts.push(`+${fmt(data.reward.coins)} PrimeMeat`);
      if (data.reward.vip) parts.push(`+${fmt(data.reward.vip)} Amberium`);
      parts.push(`+${data.reward.xp} XP`);
      if (data.reward.special) parts.push(data.reward.special.label);
      toast.success(`¡Día ${data.day} reclamado!`, { description: parts.join(" · ") });
      await Promise.all([load(), refresh?.()]);
    } catch (e) {
      play?.("error");
      toast.error(e?.response?.data?.detail || "No se pudo reclamar el regalo.");
      load();
    } finally {
      setClaiming(false);
    }
  };

  const schedule = status?.schedule || [];
  const streak = status?.streak || 0;
  const nextDay = status?.next_day || 1;

  return (
    <>
      {/* Trigger — sits to the LEFT of the PrimeMeat pill */}
      <button
        type="button"
        onClick={() => { play?.("click"); setOpen(true); }}
        data-testid="login-gift-button"
        title="Regalo de inicio de sesión"
        className="relative flex items-center justify-center w-9 h-9 border border-gold/30 bg-gold/[0.06] hover:bg-gold/[0.12] transition-colors"
        style={{ borderRadius: 2 }}
      >
        <Gift size={17} className="text-gold" />
        {canClaim && (
          <span className="absolute -top-1 -right-1 flex" data-testid="login-gift-badge">
            <span className="animate-ping absolute inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" style={{ boxShadow: "0 0 6px #34D399" }} />
          </span>
        )}
      </button>

      {createPortal(
        <AnimatePresence>
          {open && status && (
            <motion.div className="fixed inset-0 z-[80] flex items-center justify-center p-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="login-gift-modal">
              <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => { setOpen(false); play?.("close"); }} />
              <motion.div initial={{ opacity: 0, scale: 0.94, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.94, y: 20 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className="relative w-full max-w-2xl overflow-hidden border border-gold/25"
                style={{ borderRadius: 2, background: "linear-gradient(160deg, #14110a, #0a0806)" }}>
                <HudGrid color="rgba(124, 168, 66,0.05)" />
                <HudCorners color="rgba(124, 168, 66,0.6)" />
                <button onClick={() => { setOpen(false); play?.("close"); }} data-testid="login-gift-close"
                  className="absolute top-4 right-4 z-10 p-2 hover:bg-white/10 transition-colors" style={{ borderRadius: 2 }}><X size={18} /></button>

                <div className="relative p-6 sm:p-7">
                  {/* Header — terminal style */}
                  <p className="label-overline text-[10px] text-gold mb-1 tracking-[0.2em]">// RECOMPENSAS DIARIAS</p>
                  <h3 className="font-display font-extrabold text-2xl sm:text-3xl leading-none flex items-center gap-2">
                    <Gift size={24} className="text-gold" /> Regalo de Login
                  </h3>
                  <p className="text-sm text-muted-foreground mt-2">
                    Conéctate <span className="text-gold font-semibold">7 días seguidos</span> para recompensas crecientes.
                    Racha actual: <span className="text-emerald-400 font-bold" data-testid="gift-streak">{streak}/7</span>
                  </p>

                  {/* 7-day grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-5" data-testid="gift-grid">
                    {schedule.map((d) => {
                      const claimed = d.day <= streak;
                      const isNext = d.day === nextDay && canClaim;
                      const locked = d.day > nextDay || (d.day === nextDay && !canClaim && !claimed);
                      return (
                        <div key={d.day} data-testid={`gift-day-${d.day}`}
                          className="relative flex flex-col items-center gap-2 p-3 border transition-all"
                          style={{
                            borderRadius: 2,
                            borderColor: isNext ? "#34D399" : claimed ? "rgba(124, 168, 66,0.4)" : "rgba(255,255,255,0.08)",
                            background: isNext ? "rgba(52,211,153,0.08)" : claimed ? "rgba(124, 168, 66,0.05)" : "rgba(255,255,255,0.02)",
                            boxShadow: isNext ? "0 0 16px rgba(52,211,153,0.25)" : "none",
                          }}>
                          {isNext && <HudCorners color="rgba(52,211,153,0.8)" size={10} />}
                          <div className="flex items-center justify-between w-full">
                            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: d.day === 7 ? "#e879f9" : isNext ? "#34D399" : "#8a8a8a" }}>
                              Día {d.day}
                            </span>
                            {claimed && <Check size={13} className="text-gold" />}
                            {locked && <Lock size={11} className="text-muted-foreground/60" />}
                          </div>
                          <RewardChips d={d} />
                        </div>
                      );
                    })}
                  </div>

                  {/* Claim */}
                  <div className="flex items-center justify-between border-t border-white/10 pt-4 mt-6">
                    <div className="flex items-center gap-1.5 text-sm">
                      <Star size={15} className="text-sky-400 fill-sky-400/40" />
                      <span className="text-muted-foreground">XP total:</span>
                      <span className="font-display font-bold text-sky-400 tabular-nums" data-testid="gift-total-xp">{fmt(user.xp)}</span>
                    </div>
                    <button onClick={claim} disabled={!canClaim || claiming} data-testid="gift-claim-button"
                      className="inline-flex items-center justify-center gap-2 font-display font-bold px-7 py-3 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      style={{ borderRadius: 2, background: canClaim ? "linear-gradient(180deg,#7CA842,#b8860b)" : "rgba(255,255,255,0.06)", color: canClaim ? "#120e04" : "#8a8a8a" }}>
                      {claiming ? "Reclamando…" : canClaim ? <><Gift size={16} /> Reclamar Día {nextDay}</> : <><Check size={16} /> Reclamado hoy</>}
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
