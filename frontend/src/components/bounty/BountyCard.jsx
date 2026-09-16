import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence, useMotionValue, animate as animateMV } from "framer-motion";
import { Skull, Crosshair, WifiOff } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { fmtNum, fmtCountdown, dinoGlyph } from "@/lib/bountyMeta";
import { useSound } from "@/context/SoundContext";

const C = { danger: "#E11D2A", amber: "#F0B429" };

function useTick() {
  const [, set] = useState(0);
  useEffect(() => {
    const t = setInterval(() => set((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
}

// Cuenta ascendente animada para las recompensas.
function CountUp({ value, className, style }) {
  const mv = useMotionValue(0);
  const [txt, setTxt] = useState("0");
  useEffect(() => {
    const controls = animateMV(mv, Number(value || 0), {
      duration: 1.1, ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setTxt(fmtNum(Math.round(v))),
    });
    return () => controls.stop();
  }, [value]);
  return <span className={className} style={style}>{txt}</span>;
}

function RewardStat({ icon, value, label, color, testid, animateNum }) {
  return (
    <motion.div
      className="flex flex-col items-center px-2" data-testid={testid}
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15, duration: 0.4 }}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-base leading-none">{icon}</span>
        {animateNum ? (
          <CountUp value={value} className="text-lg sm:text-xl font-extrabold tracking-tight" style={{ color }} />
        ) : (
          <span className="text-lg sm:text-xl font-extrabold tracking-tight" style={{ color }}>{fmtNum(value)}</span>
        )}
      </div>
      <span className="text-[10px] uppercase tracking-[0.18em] text-white/45 mt-1">{label}</span>
    </motion.div>
  );
}

// Secuencia cinemática al llegar bounty:new — mira que se cierra -> ☠ -> nombre -> ACTIVE
function IntroSequence({ name, onDone }) {
  const [step, setStep] = useState(0);
  const { play } = useSound();
  useEffect(() => {
    play("bountyAlert");
    const timers = [
      setTimeout(() => { setStep(1); play("bountyLock"); }, 550),
      setTimeout(() => { setStep(2); play("bountyLock"); }, 1050),
      setTimeout(() => onDone && onDone(), 1950),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <motion.div
      className="absolute inset-0 z-20 flex flex-col items-center justify-center overflow-hidden bg-black/88 backdrop-blur-sm"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      data-testid="bounty-intro"
    >
      {/* destello rojo */}
      <motion.div className="absolute inset-0 pointer-events-none"
        style={{ background: "radial-gradient(circle at 50% 45%, rgba(225,29,42,0.35), transparent 60%)" }}
        initial={{ opacity: 0.8 }} animate={{ opacity: [0.8, 0.15, 0.4] }} transition={{ duration: 1.9 }} />
      <div className="bounty-scan absolute inset-0 pointer-events-none opacity-60" />
      {/* mira que se cierra */}
      <motion.div className="absolute" initial={{ scale: 2.4, opacity: 0, rotate: -25 }}
        animate={{ scale: 1, opacity: step === 0 ? 0.9 : 0, rotate: 0 }} transition={{ duration: 0.55 }}>
        <Crosshair className="w-40 h-40" style={{ color: C.danger }} strokeWidth={0.8} />
      </motion.div>
      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.p key="s0" initial={{ opacity: 0, letterSpacing: "0.7em" }}
            animate={{ opacity: 1, letterSpacing: "0.3em" }} exit={{ opacity: 0 }}
            className="relative text-sm sm:text-base font-bold uppercase tracking-[0.3em]" style={{ color: C.danger }}>
            Target Acquired
          </motion.p>
        )}
        {step === 1 && (
          <motion.div key="s1" initial={{ scale: 0.3, opacity: 0, rotate: -12 }}
            animate={{ scale: [0.3, 1.25, 1], opacity: 1, rotate: 0 }} exit={{ opacity: 0, scale: 1.5 }}
            transition={{ duration: 0.45 }}>
            <Skull className="w-20 h-20" style={{ color: C.danger, filter: "drop-shadow(0 0 18px rgba(225,29,42,0.8))" }} strokeWidth={1.4} />
          </motion.div>
        )}
        {step === 2 && (
          <motion.div key="s2" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="relative text-center">
            <motion.p initial={{ scale: 1.3 }} animate={{ scale: 1 }}
              className="text-2xl sm:text-3xl font-black text-white truncate max-w-[80vw] px-4">{name}</motion.p>
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0.5, 1] }} transition={{ delay: 0.15, duration: 0.6 }}
              className="mt-2 text-xs font-bold uppercase tracking-[0.35em]" style={{ color: C.danger }}>
              Bounty Active
            </motion.p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function BountyCard({ snapshot, lastEvent }) {
  useTick();
  const [intro, setIntro] = useState(null);
  const seenId = useRef(null);

  useEffect(() => {
    if (lastEvent && lastEvent.event === "bounty:new" && lastEvent.data && lastEvent.data.bountyId) {
      if (seenId.current !== lastEvent.data.bountyId) {
        seenId.current = lastEvent.data.bountyId;
        setIntro({ name: lastEvent.data.targetName });
      }
    }
  }, [lastEvent]);

  const cfg = snapshot && snapshot.config;
  const b = snapshot && snapshot.bounty;
  const paused = snapshot && snapshot.paused;
  const completed = b && b.status === "completed";
  const suspended = b && b.status === "suspended";
  const active = b && b.status === "active";

  const rewards = (b && b.rewards) || (cfg && { primeMeat: cfg.prime_meat, experience: cfg.experience, amberium: cfg.amberium }) || { primeMeat: 0, experience: 0, amberium: 0 };
  const nextMs = (b && b.nextAt ? Date.parse(b.nextAt) : (snapshot && snapshot.nextAt ? Date.parse(snapshot.nextAt) : 0)) || 0;

  return (
    <div className="relative w-full max-w-[440px] mx-auto" data-testid="bounty-card">
      <motion.div
        className="relative overflow-hidden rounded-2xl border"
        style={{
          background: "linear-gradient(180deg, #17070a 0%, #0b0b0d 55%, #08080a 100%)",
          borderColor: active || suspended ? "rgba(225,29,42,0.45)" : "rgba(255,255,255,0.10)",
        }}
        animate={active ? {
          boxShadow: [
            "0 0 0 1px rgba(225,29,42,0.15), 0 0 40px -20px rgba(225,29,42,0.5)",
            "0 0 0 1px rgba(225,29,42,0.35), 0 0 70px -14px rgba(225,29,42,0.75)",
            "0 0 0 1px rgba(225,29,42,0.15), 0 0 40px -20px rgba(225,29,42,0.5)",
          ],
        } : { boxShadow: "0 20px 50px -30px rgba(0,0,0,0.9)" }}
        transition={active ? { duration: 2.6, repeat: Infinity, ease: "easeInOut" } : { duration: 0.4 }}
      >
        <div className="absolute inset-0 pointer-events-none bounty-grain opacity-[0.06]" />
        {active && <div className="absolute inset-0 pointer-events-none bounty-scan opacity-40" />}

        {/* header */}
        <div className="relative flex items-center justify-between px-5 pt-4">
          <div className="flex items-center gap-2">
            <Skull className="w-4 h-4" style={{ color: C.danger }} />
            <span className="text-[11px] font-bold uppercase tracking-[0.3em] text-white/80">Global Bounty</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${active ? "animate-pulse" : ""}`}
              style={{ background: active ? C.danger : suspended ? C.amber : "#4b4b52" }} />
            <span className="text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: active ? C.danger : suspended ? C.amber : "#8A8A93" }}
              data-testid="bounty-status">
              {paused ? "Pausado" : completed ? "Completado" : suspended ? "Desconectado" : active ? "Active" : "Buscando"}
            </span>
          </div>
        </div>

        <div className="relative px-5 pb-5 pt-3">
          <AnimatePresence mode="wait">
          {(active || suspended || completed) && b ? (
            <motion.div key={b.status + b.bountyId} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {/* avatar / glyph con anillo pulsante */}
              <div className="relative mx-auto my-3 flex items-center justify-center h-32">
                {(active || suspended) && (
                  <motion.span className="absolute rounded-full"
                    style={{ width: 112, height: 112, border: `1px solid ${suspended ? C.amber : C.danger}` }}
                    animate={{ scale: [1, 1.35], opacity: [0.5, 0] }}
                    transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }} />
                )}
                <motion.div
                  className="relative w-28 h-28 rounded-full flex items-center justify-center"
                  style={{
                    background: "radial-gradient(circle at 50% 35%, rgba(225,29,42,0.18), rgba(0,0,0,0) 70%)",
                    border: "1px solid rgba(225,29,42,0.30)",
                  }}
                  initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 200, damping: 16 }}
                >
                  <motion.span className="text-6xl"
                    style={{ filter: completed ? "grayscale(1) opacity(0.5)" : "none" }}
                    animate={active ? { scale: [1, 1.06, 1] } : {}}
                    transition={{ duration: 2.4, repeat: Infinity }}>
                    {dinoGlyph(b.slug)}
                  </motion.span>
                  {suspended && (
                    <div className="absolute inset-0 rounded-full flex items-center justify-center bg-black/55">
                      <WifiOff className="w-8 h-8" style={{ color: C.amber }} />
                    </div>
                  )}
                  {/* sello ELIMINADO */}
                  {completed && (
                    <motion.div className="absolute -right-6 -top-2 px-2 py-0.5 rounded border-2 select-none"
                      style={{ borderColor: C.danger, color: C.danger, transform: "rotate(-14deg)" }}
                      initial={{ scale: 2.2, opacity: 0, rotate: 20 }} animate={{ scale: 1, opacity: 1, rotate: -14 }}
                      transition={{ type: "spring", stiffness: 220, damping: 12, delay: 0.1 }}>
                      <span className="text-[11px] font-black uppercase tracking-widest">Eliminado</span>
                    </motion.div>
                  )}
                </motion.div>
              </div>

              <div className="text-center">
                <h3 className="text-2xl sm:text-3xl font-black text-white leading-none truncate" data-testid="bounty-target-name">
                  {completed ? b.killerName : b.targetName}
                </h3>
                {completed ? (
                  <p className="mt-2 text-[11px] uppercase tracking-[0.25em] text-white/50">
                    eliminó a <span className="text-white/80 font-semibold">{b.targetName}</span>
                  </p>
                ) : (
                  <p className="mt-1.5 text-[11px] uppercase tracking-[0.28em] text-white/50" data-testid="bounty-dino">
                    {b.dinosaur}
                  </p>
                )}
              </div>

              <div className="my-4 flex items-center justify-center gap-3">
                <span className="h-px w-10" style={{ background: "linear-gradient(90deg, transparent, rgba(225,29,42,0.6))" }} />
                <span className="text-[11px] font-bold uppercase tracking-[0.3em]" style={{ color: completed ? C.amber : C.danger }}>
                  {completed ? "Reward Claimed" : suspended ? "Objetivo Desconectado" : "Wanted — Dead or Alive"}
                </span>
                <span className="h-px w-10" style={{ background: "linear-gradient(90deg, rgba(225,29,42,0.6), transparent)" }} />
              </div>

              {suspended && (
                <p className="text-center text-xs text-amber-300/80 mb-3" data-testid="bounty-suspend-timer">
                  Se cancela en {fmtCountdown(b.suspendUntil)} si no regresa
                </p>
              )}

              <div className="flex items-center justify-center divide-x divide-white/10 py-3 rounded-xl"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                <RewardStat icon="🥩" value={rewards.primeMeat} label="Prime Meat" color="#fff" testid="bounty-reward-meat" animateNum={completed} />
                <RewardStat icon="✦" value={rewards.experience} label="EXP" color="#fff" testid="bounty-reward-exp" animateNum={completed} />
                <RewardStat icon={<img src={MEDIA.coinVip} alt="" className="w-4 h-4 inline-block" />} value={rewards.amberium} label="Amberium" color={C.amber} testid="bounty-reward-amber" animateNum={completed} />
              </div>

              {completed && nextMs > 0 && (
                <div className="mt-4 text-center" data-testid="bounty-next-timer">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-white/40">Next Target</p>
                  <p className="text-xl font-bold text-white tabular-nums mt-1">{fmtCountdown(nextMs)}</p>
                </div>
              )}

              <p className="mt-4 text-center text-[10px] uppercase tracking-[0.25em] text-white/30" data-testid="bounty-id">
                Bounty ID: #{b.bountyId}
              </p>
            </motion.div>
          ) : (
            <motion.div key="waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="py-10 flex flex-col items-center text-center">
              <motion.div animate={{ rotate: [0, 90, 180, 270, 360] }} transition={{ duration: 8, repeat: Infinity, ease: "linear" }}>
                <Crosshair className="w-10 h-10 text-white/25 mb-4" />
              </motion.div>
              <p className="text-sm font-semibold text-white/70">
                {paused ? "Sistema de bounties en pausa" : "Buscando el próximo objetivo…"}
              </p>
              {!paused && nextMs > 0 && (
                <div className="mt-4" data-testid="bounty-next-timer">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-white/40">Nuevo objetivo en</p>
                  <p className="text-2xl font-bold text-white tabular-nums mt-1">{fmtCountdown(nextMs)}</p>
                </div>
              )}
            </motion.div>
          )}
          </AnimatePresence>
        </div>
      </motion.div>

      <AnimatePresence>
        {intro && <IntroSequence name={intro.name} onDone={() => setIntro(null)} />}
      </AnimatePresence>
    </div>
  );
}

export default BountyCard;
