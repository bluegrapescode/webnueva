import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Package, Wifi, WifiOff, Clock, Trophy, Sparkles, Gift, ShieldAlert } from "lucide-react";
import { useAirdrop } from "@/context/AirdropContext";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const RARITY = {
  common:    { es: "COMÚN",      ring: "#9ca3af", glow: "rgba(156,163,175,.55)", chute: "#e2e8f0", text: "text-gray-300" },
  rare:      { es: "RARO",       ring: "#3b82f6", glow: "rgba(59,130,246,.6)",   chute: "#93c5fd", text: "text-blue-300" },
  epic:      { es: "ÉPICO",      ring: "#a855f7", glow: "rgba(168,85,247,.62)",  chute: "#d8b4fe", text: "text-purple-300" },
  legendary: { es: "LEGENDARIO", ring: "#f59e0b", glow: "rgba(245,158,11,.68)",  chute: "#fcd34d", text: "text-amber-300" },
};
const pal = (r) => RARITY[r] || RARITY.common;

// Iconos por clave de material (el backend manda 🦴 para todos; aquí los
// diferenciamos visualmente sin tocar la entrega ya verificada del servidor).
const MAT_ICON = { bones: "🦴", metal: "⚙️", leather: "🟫", polymer: "🧪" };
const rewardIcon = (rw) => (rw.type === "material" && MAT_ICON[rw.key]) || rw.icon || "🎁";

