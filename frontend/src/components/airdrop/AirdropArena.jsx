import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Coins, Gem, Clock, Trophy, Sparkles, Gift, ShieldAlert, Package } from "lucide-react";
import { useAirdrop } from "@/context/AirdropContext";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { api } from "@/lib/api";

// Airdrop Global — misma temática que la Ruleta (Nublar Spin): fondo magenta
// neón con palmeras, título italic a dos tonos, HUDs glossy, tarima con brillo
// rosa, botón brillante y confeti. Aquí el protagonista es un COFRE que se abre,
// tintado por la rareza del suministro.
const PINK = "#EC4899", PINK_HI = "#FF3D9A", PINK_LO = "#BE185D";

const RARITY = {
  common:    { es: "COMÚN",      accent: "#9CA3AF", bg: "linear-gradient(180deg, #4B5563 0%, #1F2937 100%)", chute: "#e2e8f0" },
  rare:      { es: "RARO",       accent: "#3B82F6", bg: "linear-gradient(180deg, #1E40AF 0%, #0B1E4F 100%)", chute: "#93c5fd" },
  epic:      { es: "ÉPICO",      accent: "#A855F7", bg: "linear-gradient(180deg, #6D28D9 0%, #2E1065 100%)", chute: "#d8b4fe" },
  legendary: { es: "LEGENDARIO", accent: "#F59E0B", bg: "linear-gradient(180deg, #B45309 0%, #4A2803 100%)", chute: "#fcd34d" },
};
const pal = (r) => RARITY[r] || RARITY.common;
const glowOf = (r) => `${pal(r).accent}`;

const MAT_ICON = { bones: "🦴", metal: "⚙️", leather: "🟫", polymer: "🧪" };
const rewardIcon = (rw) => (rw.type === "material" && MAT_ICON[rw.key]) || rw.icon || "🎁";

// Imágenes reales que ya usa la web (mismas rutas que la Ruleta / crafteo).
// Los iconos de materiales llegan de la colección de crafteo (matImg, cargado
// desde /crafting/state) para respetar cualquier cambio del admin.
const COIN_TOKEN_IMG = {
  primemeat: "/coins/meat.png",
  amberium: "/coins/amber.png",
  growth_token: "/tokens/growth.png",
  diet_token: "/tokens/diet.png",
  resurrection_token: "/fossil.png",
};
function rewardImage(rw, matImg) {
  if (rw.type === "material") return (matImg && matImg[rw.key]) || null;
  return COIN_TOKEN_IMG[rw.key] || null;
}

