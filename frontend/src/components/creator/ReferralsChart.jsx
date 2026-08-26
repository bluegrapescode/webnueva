import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart } from "recharts";
import { TrendingUp, BarChart3 } from "lucide-react";
import { api } from "@/lib/api";

const fmtDate = (iso) => {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
  } catch { return iso; }
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-white/10 bg-black/90 px-3 py-2 text-xs backdrop-blur-md">
      <div className="text-[10px] font-black tracking-widest text-purple-400">{fmtDate(d.date)}</div>
      <div className="mt-1 text-white font-black tabular-nums">
        {d.refs} referido{d.refs === 1 ? "" : "s"}
      </div>
      {d.pm > 0 && (
        <div className="text-emerald-400 text-[11px] tabular-nums">
          +{d.pm.toLocaleString()} PM
        </div>
      )}
    </div>
  );
}

export function ReferralsChart({ days = 30 }) {
  const [data, setData]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal]   = useState(0);
  const [totalPm, setTotalPm] = useState(0);

  useEffect(() => {
    let alive = true;
    api.cpTimeseries(days).then((r) => {
      if (!alive) return;
      const rows = r.data.days || [];
      setData(rows);
      setTotal(rows.reduce((s, x) => s + (x.refs || 0), 0));
      setTotalPm(rows.reduce((s, x) => s + (x.pm || 0), 0));
    }).catch(() => {}).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [days]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-3xl border border-white/[0.05]"
      data-testid="referrals-chart"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-400/40 to-transparent" />

      <div className="relative p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 size={13} className="text-emerald-400" />
            <span className="text-[10px] font-black tracking-[0.35em] text-emerald-400/80">ÚLTIMOS {days} DÍAS</span>
          </div>
          <div className="flex items-center gap-4 text-right">
            <div>
              <div className="text-[9px] font-black tracking-widest text-white/40">REFS</div>
              <div className="text-lg font-black text-white tabular-nums">{total}</div>
            </div>
            <div>
              <div className="text-[9px] font-black tracking-widest text-white/40">PRIME MEAT</div>
              <div className="text-lg font-black text-emerald-400 tabular-nums">+{Math.round(totalPm / 1000)}K</div>
            </div>
          </div>
        </div>

        <div className="h-52 sm:h-60 w-full">
          {loading ? (
            <div className="h-full flex items-center justify-center text-xs text-white/40">Cargando…</div>
          ) : total === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center gap-1.5">
              <TrendingUp size={22} className="text-white/20" />
              <div className="text-xs text-white/40">Todavía no hay referidos en este período</div>
              <div className="text-[10px] text-white/30">Compartí tu código para empezar</div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="chartRefs" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"  stopColor="#A78BFA" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#A78BFA" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDate} stroke="rgba(255,255,255,0.3)"
                  fontSize={10} axisLine={false} tickLine={false}
                  tick={{ fill: "rgba(255,255,255,0.35)" }} minTickGap={20} />
                <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} allowDecimals={false}
                  axisLine={false} tickLine={false}
                  tick={{ fill: "rgba(255,255,255,0.35)" }} width={30} />
                <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(167,139,250,0.4)", strokeWidth: 1 }} />
                <Area type="monotone" dataKey="refs" stroke="#A78BFA" strokeWidth={2.2}
                  fill="url(#chartRefs)" activeDot={{ r: 5, fill: "#EC4899", strokeWidth: 0 }} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </motion.div>
  );
}
