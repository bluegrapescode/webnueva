import React, { useEffect, useState } from "react";
import { motion, useMotionValue, animate as animateMV } from "framer-motion";
import { Skull, Flame, Users, Clock, MapPin, Radio, User, Activity, ShieldAlert } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { fmtNum, fmtCountdown, dinoGlyph } from "@/lib/bountyMeta";

const RED = "#E11D2A";
const GOLD = "#F0B429";
const MEAT = "#22C55E";

function useTick() {
  const [, s] = useState(0);
  useEffect(() => { const t = setInterval(() => s((n) => n + 1), 1000); return () => clearInterval(t); }, []);
}

function CountUp({ value, className, style }) {
  const mv = useMotionValue(0);
  const [t, setT] = useState("0");
  useEffect(() => {
    const c = animateMV(mv, Number(value || 0), { duration: 0.9, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => setT(fmtNum(Math.round(v))) });
    return () => c.stop();
  }, [value]);
  return <span className={className} style={style}>{t}</span>;
}

// Etiqueta de rango de amenaza según el valor del bounty.
function threatOf(prime) {
  if (prime >= 200000) return { label: "AMENAZA EXTREMA", color: RED };
  if (prime >= 80000) return { label: "AMENAZA ALTA", color: RED };
  if (prime >= 30000) return { label: "AMENAZA MEDIA", color: GOLD };
  return { label: "AMENAZA BAJA", color: "#94A3B8" };
}

function StatChip({ icon, label, value, valueColor = "#fff", testid }) {
  return (
    <div className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 bg-white/[0.03] border border-white/8" data-testid={testid}>
      <span className="shrink-0">{icon}</span>
      <div className="min-w-0 leading-tight">
        <p className="text-sm font-bold font-mono truncate" style={{ color: valueColor }}>{value}</p>
        <p className="text-[9px] uppercase tracking-widest text-slate-500 truncate">{label}</p>
      </div>
    </div>
  );
}