const ms = (iso) => (iso ? new Date(iso).getTime() : 0);
function fmt(msLeft) {
  if (msLeft < 0) msLeft = 0;
  const s = Math.floor(msLeft / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${m}:${String(ss).padStart(2, "0")}`;
}

function prefersReducedMotion() {
  try { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (_) { return false; }
}

function useTick() {
  const [, set] = useState(0);
  useEffect(() => {
    let raf;
    const loop = () => { set((n) => (n + 1) % 1e9); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
}

// ─── Confeti (canvas, sin dependencias) — clonado del estilo de la Ruleta ───
function fireConfetti(canvas, big) {
  if (!canvas || prefersReducedMotion()) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width = canvas.offsetWidth || 800;
  const H = canvas.height = canvas.offsetHeight || 600;
  const colors = big ? ["#FF2489", "#EC4899", "#FFD54F", "#F59E0B", "#FFFFFF", "#84CC16"] : ["#EC4899", "#F472B6", "#A78BFA", "#C084FC"];
  const N = big ? 220 : 120;
  const parts = [];
  for (let i = 0; i < N; i++) {
    const fromLeft = i % 2 === 0;
    parts.push({
      x: fromLeft ? W * 0.12 : W * 0.88, y: H * 0.7,
      vx: (fromLeft ? 1 : -1) * (3 + Math.random() * 9), vy: -(9 + Math.random() * 11),
      g: 0.28 + Math.random() * 0.12, s: 4 + Math.random() * 6, r: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.3, c: colors[i % colors.length], life: 1,
      shape: i % 3 === 0 ? "circle" : "rect",
    });
  }
  const start = performance.now();
  const total = big ? 3200 : 1700;
  let raf = 0;
  const frame = (now) => {
    const t = now - start;
    ctx.clearRect(0, 0, W, H);
    if (big && t < 1800 && Math.random() < 0.8) {
      parts.push({ x: Math.random() * W, y: -10, vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3, g: 0.06, s: 4 + Math.random() * 5,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.2, c: colors[Math.floor(Math.random() * colors.length)], life: 1, shape: "rect" });
    }
    for (const p of parts) {
      p.vy += p.g; p.x += p.vx; p.y += p.vy; p.vx *= 0.985; p.r += p.vr;
      p.life = Math.max(0, 1 - t / total);
      ctx.save(); ctx.globalAlpha = p.life; ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c;
      if (p.shape === "circle") { ctx.beginPath(); ctx.arc(0, 0, p.s / 2, 0, Math.PI * 2); ctx.fill(); }
      else ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
      ctx.restore();
    }
    if (t < total) raf = requestAnimationFrame(frame);
    else ctx.clearRect(0, 0, W, H);
  };
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(frame);
}

// ─── Fondo ambiental (magenta + palmeras + brillo) — igual que la Ruleta ───
function AmbientBackdrop() {
  return (
    <>
      <div className="pointer-events-none absolute inset-0" style={{
        background: "radial-gradient(ellipse 70% 55% at 50% 30%, #3B0A2E 0%, #180418 35%, #060008 75%), linear-gradient(180deg, #060008 0%, #0A0208 100%)",
      }} />
      <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-[4%] h-[55%] w-[80%] rounded-full opacity-40 blur-3xl" style={{ background: "radial-gradient(circle, #EC4899 0%, transparent 70%)" }} />
      <svg className="pointer-events-none absolute top-0 left-0 w-full h-[34%] opacity-25" viewBox="0 0 1600 500" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id="ad-palm-g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#000" stopOpacity="0.85" /><stop offset="1" stopColor="#000" stopOpacity="0.2" /></linearGradient></defs>
        <path d="M120,500 L130,220 Q140,180 175,175 Q145,180 130,150 Q120,120 165,110 Q120,90 140,50 Q170,90 175,140 Q180,90 220,80 Q195,120 190,160 Q220,120 260,120 Q225,160 205,190 Q235,190 260,175 Q225,200 190,220 L200,500 Z" fill="url(#ad-palm-g)" />
        <path d="M1450,500 L1460,240 Q1475,200 1510,195 Q1480,200 1465,170 Q1455,140 1500,130 Q1455,110 1475,70 Q1505,110 1510,160 Q1515,110 1555,100 Q1530,140 1525,180 Q1555,140 1595,140 Q1560,180 1540,210 L1530,500 Z" fill="url(#ad-palm-g)" />
      </svg>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[38%]" style={{ background: "linear-gradient(0deg, rgba(236,72,153,0.15) 0%, rgba(236,72,153,0.03) 40%, transparent 100%)" }} />
    </>
  );
}

function GameTitle() {
  return (
    <div className="relative select-none">
      <div className="relative flex items-baseline gap-2 pl-1">
        <h2 className="font-black italic tracking-[0.02em] leading-none text-3xl sm:text-4xl md:text-5xl" style={{ color: "#FFF", textShadow: "0 2px 12px rgba(0,0,0,0.7)" }}>AIR</h2>
        <h2 className="font-black italic tracking-[0.02em] leading-none text-3xl sm:text-4xl md:text-5xl" style={{
          background: "linear-gradient(180deg, #FF3D9A 0%, #EC4899 55%, #BE185D 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
          filter: "drop-shadow(0 0 18px rgba(236,72,153,0.55))",
        }}>DROP</h2>
      </div>
      <div className="mt-1.5 pl-1 text-[10px] sm:text-[11px] font-black tracking-[0.35em] text-white/85 uppercase">Evento global · un solo ganador</div>
    </div>
  );
}

function ChipHud({ children, tone = PINK, testId }) {
  return (
    <div className="relative flex items-center h-11 px-4 rounded-md overflow-hidden shrink-0"
      style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: `0 8px 24px rgba(0,0,0,0.55), inset 0 0 0 1px ${tone}88` }}
      data-testid={testId}>
      {children}
    </div>
  );
}

function BalanceHud({ label, amount, icon: Icon, tone, testId }) {
  return (
    <div className="relative flex items-stretch h-11 rounded-md overflow-hidden shrink-0" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: `0 8px 24px rgba(0,0,0,0.55), inset 0 0 0 1px ${tone}88` }} data-testid={testId}>
      <div className="pl-3 pr-2 flex items-center text-[9px] sm:text-[10px] font-black tracking-[0.3em] text-white/70 uppercase">{label}</div>
      <div className="relative flex items-center px-3 min-w-[92px]" style={{ background: `linear-gradient(180deg, ${tone} 0%, ${tone}aa 100%)`, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.15)" }}>
        <span className="text-base sm:text-lg font-black tabular-nums text-white" style={{ textShadow: "0 2px 8px rgba(0,0,0,0.6)" }}>{Number(amount || 0).toLocaleString()}</span>
        <div className="ml-2 h-5 w-5 rounded-sm flex items-center justify-center" style={{ background: "rgba(0,0,0,0.35)" }}><Icon size={12} color="#fff" strokeWidth={2.5} /></div>
      </div>
    </div>
  );
}

// Puntero superior estilo Ruleta.
function IndicatorTriangle() {
  return (
    <motion.div className="pointer-events-none absolute left-1/2 -translate-x-1/2 z-30" style={{ top: 6 }} animate={{ y: [0, 6, 0] }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}>
      <div style={{ width: 0, height: 0, borderLeft: "18px solid transparent", borderRight: "18px solid transparent", borderTop: "22px solid #FFFFFF", filter: "drop-shadow(0 0 18px rgba(236,72,153,0.9)) drop-shadow(0 0 40px rgba(236,72,153,0.55))" }} />
    </motion.div>
  );
}

// Tarima con curva y brillo rosa (piso donde se posa el cofre).
function StageBar() {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-[14%] mx-auto max-w-[1100px] px-6 z-0">
      <svg viewBox="0 0 1100 60" className="w-full h-[60px]" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id="ad-stage-g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stopColor="rgba(120,10,80,0)" /><stop offset="0.35" stopColor="rgba(236,72,153,0.65)" /><stop offset="0.5" stopColor="rgba(255,255,255,0.85)" /><stop offset="0.65" stopColor="rgba(236,72,153,0.65)" /><stop offset="1" stopColor="rgba(120,10,80,0)" /></linearGradient></defs>
        <path d="M0 30 Q 550 -8 1100 30" fill="none" stroke="url(#ad-stage-g)" strokeWidth="2" />
        <path d="M0 30 Q 550 4 1100 30" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
      </svg>
      <div className="absolute inset-x-0 top-[26px] h-16" style={{ background: "radial-gradient(50% 100% at 50% 0%, rgba(236,72,153,0.30) 0%, transparent 70%)", filter: "blur(6px)" }} />
    </div>
  );
}

// ─── El COFRE que se abre (HTML/CSS 3D, tintado por rareza) ───
// Ojo: los nodos con animación de Motion NO pueden centrarse con `-translate-x-1/2`
// de Tailwind (Motion sobreescribe `transform`). Por eso el centrado va en un
// wrapper estático y la rotación/entrada van en un hijo motion.
function Chest({ accent, open = false, size = 190, shake = false }) {
  const lid = open ? -125 : 0;
  const bodyW = size * 0.74, lidH = size * 0.34;
  return (
    <div className="relative" style={{ width: size, height: size * 0.92 }} data-testid="airdrop-crate">
      {/* Halo de rareza */}
      <div className="absolute left-1/2 top-1/2 rounded-full" style={{ width: size * 1.3, height: size * 1.3, transform: "translate(-50%,-50%)",
        background: `radial-gradient(circle, ${accent}88 0%, transparent 65%)`, filter: "blur(24px)", opacity: open ? 0.95 : 0.55 }} />
      {/* Rayos de luz al abrir */}
      <AnimatePresence>
        {open && (
          <div key="rays" className="absolute left-1/2" style={{ bottom: size * 0.42, width: size * 0.7, height: size * 0.9, transform: "translateX(-50%)" }}>
            <motion.div initial={{ opacity: 0, scaleY: 0.4 }} animate={{ opacity: 1, scaleY: 1 }} exit={{ opacity: 0 }} className="w-full h-full"
              style={{ transformOrigin: "50% 100%", filter: "blur(2px)", mixBlendMode: "screen",
                background: `conic-gradient(from 200deg at 50% 100%, transparent 0deg, ${accent}00 20deg, ${accent}cc 40deg, #fff 50deg, ${accent}cc 60deg, ${accent}00 80deg, transparent 100deg)` }} />
          </div>
        )}
      </AnimatePresence>

      <motion.div className="absolute inset-0" animate={shake && !open ? { x: [0, -2, 2, -2, 2, 0] } : { x: 0 }} transition={shake ? { duration: 1.2, repeat: Infinity } : { duration: 0.3 }}>
        {/* Interior brillante (visible al abrir) */}
        <div className="absolute left-1/2" style={{ bottom: size * 0.14, width: size * 0.64, height: size * 0.3, transform: "translateX(-50%)", borderRadius: "8px 8px 0 0",
          background: `radial-gradient(60% 90% at 50% 100%, #fff 0%, ${accent} 45%, ${accent}55 100%)`, opacity: open ? 1 : 0, transition: "opacity .25s", boxShadow: `0 0 40px ${accent}` }} />

        {/* Cuerpo del cofre */}
        <div className="absolute left-1/2 overflow-hidden" style={{ bottom: 0, width: bodyW, height: size * 0.5, transform: "translateX(-50%)", borderRadius: 10,
          background: "linear-gradient(180deg, #5a3a22 0%, #3a2414 60%, #26160b 100%)",
          boxShadow: `0 18px 40px rgba(0,0,0,0.6), inset 0 0 0 2px ${accent}, inset 0 -14px 26px rgba(0,0,0,0.45)` }}>
          <div className="absolute inset-0" style={{ background: "linear-gradient(160deg, rgba(255,255,255,0.12) 0%, transparent 45%)" }} />
          {[0.2, 0.5, 0.8].map((l) => (
            <div key={l} className="absolute top-0 bottom-0" style={{ left: `${l * 100}%`, width: 6, transform: "translateX(-50%)", background: `linear-gradient(180deg, ${accent}, ${accent}77)`, opacity: 0.7 }} />
          ))}
          <div className="absolute left-1/2 top-1 h-8 w-8 rounded-md flex items-center justify-center"
            style={{ transform: "translateX(-50%)", background: `radial-gradient(circle at 40% 30%, #fff6, ${accent})`, boxShadow: `0 2px 8px rgba(0,0,0,.5), inset 0 0 0 1.5px ${accent}` }}>
            <div className="h-3 w-2 rounded-sm bg-black/50" />
          </div>
        </div>

        {/* Tapa: wrapper estático (centrado) + hijo motion (bisagra 3D) */}
        <div className="absolute left-1/2" style={{ bottom: size * 0.46, width: bodyW, height: lidH, transform: "translateX(-50%)", perspective: 800 }}>
          <motion.div className="relative w-full h-full overflow-hidden" style={{ transformOrigin: "50% 100%", borderRadius: "12px 12px 0 0",
            background: "linear-gradient(180deg, #6a4526 0%, #4a2e18 100%)", boxShadow: `inset 0 0 0 2px ${accent}, 0 -6px 18px rgba(0,0,0,0.4)` }}
            animate={{ rotateX: lid }} transition={{ type: "spring", stiffness: 120, damping: 14 }}>
            <div className="absolute inset-0" style={{ background: "linear-gradient(160deg, rgba(255,255,255,0.18) 0%, transparent 50%)" }} />
            <div className="absolute left-1/2 top-1 h-2.5 w-2.5 rounded-full" style={{ transform: "translateX(-50%)", background: accent, boxShadow: `0 0 10px ${accent}` }} />
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}

