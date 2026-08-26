import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { HudCorners } from "@/components/common/Hud";
import { STANDING_STYLE as STYLE } from "@/lib/standing";

// Localize the backend ladder's English penalty labels for the Spanish site.
const PENALTY_ES = {
  "1 hour ban": "ban de 1 hora",
  "24 hour ban": "ban de 24 horas",
  "7 day ban": "ban de 7 días",
  "Permanent ban": "ban permanente",
};

export function AccountStanding({ onLoaded }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.profileStanding().then((r) => { setData(r.data); onLoaded?.(r.data); }).catch(() => {});
  }, []);

  if (!data) return null;
  const s = data.standing;
  const st = STYLE[s.status] || STYLE.good;
  const Icon = st.Icon;
  const pct = Math.min(100, Math.round((s.active_strikes / Math.max(1, s.next_threshold)) * 100));

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      data-testid="account-standing" className="relative overflow-hidden border p-6 mb-8"
      style={{ borderRadius: 3, background: st.bg, borderColor: st.bd }}>
      <HudCorners color={`${st.c}88`} />
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Icon size={26} style={{ color: st.c }} />
          <div>
            <p className="label-overline text-[10px] tracking-widest text-muted-foreground/70">ACCOUNT STANDING</p>
            <p className="font-display font-bold text-2xl" style={{ color: st.c }} data-testid="standing-label">{st.label}</p>
          </div>
        </div>
        <div className="text-right">
          <span className="font-display font-bold text-2xl tabular-nums" style={{ color: st.c }} data-testid="standing-count">
            {s.active_strikes} <span className="text-muted-foreground/50">/ {s.next_threshold}</span>
          </span>
        </div>
      </div>

      <div className="h-[6px] w-full bg-white/5 my-4" style={{ borderRadius: 2 }}>
        <motion.div className="h-full" initial={{ width: 0 }} animate={{ width: `${pct}%` }} style={{ background: st.c, borderRadius: 2 }} />
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {s.ban_permanent ? "Cuenta baneada permanentemente"
            : s.banned ? "Suspendido temporalmente"
            : s.active_strikes === 0 ? "Sin strikes activos"
            : `${s.active_strikes} strike${s.active_strikes > 1 ? "s" : ""} activo${s.active_strikes > 1 ? "s" : ""}`}
        </span>
        <span className="font-semibold" style={{ color: st.c }} data-testid="standing-next-penalty">
          En {s.next_threshold}: {PENALTY_ES[s.next_penalty] || s.next_penalty}
        </span>
      </div>
    </motion.div>
  );
}
