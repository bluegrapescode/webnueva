import React from "react";
import { motion } from "framer-motion";
import { Users, Flame, Trophy } from "lucide-react";
import { AnimatedNumber } from "./AnimatedNumber";

function StatCard({ icon, label, value, accent, delay = 0, testid, prefix = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.45, ease: [0.2, 0.9, 0.3, 1] }}
      whileHover={{ y: -2 }}
      className="group relative overflow-hidden rounded-2xl p-5 sm:p-6 transition-colors"
      style={{ background: "#161225", border: "1px solid rgba(255,255,255,0.05)" }}
      data-testid={testid}
    >
      <div className="pointer-events-none absolute -top-16 -right-16 h-32 w-32 rounded-full opacity-0 group-hover:opacity-40 transition-opacity duration-500"
        style={{ background: `radial-gradient(circle, ${accent}, transparent 60%)` }} />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: `linear-gradient(90deg, transparent, ${accent}, transparent)` }} />

      <div className="relative flex items-center gap-2">
        <span className="opacity-80" style={{ color: accent }}>{icon}</span>
        <span className="text-[9px] font-black tracking-[0.32em] text-white/40">{label}</span>
      </div>
      <div className="relative mt-3 text-4xl sm:text-5xl font-black tabular-nums leading-none tracking-tight" style={{ color: accent }}>
        <AnimatedNumber value={Number(value || 0)} prefix={prefix} />
      </div>
    </motion.div>
  );
}

export function StatsGrid({ creator }) {
  const total = creator?.total_referrals || 0;
  const pm    = creator?.total_prime_meat_earned || 0;
  const month = creator?.monthly_referrals || 0;
  const rank  = creator?.rank ?? null;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <StatCard icon={<Users size={13} />}  label="REFERIDOS TOTALES"  value={total} accent="#FFFFFF" delay={0.05} testid="stat-total" />
      <StatCard icon={<Flame size={13} />}  label="ESTE MES"           value={month} accent="#A78BFA" delay={0.12} testid="stat-month" />
      <StatCard icon={<span>🥩</span>}      label="PRIME MEAT GANADA"  value={pm}    accent="#22C55E" delay={0.19} testid="stat-pm" />
      <StatCard icon={<Trophy size={13} />} label="RANK GLOBAL"        value={rank ?? 0} accent="#EC4899" delay={0.26} testid="stat-rank" prefix={rank ? "#" : ""} />
    </div>
  );
}