// Paracaídas + cofre colgando (fase cayendo), sobre el escenario magenta.
function ParachuteCrate({ accent, chute, size = 120 }) {
  return (
    <motion.div style={{ width: size, transformOrigin: "50% 0%" }} animate={{ rotate: [-7, 7, -7] }}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }} data-testid="airdrop-parachute">
      <svg viewBox="0 0 120 150" width={size} height={size * 1.25} style={{ filter: `drop-shadow(0 8px 26px ${accent})` }}>
        <path d="M6 46 A54 54 0 0 1 114 46 Z" fill={chute} opacity="0.97" />
        <path d="M6 46 A54 54 0 0 1 114 46" fill="none" stroke="rgba(0,0,0,.28)" strokeWidth="1.4" />
        {[24, 48, 72, 96].map((x) => <path key={x} d={`M${x} 46 Q60 44 60 46`} stroke="rgba(0,0,0,.2)" strokeWidth="1" fill="none" />)}
        {[14, 42, 78, 106].map((x, i) => <line key={i} x1={x} y1="47" x2="60" y2="92" stroke="rgba(255,255,255,.55)" strokeWidth="1" />)}
        <rect x="40" y="90" width="40" height="38" rx="4" fill="#3a2414" stroke={accent} strokeWidth="2.5" />
        <rect x="40" y="103" width="40" height="6" fill={accent} opacity="0.85" />
        <rect x="56" y="90" width="8" height="38" fill={accent} opacity="0.55" />
      </svg>
    </motion.div>
  );
}

