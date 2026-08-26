import React, { memo } from "react";
import { motion } from "framer-motion";
import { Crown } from "lucide-react";

const PODIUM_STYLE = {
  1: {
    color: "#D4AF37",
    glow: "rgba(212,175,55,0.55)",
    height: "h-[130px] sm:h-[190px]",
    order: "order-2",
    scale: "sm:scale-105",
    label: "CAMPEÓN",
  },
  2: {
    color: "#C0C6D0",
    glow: "rgba(192,198,208,0.5)",
    height: "h-[100px] sm:h-[155px]",
    order: "order-1",
    scale: "",
    label: "SEGUNDO",
  },
  3: {
    color: "#CD7F32",
    glow: "rgba(205,127,50,0.5)",
    height: "h-[86px] sm:h-[135px]",
    order: "order-3",
    scale: "",
    label: "TERCERO",
  },
};

function Avatar({ src, name, color, size = "lg", isChampion }) {
  const sz = size === "lg"
    ? "h-14 w-14 sm:h-20 sm:w-20 text-lg sm:text-2xl"
    : "h-11 w-11 sm:h-16 sm:w-16 text-sm sm:text-xl";
  return (
    <div className="relative">
      <motion.div
        className={`relative flex ${sz} items-center justify-center rounded-full border-2 font-black uppercase overflow-hidden`}
        style={{ borderColor: color, background: `linear-gradient(135deg, ${color}44, rgba(0,0,0,0.7))`, color }}
        animate={isChampion ? { boxShadow: [`0 0 20px ${color}88`, `0 0 40px ${color}`, `0 0 20px ${color}88`] } : {}}
        transition={isChampion ? { duration: 2.5, repeat: Infinity } : {}}
      >
        {src ? <img src={src} alt="" className="h-full w-full object-cover" onError={(e) => e.currentTarget.style.display = "none"} /> : (name || "?")[0]}
      </motion.div>
      {isChampion && (
        <motion.div
          initial={{ y: 0, opacity: 0, scale: 0.5 }}
          animate={{ y: -12, opacity: 1, scale: 1 }}
          transition={{ delay: 0.75, type: "spring", stiffness: 340, damping: 16 }}
          className="absolute -top-2 sm:-top-3 left-1/2 -translate-x-1/2 pointer-events-none"
        >
          <motion.div animate={{ y: [0, -3, 0], rotate: [-3, 3, -3] }} transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}>
            <Crown size={22} className="sm:hidden text-gold drop-shadow-[0_0_8px_rgba(212,175,55,0.9)]" fill="#D4AF37" />
            <Crown size={26} className="hidden sm:block text-gold drop-shadow-[0_0_10px_rgba(212,175,55,0.9)]" fill="#D4AF37" />
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}

function PodiumStand({ entry, rank, tab, currentUserId }) {
  const style = PODIUM_STYLE[rank];
  const isMe = entry && entry.user_id === currentUserId;
  // Stagger so 2 comes first, then 1 (winner), then 3 — classic reveal sequence.
  const delay = rank === 2 ? 0.05 : rank === 1 ? 0.22 : 0.42;
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.45, ease: [0.2, 0.9, 0.3, 1] }}
      className={`relative flex flex-col items-center flex-1 min-w-0 ${style.order} ${style.scale}`}
      data-testid={`lb-podium-${rank}`}
    >
      {/* Player card floating above the pillar */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: delay + 0.15, duration: 0.35, ease: [0.2, 0.9, 0.3, 1] }}
        className="relative flex flex-col items-center pb-1.5 sm:pb-2 w-full"
      >
        <Avatar src={entry?.avatar} name={entry?.name} color={style.color} size={rank === 1 ? "lg" : "md"} isChampion={rank === 1} />
        <div className="mt-1.5 sm:mt-2 text-center w-full px-1">
          <div className="font-black text-[11px] sm:text-sm tracking-tight truncate leading-tight" title={entry?.name}>
            {entry?.name || "---"}
            {isMe && <span className="ml-1 rounded-sm bg-gold px-1 py-0.5 text-[7px] font-black text-black align-middle">TÚ</span>}
          </div>
          <div className="text-[7px] sm:text-[9px] font-black tracking-widest text-white/50 whitespace-nowrap overflow-hidden text-ellipsis leading-tight">
            K/D {entry?.kd_ratio?.toFixed(2) ?? "—"} · {entry?.kills_all?.toLocaleString() ?? "—"}K
          </div>
        </div>
      </motion.div>

      {/* Pillar */}
      <motion.div
        initial={{ scaleY: 0.15, opacity: 0 }}
        animate={{ scaleY: 1, opacity: 1 }}
        transition={{ delay: delay + 0.04, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        style={{ transformOrigin: "bottom" }}
        className={`relative w-full max-w-[92px] sm:max-w-[120px] ${style.height} rounded-t-md flex flex-col items-center justify-start pt-1.5 sm:pt-3 overflow-hidden`}
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `linear-gradient(180deg, ${style.color}dd 0%, ${style.color}66 40%, rgba(0,0,0,0.6) 100%)`,
            boxShadow: `0 -8px 30px ${style.glow}, inset 0 -25px 55px rgba(0,0,0,0.6)`,
            border: `1px solid ${style.color}55`,
            borderRadius: "6px 6px 0 0",
          }}
        />
        {/* Diagonal shine */}
        <motion.div
          className="absolute inset-0 pointer-events-none rounded-t-md"
          animate={{ backgroundPositionX: ["-100%", "200%"] }}
          transition={{ duration: 5, repeat: Infinity, ease: "linear", delay: rank === 1 ? 1 : rank === 2 ? 0.8 : 1.2 }}
          style={{
            backgroundImage: "linear-gradient(120deg, transparent 25%, rgba(255,255,255,0.18) 50%, transparent 75%)",
            backgroundSize: "70% 100%",
            backgroundRepeat: "no-repeat",
          }}
        />
        <div className="relative text-[8px] sm:text-[10px] font-black tracking-[0.2em] whitespace-nowrap" style={{ color: style.color }}>
          {style.label}
        </div>
        <div
          className="relative mt-0.5 sm:mt-1 text-2xl sm:text-4xl font-black tabular-nums drop-shadow-[0_2px_8px_rgba(0,0,0,0.6)] leading-none"
          style={{ color: style.color }}
        >
          {rank}
        </div>
        <div className="relative mt-1 sm:mt-2 rounded-md bg-black/50 backdrop-blur px-1 sm:px-2 py-0.5 sm:py-1 border border-white/10 w-[86%]">
          <div className="text-[7px] sm:text-[9px] font-bold tracking-widest text-white/40 text-center leading-tight">{tab.tag.toUpperCase()}</div>
          <div className="text-[10px] sm:text-sm font-black tabular-nums text-white text-center whitespace-nowrap overflow-hidden text-ellipsis leading-tight">
            {entry?.display?.primary || "—"}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function PodiumBase({ podium, tab, currentUserId }) {
  if (!podium || podium.length === 0) {
    return (
      <div className="rounded-md border border-white/10 bg-black/30 p-8 text-center text-sm text-white/50">
        No hay campeones aún. Sé el primero.
      </div>
    );
  }
  return (
    <div className="relative overflow-hidden rounded-md border border-gold/25 bg-black/40 px-3 py-4 sm:px-6 sm:py-5" data-testid="lb-podium">
      {/* Ambient rays */}
      <div className="pointer-events-none absolute inset-0 opacity-40" style={{
        background: "radial-gradient(ellipse 60% 100% at 50% 100%, rgba(212,175,55,0.25), transparent 70%)"
      }} />
      <div className="relative flex flex-row items-end justify-center gap-2 sm:gap-4 max-w-2xl mx-auto">
        {[2, 1, 3].map((r) => {
          const entry = podium[r - 1];
          if (!entry) return <div key={r} className="flex-1" />;
          return <PodiumStand key={entry.user_id} entry={entry} rank={r} tab={tab} currentUserId={currentUserId} />;
        })}
      </div>
    </div>
  );
}

export const Podium = memo(PodiumBase);
