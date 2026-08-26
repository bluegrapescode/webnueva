import React, { useMemo, useState, useEffect, useRef } from "react";
import { motion, AnimatePresence, useMotionValue, useSpring, useTransform } from "framer-motion";
import { AlertTriangle, Biohazard, Activity, Radio, ShieldAlert, Skull, RotateCcw, Hourglass } from "lucide-react";
import { useGen0Contamination, gen0StatusFor, formatGen0Cooldown } from "./useGen0Contamination";
import { useSound } from "@/context/SoundContext";

/**
 * Gen0VirusPanel — Panel de contención biológica GEN-Ø.
 *
 * Props:
 *   percent (opcional): 0..100. Si se pasa, se ignora el hook demo interno
 *                       (así es fácil enchufar el valor real desde afuera).
 *
 * Cuando el porcentaje llega a 100% por primera vez:
 *   - Se dispara el rugido de zombie (SFX)
 *   - Se muestra el banner crítico "TRANSFORMACIÓN BIOLÓGICA DETECTADA"
 *   - La barra queda congelada en 100% (para que no oscile visualmente)
 */
export function Gen0VirusPanel({ percent: percentProp }) {
  const demo = useGen0Contamination();
  const { play } = useSound();
  const hasProp    = Number.isFinite(percentProp);   // a NaN prop must never paint "NaN%"
  const rawPercent = hasProp ? percentProp : demo.percent;
  const source     = hasProp ? "live" : demo.source;

  // Once we hit 100%, freeze the visualization and lock the "critical" state.
  const [locked, setLocked] = useState(false);
  const roaredRef = useRef(false);

  useEffect(() => {
    if (!locked && rawPercent >= 100) {
      setLocked(true);
      if (!roaredRef.current) {
        roaredRef.current = true;
        try { play("zombieRoar"); } catch (_) {}
      }
    }
    // El ciclo es real desde 2026-08-21: el zombi muere y el backend reinicia
    // la barra a 0. En LIVE un porcentaje < 100 tras el bloqueo significa que
    // el reinicio ocurrió — se desbloquea (y el rugido puede sonar en la
    // próxima mutación). Sin esto el panel quedaba clavado en 100% para
    // siempre y el enfriamiento nuevo jamás se mostraba (refutación /validate).
    if (locked && source === "live" && rawPercent < 100) {
      setLocked(false);
      roaredRef.current = false;
    }
  }, [rawPercent, locked, source, play]);

  const percent = locked ? 100 : rawPercent;
  const status  = useMemo(() => gen0StatusFor(percent), [percent]);
  const clamped = Math.max(0, Math.min(100, percent));

  // Enfriamiento entre instalaciones (orden del dueño 2026-08-21): el backend
  // entrega los segundos restantes; aquí solo se descuentan localmente contra
  // el ancla Date.now() de la última respuesta — el próximo fetch re-sincroniza.
  const { cooldownS, cooldownAtMs } = demo;
  const [cdNowMs, setCdNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!(cooldownS > 0)) return undefined;
    const t = setInterval(() => setCdNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [cooldownS, cooldownAtMs]);
  const cdLeftS = cooldownS > 0
    ? Math.max(0, Math.ceil(cooldownS - (cdNowMs - cooldownAtMs) / 1000))
    : 0;

  const resetDemo = () => {
    setLocked(false);
    roaredRef.current = false;
  };

  // Smooth animated width for the fill bar
  const mv     = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 90, damping: 22 });
  React.useEffect(() => { mv.set(clamped); }, [clamped, mv]);
  const widthStr = useTransform(spring, (v) => `${v}%`);

  // Segmented bar: 40 slots to give it that DNA/DNA-strand look
  const segments = 40;
  const filledSegments = Math.round((clamped / 100) * segments);

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="relative overflow-hidden rounded-2xl border"
      data-testid="gen0-virus-panel"
      style={{
        background: "linear-gradient(180deg, #0A0508 0%, #0E0710 50%, #08040A 100%)",
        borderColor: status.color + "55",
        boxShadow: status.intensity >= 3
          ? `0 0 32px ${status.color}55, inset 0 0 30px ${status.color}18`
          : `0 0 16px ${status.color}22, inset 0 0 20px ${status.color}0F`,
      }}
    >
      {/* Ambient glow + scanline */}
      <div className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(circle at 20% 30%, ${status.color}22, transparent 55%),
                       radial-gradient(circle at 80% 70%, ${status.accent}18, transparent 55%)`,
        }}
      />
      <div className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent 0, transparent 3px, rgba(255,255,255,0.5) 3px, rgba(255,255,255,0.5) 4px)" }}
      />
      {/* Global scanline that sweeps */}
      <motion.div
        className="pointer-events-none absolute inset-x-0 h-16 opacity-40"
        animate={{ y: ["-40px", "100%"] }}
        transition={{ duration: status.intensity >= 3 ? 2.2 : 4.5, repeat: Infinity, ease: "linear" }}
        style={{ background: `linear-gradient(180deg, transparent, ${status.color}44, transparent)` }}
      />

      {/* Glitch overlay for critical states (>75%) */}
      {status.intensity >= 3 && (
        <motion.div
          className="pointer-events-none absolute inset-0 mix-blend-screen"
          animate={{ opacity: [0, 0.15, 0, 0.08, 0, 0.2, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          style={{
            backgroundImage: `linear-gradient(90deg, ${status.color}55 0 2%, transparent 2% 5%,
                              ${status.accent}44 5% 6%, transparent 6% 45%,
                              ${status.color}33 45% 47%, transparent 47%)`,
          }}
        />
      )}

      {/* HUD Corner brackets */}
      <span className="pointer-events-none absolute top-2 left-2 h-3 w-3 border-t border-l" style={{ borderColor: status.color }} />
      <span className="pointer-events-none absolute top-2 right-2 h-3 w-3 border-t border-r" style={{ borderColor: status.color }} />
      <span className="pointer-events-none absolute bottom-2 left-2 h-3 w-3 border-b border-l" style={{ borderColor: status.color }} />
      <span className="pointer-events-none absolute bottom-2 right-2 h-3 w-3 border-b border-r" style={{ borderColor: status.color }} />

      <div className="relative p-5 sm:p-7">
        {/* Header row */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2.5 min-w-0">
            <motion.span
              className="flex h-8 w-8 items-center justify-center rounded-md border"
              animate={{ scale: status.intensity >= 3 ? [1, 1.12, 1] : [1, 1.05, 1] }}
              transition={{ duration: status.intensity >= 3 ? 0.8 : 2.2, repeat: Infinity }}
              style={{ borderColor: status.color, background: status.color + "18", color: status.color }}
            >
              <Biohazard size={18} />
            </motion.span>
            <div className="min-w-0">
              <div className="text-[9px] font-black tracking-[0.4em] text-white/40">BIOHAZARD MONITOR · LEVEL 4</div>
              <h2 className="font-display font-black text-lg sm:text-xl tracking-[0.02em] leading-none mt-1 flex items-center gap-1.5">
                <span className="text-white/80">GEN-Ø</span>
                <span className="text-white/25">/</span>
                <span
                  className={status.intensity >= 3 ? "gen0-glitch" : ""}
                  data-text="CONTAMINACIÓN"
                  style={{ color: status.color }}
                >
                  CONTAMINACIÓN
                </span>
              </h2>
            </div>
          </div>
          <StatusChip status={status} source={source} />
        </div>

        {/* Big percentage + status */}
        <div className="mt-5 sm:mt-6 flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="text-[9px] font-black tracking-[0.4em] text-white/40">NIVEL DE CONTAMINACIÓN</div>
            <div className="flex items-baseline gap-1 mt-0.5">
              <motion.span
                key={Math.floor(clamped)}
                initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
                className={`font-display font-black tabular-nums leading-none text-5xl sm:text-6xl ${status.intensity >= 3 ? "gen0-glitch" : ""}`}
                data-text={`${clamped.toFixed(1)}%`}
                style={{ color: status.color, textShadow: `0 0 24px ${status.color}88` }}
              >
                {clamped.toFixed(1)}
              </motion.span>
              <span className="text-2xl font-black tabular-nums" style={{ color: status.color, opacity: 0.6 }}>%</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] font-black tracking-[0.35em] text-white/40">ESTADO</div>
            <motion.div
              key={status.key}
              initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }}
              className={`mt-1 text-sm sm:text-base font-black tracking-[0.15em] ${status.intensity >= 3 ? "gen0-glitch" : ""}`}
              data-text={status.label}
              style={{ color: status.color }}
            >
              {status.label}
            </motion.div>
          </div>
        </div>

        {/* Segmented bar */}
        <div className="mt-5 relative">
          {/* Base track */}
          <div className="relative h-6 rounded-md overflow-hidden border" style={{ borderColor: status.color + "44", background: "rgba(0,0,0,0.6)" }}>
            {/* Filled gradient */}
            <motion.div
              className="absolute inset-y-0 left-0"
              style={{
                width: widthStr,
                background: `linear-gradient(90deg, ${status.color}, ${status.accent})`,
                boxShadow: `0 0 18px ${status.color}88`,
              }}
            >
              {/* moving shine */}
              <motion.div
                className="absolute inset-0 pointer-events-none"
                animate={{ backgroundPositionX: ["-100%", "220%"] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}
                style={{
                  backgroundImage: "linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.28) 50%, transparent 70%)",
                  backgroundSize: "50% 100%", backgroundRepeat: "no-repeat",
                }}
              />
            </motion.div>

            {/* Segment dividers (thin bars) — makes it look like a bio-containment gauge */}
            <div className="absolute inset-0 flex pointer-events-none">
              {Array.from({ length: segments }).map((_, i) => {
                const filled = i < filledSegments;
                return (
                  <div key={i} className="flex-1 border-r last:border-r-0"
                    style={{ borderColor: filled ? "rgba(0,0,0,0.35)" : "rgba(255,255,255,0.03)" }} />
                );
              })}
            </div>

            {/* Tick marks on top edge */}
            <div className="absolute inset-x-0 top-0 h-full flex pointer-events-none">
              {[25, 50, 75, 100].map((tick) => (
                <div key={tick}
                  className="absolute top-0 h-2 w-px"
                  style={{ left: `${tick}%`, background: "rgba(255,255,255,0.15)" }} />
              ))}
            </div>
          </div>

          {/* Bar footer */}
          <div className="mt-2 flex items-center justify-between text-[9px] tracking-widest tabular-nums text-white/35">
            <span>0%</span>
            <span>25%</span>
            <span>50%</span>
            <span>75%</span>
            <span style={{ color: clamped >= 100 ? status.color : undefined }}>100%</span>
          </div>
        </div>

        {/* Enfriamiento entre instalaciones — countdown hasta que otra
            instalación vuelva a contar; oculto al 100% (ya no hay nada que
            reclamar) y cuando no hay ventana activa. */}
        <AnimatePresence>
          {cdLeftS > 0 && clamped < 100 && (
            <motion.div
              key="cooldown-strip"
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="mt-5 rounded-xl border p-3.5 sm:p-4 flex items-center gap-3"
              data-testid="gen0-cooldown-timer"
              style={{ borderColor: "#F59E0B55", background: "linear-gradient(90deg, #F59E0B14, transparent 65%)" }}
            >
              <motion.div
                animate={{ rotate: [0, 0, 180, 180] }}
                transition={{ duration: 3, times: [0, 0.7, 0.85, 1], repeat: Infinity }}
              >
                <Hourglass size={20} className="shrink-0" style={{ color: "#F59E0B" }} />
              </motion.div>
              <div className="min-w-0 flex-1">
                <div className="text-[9px] font-black tracking-[0.35em] uppercase" style={{ color: "#F59E0B" }}>
                  ENFRIAMIENTO ENTRE INSTALACIONES
                </div>
                <div className="mt-0.5 text-[10px] tracking-wide text-white/45">
                  Las demás instalaciones no cuentan hasta que el temporizador llegue a cero.
                </div>
              </div>
              <div
                className="font-display font-black tabular-nums text-xl sm:text-2xl shrink-0"
                data-testid="gen0-cooldown-clock"
                style={{ color: "#F59E0B", textShadow: "0 0 16px #F59E0B66" }}
              >
                {formatGen0Cooldown(cdLeftS)}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Info strip */}
        <div className="mt-5 grid grid-cols-3 gap-2 sm:gap-3">
          <MetricPill icon={<Activity size={11} />} label="SIGNAL" value={source === "live" ? "LIVE" : "DEMO"} tone={source === "live" ? status.color : "#6B7280"} />
          <MetricPill icon={<Radio size={11} />}    label="MUTATION RATE" value={rateFor(clamped)} tone={status.color} />
          <MetricPill icon={<ShieldAlert size={11} />} label="CONTAINMENT" value={containmentFor(status.intensity)} tone={status.color} />
        </div>

        {/* Critical banner at 100% — original design (no button, no timer) */}
        <AnimatePresence>
          {locked && (
            <motion.div
              key="critical-banner"
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="relative mt-5 overflow-hidden rounded-xl border p-4 sm:p-5 flex items-center gap-3"
              style={{ borderColor: status.color, background: `linear-gradient(90deg, ${status.color}22, transparent 60%)` }}
              data-testid="gen0-critical-banner"
            >
              <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 0.7, repeat: Infinity }}>
                <Skull size={26} className="shrink-0" style={{ color: status.color }} />
              </motion.div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-black tracking-[0.35em] uppercase" style={{ color: status.color }}>⚠️ BREACH CRÍTICA</div>
                <div className="mt-0.5 text-sm sm:text-base font-black tracking-wide gen0-glitch"
                  data-text="TRANSFORMACIÓN BIOLÓGICA DETECTADA"
                  style={{ color: status.accent, textShadow: `0 0 12px ${status.color}88` }}>
                  TRANSFORMACIÓN BIOLÓGICA DETECTADA
                </div>
                <div className="mt-0.5 text-[10px] tracking-[0.3em] text-white/45">
                  CÓDIGO GENÉTICO REESCRITO · CONTENCIÓN COMPROMETIDA
                </div>
              </div>
              {source !== "live" && (
                <button onClick={resetDemo} data-testid="gen0-reset-btn"
                  title="Reiniciar simulación"
                  className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[10px] font-black tracking-widest text-white/60 hover:bg-white/[0.08] transition">
                  <RotateCcw size={11} /> REINICIAR
                </button>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Inline styles for glitch effect */}
      <style>{`
        .gen0-glitch { position: relative; }
        .gen0-glitch::before,
        .gen0-glitch::after {
          content: attr(data-text);
          position: absolute; top: 0; left: 0;
          width: 100%; height: 100%;
          pointer-events: none;
        }
        .gen0-glitch::before { color: #EF4444; transform: translate(-1.2px, 0);
          clip-path: polygon(0 20%, 100% 20%, 100% 45%, 0 45%);
          animation: gen0-glitch-a 3.4s infinite steps(1); mix-blend-mode: screen; }
        .gen0-glitch::after  { color: #22D3EE; transform: translate(1.2px, 0);
          clip-path: polygon(0 60%, 100% 60%, 100% 80%, 0 80%);
          animation: gen0-glitch-b 3.9s infinite steps(1); mix-blend-mode: screen; }
        @keyframes gen0-glitch-a {
          0%, 92%, 100% { transform: translate(-1.2px, 0); opacity: 0.6; }
          93% { transform: translate(-2.5px, -1px); opacity: 0.95; }
          95% { transform: translate(0.5px, 1px);  opacity: 0.7; }
          97% { transform: translate(-1.8px, 0);   opacity: 0.9; }
        }
        @keyframes gen0-glitch-b {
          0%, 90%, 100% { transform: translate(1.2px, 0); opacity: 0.55; }
          91% { transform: translate(2px, 0.5px);   opacity: 0.85; }
          94% { transform: translate(-0.6px, -1px); opacity: 0.7; }
          96% { transform: translate(1.5px, 0);     opacity: 0.9; }
        }
      `}</style>
    </motion.section>
  );
}

function StatusChip({ status, source }) {
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1"
      style={{ borderColor: status.color + "55", background: status.color + "14" }}
      data-testid="gen0-status-chip"
    >
      <motion.span
        className="h-1.5 w-1.5 rounded-full"
        animate={{ opacity: [1, 0.35, 1] }}
        transition={{ duration: status.intensity >= 3 ? 0.7 : 1.6, repeat: Infinity }}
        style={{ background: status.color, boxShadow: `0 0 8px ${status.color}` }}
      />
      <span className="text-[9px] font-black tracking-[0.3em]" style={{ color: status.color }}>
        {source === "live" ? "LIVE FEED" : "DEMO FEED"}
      </span>
    </div>
  );
}

function MetricPill({ icon, label, value, tone }) {
  return (
    <div className="rounded-lg border border-white/[0.05] bg-black/40 px-3 py-2 flex items-center gap-2">
      <span style={{ color: tone }}>{icon}</span>
      <div className="min-w-0">
        <div className="text-[8px] font-black tracking-[0.32em] text-white/40 uppercase">{label}</div>
        <div className="text-[11px] font-black tabular-nums truncate" style={{ color: tone }}>{value}</div>
      </div>
    </div>
  );
}

function rateFor(p) {
  if (p <= 0)   return "0.00 μ/s";
  if (p < 25)   return `${(0.05 + p * 0.005).toFixed(2)} μ/s`;
  if (p < 50)   return `${(0.20 + (p - 25) * 0.010).toFixed(2)} μ/s`;
  if (p < 75)   return `${(0.60 + (p - 50) * 0.020).toFixed(2)} μ/s`;
  if (p < 100)  return `${(1.20 + (p - 75) * 0.040).toFixed(2)} μ/s`;
  return "∞ μ/s";
}
function containmentFor(intensity) {
  return ["INTACTO", "MONITOREO", "ALERTA", "CRÍTICO", "PERDIDO"][intensity] || "INTACTO";
}

export default Gen0VirusPanel;