// ─── Botón brillante estilo Ruleta ───
function GlossyButton({ children, onClick, disabled, active = true, testId }) {
  return (
    <button onClick={onClick} disabled={disabled} data-testid={testId}
      className="relative h-14 sm:h-16 min-w-[260px] sm:min-w-[320px] px-8 rounded-lg overflow-hidden disabled:opacity-70 disabled:cursor-not-allowed"
      style={{ background: active ? "linear-gradient(180deg, #FF3D9A 0%, #EC4899 55%, #BE185D 100%)" : "linear-gradient(180deg, #3A0A24 0%, #1B0410 100%)",
        boxShadow: active ? "0 0 40px rgba(236,72,153,0.75), 0 12px 28px rgba(0,0,0,0.55), inset 0 -6px 0 rgba(0,0,0,0.35), inset 0 2px 0 rgba(255,255,255,0.25)" : "0 8px 16px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.08)" }}>
      {active && !disabled && (
        <motion.div className="absolute inset-0 pointer-events-none" animate={{ backgroundPositionX: ["-100%", "220%"] }} transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }}
          style={{ backgroundImage: "linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.4) 50%, transparent 70%)", backgroundSize: "50% 100%", backgroundRepeat: "no-repeat" }} />
      )}
      <span className="relative text-xl sm:text-2xl font-black tracking-[0.28em] text-white" style={{ textShadow: "0 2px 8px rgba(0,0,0,0.5)" }}>{children}</span>
    </button>
  );
}

// ─── Tarjeta de recompensa estilo placa de la Ruleta (flip al clic) ───
function RewardCard({ reward, index, revealed, onReveal, img }) {
  const th = pal(reward._rarity);
  const isSpecial = reward.special || reward.key === "resurrection_token";
  const accent = isSpecial ? "#F59E0B" : th.accent;
  return (
    <button type="button" onClick={() => !revealed && onReveal(index)} data-testid={`airdrop-reward-card-${index}`}
      className="relative aspect-[3/4] rounded-xl overflow-hidden select-none focus:outline-none" style={{ perspective: 900 }}>
      <motion.div className="relative w-full h-full" style={{ transformStyle: "preserve-3d" }} initial={false}
        animate={{ rotateY: revealed ? 180 : 0 }} transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}>
        {/* Dorso */}
        <div className="absolute inset-0 rounded-xl flex items-center justify-center overflow-hidden"
          style={{ backfaceVisibility: "hidden", background: "linear-gradient(180deg, #24041a 0%, #0a0206 100%)", boxShadow: `inset 0 0 0 1.5px ${PINK}66` }}>
          <div className="absolute inset-0 opacity-40" style={{ background: "repeating-linear-gradient(-24deg, transparent 0 22px, rgba(255,255,255,0.03) 22px 23px)" }} />
          <motion.div animate={{ scale: [1, 1.08, 1] }} transition={{ duration: 1.4, repeat: Infinity }}>
            <Gift size={30} style={{ color: PINK }} />
          </motion.div>
        </div>
        {/* Frente */}
        <div className="absolute inset-0 rounded-xl overflow-hidden flex flex-col items-center px-2 pt-6 pb-3"
          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)", background: th.bg,
            boxShadow: `0 16px 30px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.08)${isSpecial ? `, 0 0 26px ${accent}88` : ""}` }}>
          <div className="pointer-events-none absolute inset-0" style={{ background: "linear-gradient(160deg, rgba(255,255,255,0.16) 0%, transparent 50%)" }} />
          {/* Cinta de rareza */}
          <div className="absolute top-0 left-0 right-0 flex justify-center">
            <span className="px-2.5 py-[2px] rounded-b-md text-[8px] font-black tracking-[0.28em] uppercase whitespace-nowrap"
              style={{ background: `linear-gradient(180deg, ${accent}, ${accent}aa)`, color: "#0B0208" }}>
              {isSpecial ? "ESPECIAL" : th.es}
            </span>
          </div>
          {/* Disco radial con imagen real (o emoji de respaldo) */}
          <div className="relative flex-1 w-full flex items-center justify-center">
            <div className="relative flex items-center justify-center h-[62px] w-[62px] rounded-full"
              style={{ background: `radial-gradient(circle at 40% 30%, rgba(255,255,255,0.35), rgba(255,255,255,0.05) 40%, transparent 70%), radial-gradient(circle at 50% 60%, ${accent} 0%, ${accent}88 55%, ${accent}22 100%)`,
                border: `2px solid ${accent}`, boxShadow: `0 8px 20px rgba(0,0,0,0.5), 0 0 26px ${accent}66` }}>
              {img ? (
                <img src={img} alt={reward.name} className="h-[46px] w-[46px] object-contain" draggable={false} loading="lazy"
                  style={{ filter: `drop-shadow(0 3px 6px ${accent}88) drop-shadow(0 0 8px rgba(255,255,255,0.3))` }} />
              ) : (
                <span className="text-2xl leading-none">{rewardIcon(reward)}</span>
              )}
            </div>
          </div>
          <div className="text-[10px] font-black tracking-[0.06em] text-white uppercase text-center leading-tight truncate w-full">{reward.name}</div>
          <div className="font-display font-black text-lg" style={{ color: isSpecial ? "#fcd34d" : "#fff" }}>×{Number(reward.qty || 1).toLocaleString()}</div>
        </div>
      </motion.div>
    </button>
  );
}

