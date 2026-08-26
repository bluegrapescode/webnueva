import React, { memo } from "react";
import { motion } from "framer-motion";
import { Skull } from "lucide-react";

function Avatar({ src, name, size = 36 }) {
  return (
    <div
      className="flex items-center justify-center rounded-full border border-white/20 bg-black/50 font-black uppercase overflow-hidden shrink-0"
      style={{ height: size, width: size, fontSize: size * 0.4 }}
    >
      {src ? <img src={src} alt="" className="h-full w-full object-cover" onError={(e) => e.currentTarget.style.display="none"} /> : (name || "?")[0]}
    </div>
  );
}

function RankBadge({ rank }) {
  // Ranks 4-10 have a subtle amber tint; 11-30 are neutral
  const isTopTen = rank <= 10;
  return (
    <div
      className={`flex h-8 w-8 sm:h-10 sm:w-10 shrink-0 items-center justify-center rounded-md border font-mono text-xs sm:text-sm font-black tabular-nums ${
        isTopTen ? "border-amber-400/40 bg-amber-400/10 text-amber-300" : "border-white/15 bg-white/5 text-white/60"
      }`}
    >
      {rank}
    </div>
  );
}

function RankRowBase({ entry, tab, isMe, standalone = false }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 8 }}
      transition={{ type: "spring", stiffness: 380, damping: 32 }}
      className={`flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2 sm:py-2.5 transition ${
        isMe ? "bg-gold/[0.08] border-l-2 border-l-gold" : "hover:bg-white/[0.03]"
      } ${standalone ? "" : ""}`}
      data-testid={`lb-row-${entry.user_id}`}
    >
      <RankBadge rank={entry.rank} />
      <Avatar src={entry.avatar} name={entry.name} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 sm:gap-2">
          <span className="font-black text-sm truncate">{entry.name}</span>
          {isMe && <span className="rounded-sm bg-gold px-1.5 py-0.5 text-[8px] font-black tracking-widest text-black">TÚ</span>}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-white/45 tracking-wider">
          <span className="inline-flex items-center gap-1">
            <Skull size={10} className="text-crimson/70" />
            <span className="tabular-nums">K/D {entry.kd_ratio?.toFixed(2) ?? "—"}</span>
          </span>
          <span className="hidden sm:inline text-white/25">·</span>
          <span className="hidden sm:inline tabular-nums">{entry.kills_month?.toLocaleString() ?? 0} kills · {entry.quests_month?.toLocaleString() ?? 0} misiones</span>
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm sm:text-base font-black tabular-nums whitespace-nowrap" style={{ color: tab.accent }}>
          {entry.display?.primary || "—"}
        </div>
        <div className="text-[9px] font-bold tracking-widest text-white/40 uppercase">
          {entry.display?.secondary || tab.tag}
        </div>
      </div>
    </motion.div>
  );
}

export const RankRow = memo(RankRowBase, (p, n) =>
  p.entry.rank === n.entry.rank &&
  p.entry.user_id === n.entry.user_id &&
  p.entry.display?.primary === n.entry.display?.primary &&
  p.entry.kd_ratio === n.entry.kd_ratio &&
  p.isMe === n.isMe &&
  p.tab === n.tab
);