const ms = (iso) => (iso ? new Date(iso).getTime() : 0);
function fmt(msLeft) {
  if (msLeft < 0) msLeft = 0;
  const s = Math.floor(msLeft / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${m}:${String(ss).padStart(2, "0")}`;
}

// Fuerza re-render fluido (~rAF) mientras la escena está montada.
function useTick() {
  const [, set] = useState(0);
  useEffect(() => {
    let raf;
    const loop = () => { set((n) => (n + 1) % 1e9); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
}

// ── Paracaídas + caja (SVG) con balanceo por viento ──
function ParachuteCrate({ color, chute, size = 118 }) {
  return (
    <motion.div
      style={{ width: size, transformOrigin: "50% 0%" }}
      animate={{ rotate: [-7, 7, -7] }}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
      data-testid="airdrop-parachute"
    >
      <svg viewBox="0 0 120 150" width={size} height={size * 1.25} style={{ filter: `drop-shadow(0 8px 24px ${color})` }}>
        <path d="M6 46 A54 54 0 0 1 114 46 Z" fill={chute} opacity="0.96" />
        <path d="M6 46 A54 54 0 0 1 114 46" fill="none" stroke="rgba(0,0,0,.28)" strokeWidth="1.4" />
        {[24, 48, 72, 96].map((x) => <path key={x} d={`M${x} 46 Q60 44 60 46`} stroke="rgba(0,0,0,.22)" strokeWidth="1" fill="none" />)}
        {[14, 42, 78, 106].map((x, i) => <line key={i} x1={x} y1="47" x2="60" y2="92" stroke="rgba(255,255,255,.5)" strokeWidth="1" />)}
        <g>
          <rect x="40" y="90" width="40" height="38" rx="4" fill="#3a2a1c" stroke={color} strokeWidth="2.5" />
          <rect x="40" y="103" width="40" height="6" fill={color} opacity="0.85" />
          <rect x="56" y="90" width="8" height="38" fill={color} opacity="0.55" />
          <circle cx="60" cy="109" r="4" fill={color} />
        </g>
      </svg>
    </motion.div>
  );
}

// ── Caja aterrizada, latiendo, lista para reclamar ──
function GroundCrate({ color, glow, opened = false }) {
  return (
    <motion.div
      className="relative"
      animate={opened ? {} : { y: [0, -6, 0], scale: [1, 1.03, 1] }}
      transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
      data-testid="airdrop-crate"
    >
      <div className="absolute inset-0 rounded-2xl blur-2xl" style={{ background: glow, transform: "scale(1.6)" }} />
      <svg viewBox="0 0 120 110" width={150} height={138} className="relative" style={{ filter: `drop-shadow(0 10px 30px ${glow})` }}>
        <rect x="18" y="34" width="84" height="66" rx="6" fill="#3a2a1c" stroke={color} strokeWidth="3" />
        <rect x="18" y="52" width="84" height="10" fill={color} opacity="0.85" />
        <rect x="54" y="34" width="12" height="66" fill={color} opacity="0.5" />
        <motion.rect
          x="18" y="34" width="84" height="16" rx="6" fill={color} opacity="0.95"
          animate={opened ? { y: 8, rotate: -18, opacity: 0.5 } : {}}
          style={{ transformOrigin: "18px 34px" }}
        />
        <circle cx="60" cy="70" r="7" fill={color} />
        <text x="60" y="75" textAnchor="middle" fontSize="10" fontWeight="900" fill="#1a1207">✦</text>
      </svg>
    </motion.div>
  );
}

// ── Tarjeta de recompensa (boca abajo → clic → revela) ──
function RewardCard({ reward, index, revealed, onReveal, color }) {
  const isSpecial = reward.special || reward.key === "resurrection_token";
  return (
    <button
      type="button"
      onClick={() => !revealed && onReveal(index)}
      data-testid={`airdrop-reward-card-${index}`}
      className="relative aspect-[3/4] rounded-xl overflow-hidden select-none focus:outline-none"
      style={{ perspective: 900 }}
    >
      <motion.div
        className="relative w-full h-full"
        style={{ transformStyle: "preserve-3d" }}
        initial={false}
        animate={{ rotateY: revealed ? 180 : 0 }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Dorso */}
        <div
          className="absolute inset-0 rounded-xl flex items-center justify-center glass"
          style={{ backfaceVisibility: "hidden", border: `1px solid ${color}55` }}
        >
          <motion.div animate={{ scale: [1, 1.08, 1] }} transition={{ duration: 1.4, repeat: Infinity }}>
            <Gift size={30} style={{ color }} />
          </motion.div>
        </div>
        {/* Frente */}
        <div
          className="absolute inset-0 rounded-xl flex flex-col items-center justify-center gap-1 p-2 text-center"
          style={{
            backfaceVisibility: "hidden", transform: "rotateY(180deg)",
            background: isSpecial
              ? "linear-gradient(160deg, rgba(245,158,11,.22), rgba(0,0,0,.5))"
              : "linear-gradient(160deg, rgba(255,255,255,.06), rgba(0,0,0,.45))",
            border: `1px solid ${isSpecial ? "#f59e0b" : color}${isSpecial ? "" : "66"}`,
            boxShadow: isSpecial ? "0 0 26px rgba(245,158,11,.5)" : "none",
          }}
        >
          <span className="text-3xl leading-none">{rewardIcon(reward)}</span>
          <span className="font-bold text-[11px] leading-tight">{reward.name}</span>
          <span className="font-display font-extrabold text-lg" style={{ color: isSpecial ? "#fcd34d" : color }}>
            ×{Number(reward.qty || 1).toLocaleString()}
          </span>
        </div>
      </motion.div>
    </button>
  );
}

export default function AirdropArena() {
  const { state, connected, serverNow, claim } = useAirdrop();
  const { user } = useAuth();
  const { play } = useSound();
  useTick();

  const [claiming, setClaiming] = useState(false);
  const [claimResult, setClaimResult] = useState(null);
  const [revealed, setRevealed] = useState(new Set());
  const lastAirdropId = useRef(null);

  // Reinicia el estado local cuando empieza un nuevo airdrop.
  useEffect(() => {
    if (state?.id && state.id !== lastAirdropId.current) {
      lastAirdropId.current = state.id;
      setClaimResult(null);
      setClaiming(false);
      setRevealed(new Set());
    }
  }, [state?.id]);

  const st = state?.state;
  const p = pal(state?.rarity);
  const now = serverNow();

  const myRewards = claimResult?.rewards || state?.my_rewards || null;
  const iAmWinner = !!myRewards || (claimResult?.winner === true);

  const doClaim = useCallback(async () => {
    if (claiming) return;
    setClaiming(true);
    try {
      const r = await claim();
      setClaimResult(r);
      play("airdropClaimed");
    } catch (e) {
      const detail = e?.response?.data?.detail || "No se pudo reclamar el Airdrop.";
      toast.error(detail, { icon: <ShieldAlert className="w-4 h-4 text-[#ff6b74]" /> });
    } finally {
      setClaiming(false);
    }
  }, [claiming, claim, play]);

  const onReveal = useCallback((idx) => {
    setRevealed((prev) => {
      if (prev.has(idx)) return prev;
      const next = new Set(prev);
      next.add(idx);
      const rw = myRewards?.[idx];
      const special = rw && (rw.special || rw.key === "resurrection_token") || state?.rarity === "legendary";
      play(special ? "airdropLegendary" : "airdropAvailable");
      return next;
    });
  }, [myRewards, state?.rarity, play]);

  const revealAll = useCallback(() => {
    if (!myRewards) return;
    myRewards.forEach((_, i) => setTimeout(() => onReveal(i), i * 260));
  }, [myRewards, onReveal]);

  // ── Cálculos de fase/countdown (todo relativo al reloj del servidor) ──
  const dropAt = ms(state?.drop_at), landAt = ms(state?.land_at), expireAt = ms(state?.expire_at);
  const nextAt = ms(state?.next_at), cooldownUntil = ms(state?.cooldown_until);
  const fallProgress = landAt > dropAt ? Math.min(1, Math.max(0, (now - dropAt) / (landAt - dropAt))) : 0;

  return (
    <div className="relative" data-testid="airdrop-arena">
      <style>{`
        @keyframes ad-cloud { from { transform: translateX(-12%); } to { transform: translateX(112%); } }
        @keyframes ad-beam { 0%,100% { transform: rotate(-16deg); opacity:.25 } 50% { transform: rotate(16deg); opacity:.55 } }
        @keyframes ad-pulse { 0%,100% { opacity:.35 } 50% { opacity:.9 } }
      `}</style>

      {/* Cabecera */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: `${p.ring}22` }}>
            <Package size={22} style={{ color: p.ring }} />
          </div>
          <div>
            <p className="label-overline text-[10px]" style={{ color: p.ring }}>Evento Global · La Isla Nublar</p>
            <h2 className="font-display font-extrabold text-2xl tracking-tight leading-none">Airdrop Global</h2>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {state?.rarity && (
            <span className="px-3 py-1.5 rounded-full text-[11px] font-extrabold tracking-wider"
              style={{ background: `${p.ring}1f`, color: p.ring, border: `1px solid ${p.ring}55` }}
              data-testid="airdrop-rarity">
              {p.es}
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="airdrop-conn">
            {connected ? <Wifi size={13} className="text-emerald-400" /> : <WifiOff size={13} className="text-crimson" />}
            {connected ? "En vivo" : "Reconectando"}
          </span>
        </div>
      </div>

      {/* Escena */}
      <div className="relative rounded-3xl overflow-hidden border border-white/10"
        style={{ height: 440, background: "linear-gradient(180deg,#0a1220 0%,#0d1a2b 40%,#10241a 100%)" }}
        data-testid="airdrop-scene">
        {/* Estrellas */}
        <div className="absolute inset-0" style={{ backgroundImage: "radial-gradient(1px 1px at 20% 20%, #fff6, transparent), radial-gradient(1px 1px at 70% 30%, #fff4, transparent), radial-gradient(1px 1px at 40% 60%, #fff3, transparent), radial-gradient(1px 1px at 85% 15%, #fff5, transparent)" }} />
        {/* Nubes */}
        {[["18%", 60, 26, 0.10], ["45%", 40, 34, 0.08], ["12%", 90, 20, 0.06]].map(([top, w, dur, op], i) => (
          <div key={i} className="absolute rounded-full bg-white blur-2xl" style={{ top, width: `${w}%`, height: 60, opacity: op, animation: `ad-cloud ${dur}s linear ${i * -8}s infinite` }} />
        ))}
        {/* Suelo (jungla) */}
        <div className="absolute bottom-0 left-0 right-0 h-24" style={{ background: "linear-gradient(180deg, transparent, #0c1f12 70%)" }} />
        <div className="absolute bottom-0 left-0 right-0 h-2" style={{ background: p.ring, opacity: 0.4, filter: "blur(2px)" }} />

        {/* Reflectores de alerta */}
        {(st === "incoming" || st === "falling") && (
          <>
            <div className="absolute -top-10 left-[22%] w-40 h-[420px] origin-top" style={{ background: `linear-gradient(${p.glow}, transparent)`, animation: "ad-beam 4s ease-in-out infinite", clipPath: "polygon(45% 0, 55% 0, 100% 100%, 0 100%)" }} />
            <div className="absolute -top-10 right-[22%] w-40 h-[420px] origin-top" style={{ background: `linear-gradient(${p.glow}, transparent)`, animation: "ad-beam 4s ease-in-out .8s infinite", clipPath: "polygon(45% 0, 55% 0, 100% 100%, 0 100%)" }} />
          </>
        )}

        {/* Contenido central por fase */}
        <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
          <AnimatePresence mode="wait">
            {/* WAITING */}
            {st === "waiting" && (
              <motion.div key="waiting" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center">
                <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity }}>
                  <Package size={54} className="text-muted-foreground/70 mb-3" />
                </motion.div>
                <p className="label-overline text-[11px] text-muted-foreground mb-1">Próximo suministro global en</p>
                <p className="font-display font-black text-5xl sm:text-6xl tabular-nums tracking-tight" style={{ color: p.ring }} data-testid="airdrop-countdown">
                  {fmt(dropAt - now)}
                </p>
                <p className="text-sm text-muted-foreground mt-3 max-w-xs">Cae para <b>todos a la vez</b>. Solo un superviviente podrá reclamarlo.</p>
              </motion.div>
            )}

            {/* INCOMING */}
            {st === "incoming" && (
              <motion.div key="incoming" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center">
                <motion.p animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1, repeat: Infinity }}
                  className="font-display font-black text-2xl sm:text-3xl mb-2 tracking-widest" style={{ color: p.ring }}>
                  ⚠ SUMINISTRO ENTRANTE
                </motion.p>
                <p className="font-display font-black text-6xl tabular-nums" style={{ color: p.ring, textShadow: `0 0 30px ${p.glow}` }} data-testid="airdrop-countdown">
                  {fmt(dropAt - now)}
                </p>
                <p className="text-sm text-muted-foreground mt-3">Prepárate... está a punto de caer.</p>
              </motion.div>
            )}

            {/* FALLING */}
            {st === "falling" && (
              <motion.div key="falling" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0">
                <div className="absolute left-1/2 -translate-x-1/2" style={{ top: `${8 + fallProgress * 62}%`, transition: "top 80ms linear" }}>
                  <ParachuteCrate color={p.ring} chute={p.chute} />
                </div>
                <motion.p animate={{ opacity: [0.5, 1, 0.5] }} transition={{ duration: 1.2, repeat: Infinity }}
                  className="absolute bottom-6 left-0 right-0 font-display font-bold text-lg" style={{ color: p.ring }}>
                  🪂 Cayendo sobre la isla...
                </motion.p>
              </motion.div>
            )}

            {/* AVAILABLE */}
            {st === "available" && (
              <motion.div key="available" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center">
                <GroundCrate color={p.ring} glow={p.glow} opened={iAmWinner} />
                {iAmWinner ? (
                  <p className="font-display font-bold text-lg mt-3" style={{ color: p.ring }}>¡Es tuyo! Abre tus recompensas abajo 👇</p>
                ) : (
                  <>
                    <p className="label-overline text-[11px] text-muted-foreground mt-3 mb-1 inline-flex items-center gap-1.5">
                      <Clock size={12} /> Se cierra en {fmt(expireAt - now)}
                    </p>
                    <motion.button
                      onClick={doClaim} disabled={claiming}
                      data-testid="airdrop-claim-btn"
                      whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.96 }}
                      className="mt-1 px-10 py-4 rounded-2xl font-display font-black text-xl tracking-wide disabled:opacity-60"
                      style={{ background: p.ring, color: "#0a0a0a", boxShadow: `0 0 40px ${p.glow}`, animation: "ad-pulse 1.4s ease-in-out infinite" }}>
                      {claiming ? "RECLAMANDO..." : "RECLAMAR AIRDROP"}
                    </motion.button>
                    <p className="text-xs text-muted-foreground mt-2">Solo el primero se lo lleva. ¡Sé rápido!</p>
                  </>
                )}
              </motion.div>
            )}

            {/* CLAIMED */}
            {st === "claimed" && (
              <motion.div key="claimed" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center">
                {iAmWinner ? (
                  <>
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 200 }}>
                      <Trophy size={48} style={{ color: p.ring }} />
                    </motion.div>
                    <p className="font-display font-black text-2xl mt-2" style={{ color: p.ring }}>¡GANASTE EL AIRDROP {p.es}!</p>
                    <p className="text-sm text-muted-foreground mt-1">Toca cada carta para revelar tu botín.</p>
                  </>
                ) : (
                  <>
                    <GroundCrate color={p.ring} glow={p.glow} opened />
                    <div className="flex items-center gap-2 mt-3">
                      {state?.winner?.avatar && <img src={state.winner.avatar} alt="" className="w-8 h-8 rounded-full object-cover ring-2" style={{ ["--tw-ring-color"]: p.ring }} />}
                      <p className="font-bold text-lg">🏆 {state?.winner?.name || "Otro superviviente"} se lo llevó</p>
                    </div>
                    <p className="label-overline text-[11px] text-muted-foreground mt-2 inline-flex items-center gap-1.5">
                      <Clock size={12} /> Próximo airdrop en {fmt((nextAt || cooldownUntil) - now)}
                    </p>
                  </>
                )}
              </motion.div>
            )}

            {/* EXPIRED */}
            {st === "expired" && (
              <motion.div key="expired" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center">
                <Package size={48} className="text-muted-foreground/50 mb-2" />
                <p className="font-display font-bold text-xl text-muted-foreground">Nadie reclamó el suministro</p>
                <p className="label-overline text-[11px] text-muted-foreground mt-2 inline-flex items-center gap-1.5">
                  <Clock size={12} /> Próximo airdrop en {fmt((nextAt || cooldownUntil) - now)}
                </p>
              </motion.div>
            )}

            {/* DISABLED / sin datos */}
            {(st === "disabled" || !st) && (
              <motion.div key="disabled" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center">
                <Package size={48} className="text-muted-foreground/40 mb-2" />
                <p className="text-muted-foreground">{st === "disabled" ? "Los Airdrops están desactivados por ahora." : "Sincronizando evento global..."}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Panel de recompensas del ganador (carta por carta) */}
      <AnimatePresence>
        {iAmWinner && myRewards && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-5 glass rounded-2xl p-5" data-testid="airdrop-rewards-panel">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <p className="font-display font-bold text-lg inline-flex items-center gap-2">
                <Sparkles size={18} style={{ color: p.ring }} /> Tu botín {p.es}
              </p>
              <button onClick={revealAll} data-testid="airdrop-reveal-all"
                className="px-3 py-1.5 rounded-lg text-xs font-bold glass hover:text-foreground">
                Revelar todo
              </button>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
              {myRewards.map((rw, i) => (
                <RewardCard key={i} reward={rw} index={i} revealed={revealed.has(i)} onReveal={onReveal} color={p.ring} />
              ))}
            </div>
            {revealed.size === myRewards.length && (
              <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="text-center text-sm text-emerald-400 mt-4 font-medium">
                ✓ Recompensas añadidas a tu cuenta.
              </motion.p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Aviso de sesión Steam para reclamar */}
      {!user?.steam_id && st === "available" && !iAmWinner && (
        <p className="mt-4 text-center text-xs text-amber-400/90" data-testid="airdrop-steam-warn">
          Necesitas iniciar sesión con Steam para reclamar el Airdrop.
        </p>
      )}
    </div>
  );
}