// Tarjeta WANTED rica (contrato o auto-bounty). rank = posición en el tablón (0 = #1).
export function BountyCard({ bounty: b, variant = "full", rank }) {
  useTick();
  if (!b) {
    return (
      <div className="w-full rounded-2xl border border-white/10 bg-[#0b0b0d] p-10 text-center" data-testid="bounty-card-empty">
        <Skull className="w-9 h-9 mx-auto text-white/20 mb-3" />
        <p className="text-sm text-white/50">No hay bounties activos ahora mismo.</p>
        <p className="text-xs text-white/30 mt-1">Sé el primero: elige un objetivo o pon precio a tu cabeza.</p>
      </div>
    );
  }
  const isSelf = b.type === "self";
  const hero = variant === "hero";
  const accent = isSelf ? GOLD : RED;
  const prime = isSelf ? 0 : (b.reward ? b.reward.primeMeat : 0);
  const amber = isSelf ? (b.killerAmber || 0) : (b.reward ? b.reward.amberium : 0);
  const threat = isSelf ? { label: "OBJETIVO DORADO", color: GOLD } : threatOf(prime);
  const isTop = rank === 0;

  // Progreso de supervivencia (self).
  const survPct = isSelf && b.startedAt && b.endsAt
    ? Math.min(100, Math.max(0, ((Date.now() - b.startedAt) / (b.endsAt - b.startedAt)) * 100)) : 0;

  return (
    <motion.div
      className={`relative flex flex-col overflow-hidden rounded-2xl border ${hero ? "h-full" : ""}`}
      style={{
        background: isSelf ? "linear-gradient(160deg, #1c1206 0%, #101018 55%, #0a0a0c 100%)" : "linear-gradient(160deg, #1c0709 0%, #101018 55%, #0a0a0c 100%)",
        borderColor: isSelf ? "rgba(240,180,41,0.35)" : "rgba(225,29,42,0.35)",
      }}
      whileHover={{ y: -4 }}
      animate={{ boxShadow: [
        `0 10px 30px rgba(0,0,0,0.6), 0 0 26px -18px ${accent}`,
        `0 10px 30px rgba(0,0,0,0.6), 0 0 40px -12px ${accent}`,
        `0 10px 30px rgba(0,0,0,0.6), 0 0 26px -18px ${accent}`,
      ] }}
      transition={{ boxShadow: { duration: 2.8, repeat: Infinity, ease: "easeInOut" }, y: { duration: 0.2 } }}
      data-testid="bounty-card"
    >
      <div className="absolute inset-0 pointer-events-none opacity-[0.08]" style={{ backgroundImage: `radial-gradient(${accent} 1px, transparent 1px)`, backgroundSize: "16px 16px" }} />
      <div className="absolute inset-0 pointer-events-none bounty-scan opacity-25" />

      {/* Header: tipo + rango + bounty id */}
      <div className="relative flex items-center justify-between gap-2 px-4 pt-3.5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
          style={{ background: isSelf ? "rgba(240,180,41,0.12)" : "rgba(225,29,42,0.12)", color: accent, border: `1px solid ${accent}55` }}>
          {isSelf ? <Flame className="w-3 h-3" /> : <Skull className="w-3 h-3" />}
          {isSelf ? "Autodesafío" : "Contrato"}
        </span>
        {isTop && (
          <motion.span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded"
            style={{ background: "rgba(225,29,42,0.18)", color: "#FF4D4D", border: "1px solid rgba(225,29,42,0.5)" }}
            animate={{ opacity: [1, 0.6, 1] }} transition={{ duration: 1.6, repeat: Infinity }} data-testid="bounty-most-wanted">
            <Flame className="w-3 h-3" /> #1 MÁS BUSCADO
          </motion.span>
        )}
      </div>

      {/* Avatar + identidad */}
      <div className="relative px-4 pt-2 flex items-start gap-3.5">
        <div className="relative shrink-0">
          <motion.span className="absolute inset-0 rounded-full" style={{ border: `1px solid ${accent}` }}
            animate={{ scale: [1, 1.3], opacity: [0.5, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }} />
          <div className={`${hero ? "w-24 h-24" : "w-16 h-16"} rounded-full flex items-center justify-center`}
            style={{ background: `radial-gradient(circle at 50% 35%, ${accent}2e, transparent 70%)`, border: `1px solid ${accent}55` }}>
            <span className={hero ? "text-5xl" : "text-3xl"}>{dinoGlyph(b.slug)}</span>
          </div>
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <h3 className={`${hero ? "text-2xl md:text-3xl" : "text-lg"} font-black uppercase tracking-tight text-white leading-none truncate`} data-testid="bounty-target-name">{b.targetName}</h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-300 truncate" data-testid="bounty-dino">{b.dinosaur}</span>
            <span className="text-slate-600">•</span>
            <span className="text-[11px] text-slate-400">Adulto</span>
          </div>
          <div className="inline-flex items-center gap-1 mt-2 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ color: threat.color, background: `${threat.color}18` }} data-testid="bounty-threat">
            <ShieldAlert className="w-3 h-3" /> {threat.label}
          </div>
        </div>
      </div>

      {/* WANTED stamp banner */}
      <div className="relative px-4 mt-3">
        <div className="flex items-center gap-2">
          <span className="h-px flex-1" style={{ background: `linear-gradient(90deg, transparent, ${accent}88)` }} />
          <span className="text-[10px] font-black uppercase tracking-[0.25em] px-2 py-0.5 rounded" style={{ color: accent, border: `1px solid ${accent}66`, background: `${accent}12` }}>
            {isSelf ? "Vivo o Muerto" : "Wanted — Dead or Alive"}
          </span>
          <span className="h-px flex-1" style={{ background: `linear-gradient(90deg, ${accent}88, transparent)` }} />
        </div>
      </div>

      {/* Cuerpo de datos */}
      <div className="relative px-4 py-3.5 mt-1 flex-1">
        {isSelf ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <StatChip testid="bounty-self-accrued" icon={<img src={MEDIA.coinNormal} alt="" className="w-4 h-4" />} label="Acumulado" valueColor={GOLD} value={<CountUp value={b.accrued || 0} />} />
              <StatChip testid="bounty-self-permin" icon={<Activity className="w-3.5 h-3.5" style={{ color: MEAT }} />} label="Por minuto" valueColor="#fff" value={`+${fmtNum(b.primePerMin)}`} />
              <StatChip testid="bounty-self-killeramber" icon={<img src={MEDIA.coinVip} alt="" className="w-4 h-4" />} label="Al cazador" valueColor={GOLD} value={fmtNum(amber)} />
              <StatChip testid="bounty-self-timer" icon={<Clock className="w-3.5 h-3.5 text-slate-300" />} label="Restante" valueColor="#fff" value={fmtCountdown(b.endsAt)} />
            </div>
            <div className="mt-3">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400 mb-1">
                <span>Supervivencia</span><span className="font-mono">{Math.round(survPct)}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                <motion.div className="h-full rounded-full" style={{ background: `linear-gradient(90deg, ${GOLD}, #FF9F1C)` }} animate={{ width: `${survPct}%` }} transition={{ duration: 0.6 }} />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400" data-testid="bounty-telemetry">
              <Radio className="w-3 h-3 text-red-500 animate-pulse" /> Coordenadas transmitidas en vivo
            </div>
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <StatChip testid="bounty-reward-meat" icon={<img src={MEDIA.coinNormal} alt="" className="w-4 h-4" />} label="Prime Meat" valueColor={MEAT} value={<CountUp value={prime} />} />
              <StatChip testid="bounty-reward-amber" icon={<img src={MEDIA.coinVip} alt="" className="w-4 h-4" />} label="Amberium" valueColor={GOLD} value={fmtNum(amber)} />
              <StatChip testid="bounty-count" icon={<Users className="w-3.5 h-3.5 text-slate-300" />} label="Contratistas" valueColor="#fff" value={`${b.count || 1}`} />
              <StatChip testid="bounty-expires" icon={<Clock className="w-3.5 h-3.5 text-slate-300" />} label="Expira en" valueColor="#fff" value={fmtCountdown(b.expiresAt)} />
            </div>
            <div className="mt-3 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400">
              <span className="inline-flex items-center gap-1 truncate" data-testid="bounty-issuer"><User className="w-3 h-3" /> por {b.placerName || "Anónimo"}</span>
              <span className="inline-flex items-center gap-1"><MapPin className="w-3 h-3" /> Isla Nublar</span>
            </div>
          </>
        )}
      </div>

      {/* Recompensa total destacada */}
      <div className="relative px-4 pb-4">
        <div className="flex items-center justify-between rounded-xl px-3.5 py-2.5" style={{ background: `${accent}10`, border: `1px solid ${accent}33` }}>
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{isSelf ? "Recompensa al cazador" : "Recompensa total"}</span>
          <span className="text-lg font-black font-mono flex items-center gap-2" style={{ color: accent }}>
            {isSelf ? (<><img src={MEDIA.coinVip} alt="" className="w-4 h-4" />{fmtNum(amber)}</>)
              : (<><span style={{ color: MEAT }} className="flex items-center gap-1"><img src={MEDIA.coinNormal} alt="" className="w-4 h-4" />{fmtNum(prime)}</span>{amber > 0 && <span style={{ color: GOLD }} className="flex items-center gap-1"><img src={MEDIA.coinVip} alt="" className="w-4 h-4" />{fmtNum(amber)}</span>}</>)}
          </span>
        </div>
        <p className="mt-2 text-center text-[9px] uppercase tracking-[0.2em] text-slate-600" data-testid="bounty-id">Bounty ID • #{b.bountyId || b.targetId}</p>
      </div>
    </motion.div>
  );
}

export default BountyCard;