// ─── Pool de botín posible (estilo "Premios posibles" de la Ruleta) ───
function lootRows(lt, matImg) {
  if (!lt) return [];
  const rows = [];
  const mat = lt.materials || {};
  if ((mat.chance || 0) > 0) {
    rows.push({ key: "materials", name: "Materiales de crafteo", detail: `×${mat.picks || 1} tipos · ${mat.min}–${mat.max} c/u`,
      chance: mat.chance, imgs: ["bones", "metal", "leather", "polymer"].map((k) => matImg && matImg[k]).filter(Boolean) });
  }
  const pm = lt.primemeat || {};
  if ((pm.chance || 0) > 0) rows.push({ key: "primemeat", name: "PrimeMeat", detail: `${Number(pm.min || 0).toLocaleString()}–${Number(pm.max || 0).toLocaleString()}`, chance: pm.chance, img: "/coins/meat.png" });
  const am = lt.amberium || {};
  if ((am.chance || 0) > 0) rows.push({ key: "amberium", name: "Amberium", detail: `${Number(am.min || 0).toLocaleString()}–${Number(am.max || 0).toLocaleString()}`, chance: am.chance, img: "/coins/amber.png" });
  [["growth_token", "Growth Token", "/tokens/growth.png"], ["diet_token", "Diet Token", "/tokens/diet.png"], ["resurrection_token", "Resurrection Token", "/fossil.png"]].forEach(([k, nm, img]) => {
    const c = (lt[k] || {}).chance || 0;
    if (c > 0) rows.push({ key: k, name: nm, detail: "×1", chance: c, img, special: k === "resurrection_token" });
  });
  return rows;
}

