import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, ArrowDownLeft, ArrowUpRight, Gift } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CoinChip } from "@/components/common/CoinChip";
import { AnimatedCounter } from "@/components/common/AnimatedCounter";
import { PageLoader } from "@/components/common/PageLoader";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";

const TYPE_FILTERS = ["all", "earn", "purchase", "reward", "redeem"];

function txIcon(t) {
  if (t.amount > 0) return <ArrowDownLeft size={16} className="text-emerald" />;
  return <ArrowUpRight size={16} className="text-crimson" />;
}

export default function Economy() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [summary, setSummary] = useState(null);
  const [chart, setChart] = useState([]);
  const [txs, setTxs] = useState(null);
  const [curFilter, setCurFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");

  const loadTxs = () => {
    api.transactions({ currency: curFilter === "all" ? undefined : curFilter, ttype: typeFilter })
      .then((r) => setTxs(r.data)).catch(() => setTxs([]));
  };

  useEffect(() => {
    if (!user) return;
    api.economySummary().then((r) => setSummary(r.data)).catch(() => {});
    api.economyChart().then((r) => setChart(r.data)).catch(() => {});
  }, [user]);

  useEffect(() => { if (user) loadTxs(); /* eslint-disable-next-line */ }, [user, curFilter, typeFilter]);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Tu economía te espera" sub="Inicia sesión para ver saldos, transacciones y analíticas." /></div>;
  if (!summary) return <PageLoader label="Cargando economía" />;

  const exportCsv = () => {
    if (!txs?.length) return;
    const rows = [["Date", "Currency", "Type", "Amount", "Description"], ...txs.map((t) => [t.created_at, t.currency, t.type, t.amount, t.description])];
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "primal-transactions.csv";
    a.click();
    play("success");
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="flex flex-wrap items-end justify-between gap-4 mb-10">
        <div>
          <p className="label-overline text-xs text-gold mb-2">Cartera</p>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Economía</h1>
        </div>
      </motion.div>

      {/* Balance cards */}
      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {[
          { type: "normal", label: "PrimeMeat", bal: summary.coins, earned: summary.earned_normal, spent: summary.spent_normal, glow: "hover:gold-glow" },
          { type: "vip", label: "Amberium", bal: summary.vip_coins, earned: summary.earned_vip, spent: summary.spent_vip, glow: "hover:crimson-glow" },
        ].map((c, i) => (
          <motion.div key={c.type} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.1 }}
            className={`relative glass rounded-2xl p-7 overflow-hidden ${c.glow} transition-all duration-500`} data-testid={`balance-card-${c.type}`}>
            <div className="grain absolute inset-0 opacity-40" />
            <div className="relative flex items-center gap-5">
              <CoinChip type={c.type} size="xl" />
              <div className="flex-1">
                <p className="label-overline text-[10px] text-muted-foreground">{c.label}</p>
                <p className="font-display font-extrabold text-4xl mt-1"><AnimatedCounter value={c.bal} /></p>
              </div>
            </div>
            <div className="relative grid grid-cols-2 gap-3 mt-6">
              <div className="glass rounded-xl p-3">
                <span className="inline-flex items-center gap-1.5 text-xs text-emerald"><TrendingUp size={13} /> Earned</span>
                <p className="font-display font-bold text-lg mt-0.5">{c.earned.toLocaleString()}</p>
              </div>
              <div className="glass rounded-xl p-3">
                <span className="inline-flex items-center gap-1.5 text-xs text-crimson"><TrendingDown size={13} /> Spent</span>
                <p className="font-display font-bold text-lg mt-0.5">{c.spent.toLocaleString()}</p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Chart */}
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
        className="glass rounded-2xl p-6 mb-6" data-testid="economy-chart">
        <p className="label-overline text-xs text-muted-foreground mb-6">7-Day Net Movement</p>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chart}>
              <defs>
                <linearGradient id="gNormal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34D399" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gVip" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7CA842" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#7CA842" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} stroke="#666" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#666" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "rgba(12,12,15,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }} />
              <Area type="monotone" dataKey="normal" stroke="#34D399" strokeWidth={2} fill="url(#gNormal)" name="Survival" />
              <Area type="monotone" dataKey="vip" stroke="#7CA842" strokeWidth={2} fill="url(#gVip)" name="Amberium" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      {/* Transactions */}
      <div className="glass rounded-2xl p-6" data-testid="transactions-panel">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <p className="label-overline text-xs text-muted-foreground">Historial de Transacciones</p>
          <div className="flex flex-wrap gap-2 items-center">
            {["all", "normal", "vip"].map((c) => (
              <button key={c} onClick={() => { setCurFilter(c); play("click"); }} data-testid={`tx-cur-${c}`}
                className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-all ${curFilter === c ? "bg-gold text-background" : "glass text-muted-foreground"}`}>{c === "all" ? "All" : c.toUpperCase()}</button>
            ))}
            <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); play("click"); }} data-testid="tx-type-filter"
              className="text-xs glass rounded-lg px-3 py-1.5 bg-transparent focus:outline-none">
              {TYPE_FILTERS.map((t) => <option key={t} value={t} className="bg-background">{t}</option>)}
            </select>
            <button onClick={exportCsv} data-testid="export-csv" className="text-xs font-semibold glass px-3 py-1.5 rounded-lg hover:border-gold/40 transition-colors">Exportar CSV</button>
          </div>
        </div>
        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {txs === null ? <p className="text-muted-foreground py-8 text-center text-sm">Loading…</p>
            : txs.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no hay transacciones.</p>
            : txs.map((t, i) => (
              <motion.div key={t.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}
                className="flex items-center gap-3 glass rounded-xl p-3.5 hover:border-white/15 transition-colors">
                <div className="p-2 rounded-lg bg-secondary">{txIcon(t)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate">{t.description}</p>
                  <p className="text-xs text-muted-foreground">{new Date(t.created_at).toLocaleString()} · <span className="capitalize">{t.type}</span></p>
                </div>
                <div className={`font-display font-bold tabular-nums ${t.amount > 0 ? "text-emerald" : "text-crimson"}`}>
                  {t.amount > 0 ? "+" : ""}{t.amount.toLocaleString()} <span className="text-[10px] text-muted-foreground">{t.currency === "vip" ? "AMB" : "PM"}</span>
                </div>
              </motion.div>
            ))}
        </div>
      </div>
    </div>
  );
}
