import React from "react";
import { motion } from "framer-motion";
import { Lock, Check } from "lucide-react";

/**
 * Horizontal dinosaur growth-stage milestones with visual state per stage.
 * Data comes from dashboard.milestones = { stages: [...], next: {...} }
 * Stages: Juvie → Sub-Adult → Adult → Elder → Apex
 */
export function MilestoneTimeline({ milestones, totalRefs = 0 }) {
  const stages = milestones?.stages || [];
  const next   = milestones?.next;
  if (!stages.length) return null;

  return (
    <div
      className="relative overflow-hidden rounded-3xl border border-white/[0.05]"
      data-testid="milestone-timeline"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400/40 to-transparent" />
      <div className="pointer-events-none absolute -top-24 -right-16 h-56 w-56 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(139,92,246,0.6), transparent 65%)" }} />

      <div className="relative p-6 sm:p-7">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="text-[10px] font-black tracking-[0.35em] text-purple-400/80">EVOLUCIÓN · ETAPAS</div>
            <h3 className="mt-1 text-xl sm:text-2xl font-black tracking-tight text-white">
              Tu Crecimiento como Creator
            </h3>
          </div>
          {next && (
            <div className="text-right">
              <div className="text-[10px] font-black tracking-[0.32em] text-white/40">SIGUIENTE ETAPA</div>
              <div className="mt-0.5 text-sm">
                <span className="mr-1.5">{next.medal}</span>
                <span className="font-black" style={{ color: next.color }}>{next.title}</span>
                <span className="mx-2 text-white/25">·</span>
                <span className="text-white/60 tabular-nums">
                  faltan <b className="text-white">{next.remaining}</b> refs
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Timeline */}
        <div className="relative mt-6">
          {/* Base line */}
          <div className="absolute left-4 right-4 top-1/2 -translate-y-1/2 h-0.5 bg-white/[0.06] rounded-full" />
          {/* Progress line (fills up to the most advanced reached stage) */}
          {(() => {
            const idx = stages.findIndex((s) => s.state === "current");
            const done = idx >= 0 ? idx : stages.filter((s) => s.state === "reached").length - 1;
            if (done < 0) return null;
            const pct = ((done + 1) / stages.length) * 100;
            return (
              <motion.div
                className="absolute left-4 top-1/2 -translate-y-1/2 h-0.5 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `calc(${pct}% - 2rem)` }}
                transition={{ duration: 0.8 }}
                style={{ background: "linear-gradient(90deg, #7CA842, #22C55E, #F59E0B, #A78BFA, #D4AF37)",
                         boxShadow: "0 0 14px rgba(167,139,250,0.5)" }}
              />
            );
          })()}

          <div className="relative grid grid-cols-5 gap-3">
            {stages.map((s, i) => {
              const isReached  = s.state === "reached" || s.state === "current";
              const isCurrent  = s.state === "current";
              return (
                <motion.div
                  key={s.key}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.06 * i, duration: 0.4 }}
                  className="flex flex-col items-center text-center"
                  data-testid={`ms-stage-${s.key}`}
                >
                  <div
                    className="relative flex h-14 w-14 sm:h-16 sm:w-16 items-center justify-center rounded-full border-2"
                    style={{
                      borderColor: isReached ? s.color : "rgba(255,255,255,0.10)",
                      background: isReached
                        ? `linear-gradient(135deg, ${s.color}33, rgba(0,0,0,0.7))`
                        : "rgba(0,0,0,0.4)",
                      boxShadow: isCurrent ? `0 0 24px ${s.color}80` : "none",
                    }}
                  >
                    <span className="text-2xl sm:text-3xl grayscale-0" style={{ filter: isReached ? "none" : "grayscale(1) opacity(0.4)" }}>
                      {s.medal}
                    </span>
                    {isReached && (
                      <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full text-white"
                        style={{ background: s.color }}>
                        <Check size={11} strokeWidth={3} />
                      </span>
                    )}
                    {!isReached && s.state === "locked" && (
                      <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 border border-white/10 text-white/50">
                        <Lock size={9} />
                      </span>
                    )}
                    {isCurrent && (
                      <motion.div
                        className="absolute inset-[-6px] rounded-full pointer-events-none"
                        animate={{ scale: [1, 1.15, 1], opacity: [0.5, 0.1, 0.5] }}
                        transition={{ duration: 2, repeat: Infinity }}
                        style={{ border: `2px solid ${s.color}` }}
                      />
                    )}
                  </div>
                  <div className="mt-2 text-[10px] font-black tracking-widest uppercase"
                    style={{ color: isReached ? s.color : "rgba(255,255,255,0.35)" }}>
                    {s.title}
                  </div>
                  <div className="mt-0.5 text-[10px] tabular-nums text-white/40">
                    {s.threshold} refs
                  </div>
                  <div className="text-[9px] font-black tabular-nums" style={{ color: isReached ? "#22C55E" : "rgba(255,255,255,0.25)" }}>
                    +{Math.round(s.bonus / 1000)}K PM
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Bottom summary bar */}
        <div className="mt-5 flex items-center justify-between gap-3 flex-wrap text-[11px]">
          <div className="text-white/50">
            Total referidos validados: <b className="text-white tabular-nums">{totalRefs.toLocaleString()}</b>
          </div>
          <div className="text-white/40">
            Cada etapa da bono automático + título permanente
          </div>
        </div>
      </div>
    </div>
  );
}