function LootPool({ pool, matImg }) {
  if (!pool || !pool.loot) return null;
  const weights = pool.rarity_weights || {};
  const totalW = Object.values(weights).reduce((a, b) => a + (Number(b) || 0), 0) || 1;
  const order = ["common", "rare", "epic", "legendary"];
  return (
    <div className="relative px-4 sm:px-6 md:px-8 pb-6 pt-2" data-testid="airdrop-pool">
      <div className="rounded-xl overflow-hidden" style={{ background: "linear-gradient(180deg, rgba(24,4,24,0.92) 0%, rgba(6,0,4,0.92) 100%)", boxShadow: "inset 0 0 0 1px rgba(236,72,153,0.25)" }}>
        <div className="px-4 py-2.5 flex items-center justify-between gap-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 min-w-0">
            <Package size={13} className="text-pink-400 shrink-0" />
            <span className="text-[11px] font-black tracking-[0.3em] text-white uppercase whitespace-nowrap">Botín posible</span>
          </div>
          <span className="hidden sm:block text-[9px] font-black tracking-[0.25em] text-white/40 uppercase truncate">Cada suministro es de una rareza · el contenido se genera al caer</span>
        </div>
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {order.map((r) => {
            const th = pal(r);
            const rows = lootRows(pool.loot[r], matImg);
            const wPct = Math.round((Number(weights[r]) || 0) / totalW * 100);
            return (
              <div key={r} className="rounded-lg overflow-hidden" style={{ background: "rgba(0,0,0,0.35)", boxShadow: `inset 0 0 0 1px ${th.accent}55` }} data-testid={`airdrop-pool-${r}`}>
                <div className="px-3 py-2 flex items-center justify-between" style={{ background: `linear-gradient(180deg, ${th.accent}33, transparent)` }}>
                  <span className="text-[11px] font-black tracking-[0.22em] uppercase" style={{ color: th.accent }}>{th.es}</span>
                  <span className="text-[10px] font-black tabular-nums px-2 py-0.5 rounded-full" style={{ background: `${th.accent}22`, color: th.accent }}>{wPct}%</span>
                </div>
                <ul className="p-2 space-y-1.5">
                  {rows.map((row) => (
                    <li key={row.key} className="flex items-center gap-2.5 rounded-md px-2 py-1.5" style={{ background: "rgba(255,255,255,0.03)" }}>
                      <div className="shrink-0 h-9 w-9 rounded-md flex items-center justify-center overflow-hidden" style={{ background: `radial-gradient(circle at 40% 30%, ${(row.special ? "#F59E0B" : th.accent)}55, ${(row.special ? "#F59E0B" : th.accent)}18)`, border: `1.5px solid ${(row.special ? "#F59E0B" : th.accent)}88` }}>
                        {row.imgs && row.imgs.length ? (
                          <div className="grid grid-cols-2 gap-px p-0.5">
                            {row.imgs.slice(0, 4).map((src, i) => <img key={i} src={src} alt="" className="h-3.5 w-3.5 object-contain" draggable={false} loading="lazy" />)}
                          </div>
                        ) : row.img ? (
                          <img src={row.img} alt="" className="h-6 w-6 object-contain" draggable={false} loading="lazy" />
                        ) : <Gift size={16} style={{ color: th.accent }} />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-black text-white uppercase truncate leading-tight">{row.name}</div>
                        <div className="text-[9px] font-bold text-white/50 tabular-nums truncate">{row.detail}</div>
                      </div>
                      <span className="shrink-0 text-[10px] font-black tabular-nums" style={{ color: th.accent }}>{row.chance}%</span>
                    </li>
                  ))}
                  {rows.length === 0 && <li className="text-[10px] text-white/40 italic px-2 py-1">Sin recompensas</li>}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </div>
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
  const confettiRef = useRef(null);
  const [matImg, setMatImg] = useState({});
  const [pool, setPool] = useState(null);

  // Carga los iconos reales de materiales (mismos que el sistema de crafteo)
  // y el pool de botín posible por rareza.
  useEffect(() => {
    let alive = true;
    api.craftingState()
      .then((r) => {
        if (!alive) return;
        const map = {};
        (r.data?.materials || []).forEach((m) => { if (m?.id && m?.icon) map[m.id] = m.icon; });
        setMatImg(map);
      })
      .catch(() => {});
    api.airdropPool()
      .then((r) => { if (alive) setPool(r.data); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

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

  const rawRewards = claimResult?.rewards || state?.my_rewards || null;
  const myRewards = rawRewards ? rawRewards.map((r) => ({ ...r, _rarity: state?.rarity })) : null;
  const iAmWinner = !!myRewards || (claimResult?.winner === true);

  const doClaim = useCallback(async () => {
    if (claiming) return;
    setClaiming(true);
    try {
      const r = await claim();
      setClaimResult(r);
      play("airdropClaimed");
      if (state?.rarity === "legendary" || state?.rarity === "epic") {
        setTimeout(() => fireConfetti(confettiRef.current, state?.rarity === "legendary"), 250);
      }
    } catch (e) {
      const detail = e?.response?.data?.detail || "No se pudo reclamar el Airdrop.";
      toast.error(detail, { icon: <ShieldAlert className="w-4 h-4 text-[#ff6b74]" /> });
    } finally {
      setClaiming(false);
    }
  }, [claiming, claim, play, state?.rarity]);

  const onReveal = useCallback((idx) => {
    setRevealed((prev) => {
      if (prev.has(idx)) return prev;
      const next = new Set(prev);
      next.add(idx);
      const rw = myRewards?.[idx];
      const special = (rw && (rw.special || rw.key === "resurrection_token")) || state?.rarity === "legendary";
      play(special ? "airdropLegendary" : "airdropAvailable");
      if (special) fireConfetti(confettiRef.current, true);
      return next;
    });
  }, [myRewards, state?.rarity, play]);

  const revealAll = useCallback(() => {
    if (!myRewards) return;
    myRewards.forEach((_, i) => setTimeout(() => onReveal(i), i * 240));
  }, [myRewards, onReveal]);

  const dropAt = ms(state?.drop_at), landAt = ms(state?.land_at), expireAt = ms(state?.expire_at);
  const nextAt = ms(state?.next_at), cooldownUntil = ms(state?.cooldown_until);
  const fallProgress = landAt > dropAt ? Math.min(1, Math.max(0, (now - dropAt) / (landAt - dropAt))) : 0;

  return (
    <div className="relative rounded-2xl overflow-hidden text-white" data-testid="airdrop-arena"
      style={{ boxShadow: "0 30px 80px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.06)" }}>
      <AmbientBackdrop />
      <canvas ref={confettiRef} className="pointer-events-none absolute inset-0 z-[45]" aria-hidden="true" />
      <style>{`@keyframes ad-beam { 0%,100% { transform: rotate(-16deg); opacity:.25 } 50% { transform: rotate(16deg); opacity:.55 } }`}</style>

      {/* Barra superior */}
      <div className="relative flex flex-col lg:flex-row lg:items-start justify-between px-4 sm:px-6 md:px-8 pt-5 sm:pt-6 gap-3">
        <GameTitle />
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap lg:justify-end">
          <ChipHud tone={connected ? "#22C55E" : "#94A3B8"} testId="airdrop-conn">
            <span className={`h-1.5 w-1.5 rounded-full mr-1.5 ${connected ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
            <span className="text-[9px] font-black tracking-[0.3em] uppercase" style={{ color: connected ? "#22C55E" : "#94A3B8" }}>{connected ? "EN VIVO" : "OFF"}</span>
          </ChipHud>
          {state?.rarity && (
            <ChipHud tone={p.accent} testId="airdrop-rarity">
              <Package size={13} style={{ color: p.accent }} className="mr-2" />
              <span className="text-[11px] font-black tracking-[0.25em] uppercase" style={{ color: p.accent, textShadow: `0 0 10px ${p.accent}88` }}>{p.es}</span>
            </ChipHud>
          )}
          <BalanceHud label="PRIMEMEAT" amount={user?.coins ?? 0} icon={Coins} tone="#FF2489" testId="airdrop-balance-hud" />
          <BalanceHud label="AMBERIUM" amount={user?.vip_coins ?? 0} icon={Gem} tone="#F59E0B" testId="airdrop-amber-hud" />
        </div>
      </div>

      {/* Escenario */}
      <div className="relative" style={{ minHeight: 430 }} data-testid="airdrop-scene">
        <IndicatorTriangle />
        <StageBar />

        <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center pt-8 pb-6">
          {/* Reflectores en alerta */}
          {(st === "incoming" || st === "falling") && (
            <>
              <div className="absolute -top-6 left-[24%] w-40 h-[440px] origin-top" style={{ background: `linear-gradient(${p.accent}66, transparent)`, animation: "ad-beam 4s ease-in-out infinite", clipPath: "polygon(45% 0, 55% 0, 100% 100%, 0 100%)" }} />
              <div className="absolute -top-6 right-[24%] w-40 h-[440px] origin-top" style={{ background: `linear-gradient(${p.accent}66, transparent)`, animation: "ad-beam 4s ease-in-out .8s infinite", clipPath: "polygon(45% 0, 55% 0, 100% 100%, 0 100%)" }} />
            </>
          )}

          <AnimatePresence mode="wait">
            {/* WAITING */}
            {st === "waiting" && (
              <motion.div key="waiting" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-4">
                <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity }}>
                  <Chest accent={p.accent} />
                </motion.div>
                <div>
                  <p className="text-[11px] font-black tracking-[0.35em] text-white/70 uppercase mb-1">Próximo suministro global en</p>
                  <p className="font-black italic text-5xl sm:text-6xl tabular-nums leading-none" data-testid="airdrop-countdown"
                    style={{ background: "linear-gradient(180deg,#FF3D9A,#EC4899,#BE185D)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", filter: "drop-shadow(0 0 20px rgba(236,72,153,0.55))" }}>
                    {fmt(dropAt - now)}
                  </p>
                </div>
              </motion.div>
            )}

            {/* INCOMING */}
            {st === "incoming" && (
              <motion.div key="incoming" initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3">
                <motion.p animate={{ opacity: [0.5, 1, 0.5] }} transition={{ duration: 1, repeat: Infinity }}
                  className="font-black italic text-xl sm:text-2xl tracking-[0.2em]" style={{ color: p.accent, textShadow: `0 0 26px ${p.accent}` }}>
                  ⚠ SUMINISTRO ENTRANTE
                </motion.p>
                <p className="font-black italic text-6xl tabular-nums" data-testid="airdrop-countdown"
                  style={{ color: "#fff", textShadow: `0 0 34px ${p.accent}` }}>{fmt(dropAt - now)}</p>
                <p className="text-[11px] font-black tracking-[0.3em] text-white/70 uppercase">Prepárate... está por caer</p>
              </motion.div>
            )}

            {/* FALLING */}
            {st === "falling" && (
              <motion.div key="falling" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0">
                <div className="absolute left-1/2 -translate-x-1/2" style={{ top: `${6 + fallProgress * 58}%`, transition: "top 80ms linear" }}>
                  <ParachuteCrate accent={p.accent} chute={p.chute} />
                </div>
                <motion.p animate={{ opacity: [0.5, 1, 0.5] }} transition={{ duration: 1.2, repeat: Infinity }}
                  className="absolute bottom-8 left-0 right-0 font-black italic text-lg tracking-[0.15em]" style={{ color: p.accent, textShadow: `0 0 20px ${p.accent}` }}>
                  🪂 CAYENDO SOBRE LA ISLA...
                </motion.p>
              </motion.div>
            )}

            {/* AVAILABLE */}
            {st === "available" && (
              <motion.div key="available" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3">
                <motion.div animate={iAmWinner ? {} : { y: [0, -7, 0], scale: [1, 1.03, 1] }} transition={{ duration: 1.5, repeat: Infinity }}>
                  <Chest accent={p.accent} open={iAmWinner} shake={!iAmWinner} />
                </motion.div>
                {iAmWinner ? (
                  <p className="font-black italic text-lg" style={{ color: p.accent, textShadow: `0 0 18px ${p.accent}` }}>¡Es tuyo! Abre tus recompensas abajo 👇</p>
                ) : (
                  <>
                    <div className="flex items-center gap-2 h-8 px-4 rounded-md" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: "inset 0 0 0 1px rgba(236,72,153,0.55)" }}>
                      <Clock size={12} className="text-pink-300" />
                      <span className="text-[11px] font-black tracking-[0.28em] text-white/90 uppercase tabular-nums">Se cierra en {fmt(expireAt - now)}</span>
                    </div>
                    <GlossyButton onClick={doClaim} disabled={claiming} testId="airdrop-claim-btn">
                      {claiming ? "RECLAMANDO…" : "RECLAMAR"}
                    </GlossyButton>
                    <p className="text-[10px] font-black tracking-[0.28em] text-white/55 uppercase">Solo el primero se lo lleva</p>
                  </>
                )}
              </motion.div>
            )}

            {/* CLAIMED */}
            {st === "claimed" && (
              <motion.div key="claimed" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3">
                <Chest accent={p.accent} open />
                {iAmWinner ? (
                  <>
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 200 }} className="flex items-center gap-2">
                      <Trophy size={26} style={{ color: p.accent }} />
                      <p className="font-black italic text-xl sm:text-2xl" style={{ color: "#fff", textShadow: `0 0 24px ${p.accent}` }}>¡GANASTE EL AIRDROP {p.es}!</p>
                    </motion.div>
                    <p className="text-[11px] font-black tracking-[0.28em] text-white/70 uppercase">Toca cada carta para revelar tu botín</p>
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      {state?.winner?.avatar && <img src={state.winner.avatar} alt="" className="w-8 h-8 rounded-full object-cover" style={{ boxShadow: `0 0 0 2px ${p.accent}` }} />}
                      <p className="font-black italic text-lg">🏆 {state?.winner?.name || "Otro superviviente"} se lo llevó</p>
                    </div>
                    <div className="flex items-center gap-2 h-8 px-4 rounded-md" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)" }}>
                      <Clock size={12} className="text-pink-300" />
                      <span className="text-[11px] font-black tracking-[0.25em] text-white/85 uppercase tabular-nums">Próximo airdrop en {fmt((nextAt || cooldownUntil) - now)}</span>
                    </div>
                  </>
                )}
              </motion.div>
            )}

            {/* EXPIRED */}
            {st === "expired" && (
              <motion.div key="expired" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3">
                <div className="opacity-50 grayscale"><Chest accent={p.accent} /></div>
                <p className="font-black italic text-lg text-white/70">Nadie reclamó el suministro</p>
                <div className="flex items-center gap-2 h-8 px-4 rounded-md" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)" }}>
                  <Clock size={12} className="text-pink-300" />
                  <span className="text-[11px] font-black tracking-[0.25em] text-white/85 uppercase tabular-nums">Próximo airdrop en {fmt((nextAt || cooldownUntil) - now)}</span>
                </div>
              </motion.div>
            )}

            {/* DISABLED / sin datos */}
            {(st === "disabled" || !st) && (
              <motion.div key="disabled" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-3">
                <div className="opacity-40"><Chest accent={p.accent} /></div>
                <p className="text-white/60 text-sm">{st === "disabled" ? "Los Airdrops están desactivados por ahora." : "Sincronizando evento global…"}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Panel de recompensas del ganador (carta por carta) */}
      <AnimatePresence>
        {iAmWinner && myRewards && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="relative px-4 sm:px-6 md:px-8 pb-6 pt-2" data-testid="airdrop-rewards-panel">
            <div className="rounded-xl overflow-hidden" style={{ background: "linear-gradient(180deg, rgba(24,4,24,0.92) 0%, rgba(6,0,4,0.92) 100%)", boxShadow: "inset 0 0 0 1px rgba(236,72,153,0.25)" }}>
              <div className="px-4 py-2.5 flex items-center justify-between gap-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2 min-w-0">
                  <Sparkles size={13} className="text-pink-400 shrink-0" />
                  <span className="text-[11px] font-black tracking-[0.3em] text-white uppercase whitespace-nowrap">Tu botín {p.es}</span>
                </div>
                <button onClick={revealAll} data-testid="airdrop-reveal-all"
                  className="px-3 py-1.5 rounded-md text-[10px] font-black tracking-[0.2em] uppercase" style={{ background: "linear-gradient(90deg, #EC4899, #BE185D)", color: "#fff", boxShadow: "0 0 16px rgba(236,72,153,0.5)" }}>
                  Revelar todo
                </button>
              </div>
              <div className="p-4 grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
                {myRewards.map((rw, i) => (
                  <RewardCard key={i} reward={rw} index={i} revealed={revealed.has(i)} onReveal={onReveal} img={rewardImage(rw, matImg)} />
                ))}
              </div>
              {revealed.size === myRewards.length && (
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center text-[11px] font-black tracking-[0.2em] text-emerald-400 uppercase pb-4">
                  ✓ Recompensas añadidas a tu cuenta
                </motion.p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!user?.steam_id && st === "available" && !iAmWinner && (
        <p className="relative text-center text-[11px] font-black tracking-[0.2em] text-amber-400/90 uppercase pb-5" data-testid="airdrop-steam-warn">
          Necesitas iniciar sesión con Steam para reclamar el Airdrop
        </p>
      )}

      {/* Pool de botín posible por rareza */}
      <LootPool pool={pool} matImg={matImg} />
    </div>
  );
}
