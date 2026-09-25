import React, { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Spade, Rocket, Dices, Trophy, BarChart3, History, Coins, Crown, Package, Dice5, Gift, Plane } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import Blackjack from "@/components/casino/Blackjack";
import Roll from "@/components/casino/Roll";
import Wheel from "@/components/casino/Wheel";
import Cases from "@/pages/Cases";
import AirdropArena from "@/components/airdrop/AirdropArena";

// Crash retired 2026-08-20 (owner order). Its tab and component are gone; the
// icon map keeps the crash entry so ledger history rows from before the
// retirement still render with their own icon instead of the fallback.
// Nublar Spin (2026-08-23): the daily free wheel lives here as a tab (owner:
// "put it in casino tab"); ?tab=wheel deep-links straight to it.
const GAMES = [
  { k: "airdrop", label: "Airdrop", icon: Plane, C: () => <AirdropArena /> },
  { k: "blackjack", label: "Blackjack", icon: Spade, C: Blackjack },
  { k: "roll", label: "Roll", icon: Dices, C: Roll },
  { k: "wheel", label: "Ruleta Diaria", icon: Gift, C: Wheel },
  { k: "crates", label: "Cajas", icon: Package, C: () => <Cases embedded /> },
];
// Tabs that own the full width (no stats/leaderboard sidebar).
const FULL_WIDTH = ["airdrop", "crates", "crash", "roll", "wheel"];

const GAME_ICON = { blackjack: Spade, roll: Dices, crash: Rocket };

export default function Casino() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  // ?tab=crates|blackjack|roll lets the retired /cases route land on Cajas directly;
  // an old ?tab=crash link fails the GAMES membership check and falls back to blackjack.
  const location = useLocation();
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    return GAMES.some((g) => g.k === t) ? t : "blackjack";
  });
  useEffect(() => {
    const t = new URLSearchParams(location.search).get("tab");
    if (t && GAMES.some((g) => g.k === t)) setTab(t);
  }, [location.search]);
  const [balance, setBalance] = useState(user?.coins ?? 0);
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [board, setBoard] = useState([]);

  const loadMeta = () => {
    api.casinoStats().then((r) => setStats(r.data)).catch(() => {});
    api.casinoHistory().then((r) => setHistory(r.data)).catch(() => {});
    api.casinoLeaderboard().then((r) => setBoard(r.data)).catch(() => {});
  };
  useEffect(() => { if (user) { setBalance(user.coins); loadMeta(); } }, [user]);

  const onResolved = () => { refresh(); loadMeta(); };

  if (!user) return <div className="max-w-6xl mx-auto px-6 py-14"><SignInPrompt title="Mini Juegos Isla Nublar" sub="Inicia sesión para jugar y abrir Cajas con tu PrimeMeat." /></div>;

  const Active = GAMES.find((g) => g.k === tab)?.C;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12">
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gold/15 flex items-center justify-center"><Crown className="text-gold" size={24} /></div>
          <div>
            <p className="label-overline text-xs text-gold">Zona de Mini Juegos</p>
            <h1 className="font-display font-extrabold text-4xl tracking-tighter">Mini Juegos Isla Nublar</h1>
          </div>
        </div>
      </motion.div>

      {/* Game tabs */}
      <div className="flex gap-2 mb-5 overflow-x-auto pb-1" data-testid="casino-tabs">
        {GAMES.map((g) => (
          <button key={g.k} onClick={() => { setTab(g.k); play("click"); }} data-testid={`casino-tab-${g.k}`}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm whitespace-nowrap transition-all ${tab === g.k ? "bg-gold text-background gold-glow" : "glass text-muted-foreground hover:text-foreground"}`}>
            <g.icon size={16} /> {g.label}
          </button>
        ))}
      </div>

      <div className={FULL_WIDTH.includes(tab) ? "" : "grid lg:grid-cols-[1fr_320px] gap-5"}>
        {/* Game */}
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.25 }}>
            {Active && <Active balance={balance} setBalance={setBalance} onResolved={onResolved} />}
          </motion.div>
        </AnimatePresence>

        {/* Sidebar */}
        {!FULL_WIDTH.includes(tab) && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="glass rounded-2xl p-4" data-testid="casino-stats">
            <p className="label-overline text-[10px] text-muted-foreground mb-3 inline-flex items-center gap-1.5"><BarChart3 size={12} className="text-gold" /> Your stats</p>
            <div className="grid grid-cols-2 gap-2.5">
              {[["Games", stats?.games ?? 0], ["Wins", stats?.wins ?? 0], ["Wagered", (stats?.wagered ?? 0).toLocaleString()], ["Biggest win", `+${(stats?.biggest_win ?? 0).toLocaleString()}`]].map(([l, v]) => (
                <div key={l} className="glass rounded-lg p-2.5"><p className="text-[9px] label-overline text-muted-foreground">{l}</p><p className="font-bold text-sm truncate">{v}</p></div>
              ))}
            </div>
            <div className={`mt-2.5 rounded-lg p-2.5 text-center ${(stats?.net ?? 0) >= 0 ? "bg-emerald-500/10 text-emerald-400" : "bg-crimson/10 text-crimson"}`}>
              <span className="text-[10px] label-overline">Net profit</span>
              <p className="font-display font-bold text-lg">{(stats?.net ?? 0) >= 0 ? "+" : ""}{(stats?.net ?? 0).toLocaleString()}</p>
            </div>
          </div>

          {/* Leaderboard */}
          <div className="glass rounded-2xl p-4" data-testid="casino-leaderboard">
            <p className="label-overline text-[10px] text-muted-foreground mb-3 inline-flex items-center gap-1.5"><Trophy size={12} className="text-gold" /> Mejores jugadores</p>
            {board.length === 0 ? <p className="text-xs text-muted-foreground text-center py-3">Aún no hay partidas</p> : (
              <div className="space-y-1.5">
                {board.slice(0, 6).map((r, i) => (
                  <div key={r.user_id} className="flex items-center gap-2 text-sm" data-testid={`lb-row-${i}`}>
                    <span className={`w-5 text-center font-bold text-xs ${i === 0 ? "text-gold" : "text-muted-foreground"}`}>{i + 1}</span>
                    <img src={r.avatar || "/favicon.ico"} alt="" className="w-6 h-6 rounded-full object-cover" />
                    <span className="flex-1 truncate text-xs">{r.name}</span>
                    <span className={`text-xs font-bold ${r.net >= 0 ? "text-emerald-400" : "text-crimson"}`}>{r.net >= 0 ? "+" : ""}{r.net.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* History */}
          <div className="glass rounded-2xl p-4" data-testid="casino-history">
            <p className="label-overline text-[10px] text-muted-foreground mb-3 inline-flex items-center gap-1.5"><History size={12} className="text-gold" /> Apuestas recientes</p>
            {history.length === 0 ? <p className="text-xs text-muted-foreground text-center py-3">Tus apuestas aparecerán aquí</p> : (
              <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
                {history.map((h) => {
                  const Icon = GAME_ICON[h.game] || Dice5;
                  return (
                    <div key={h.id} className="flex items-center gap-2 glass rounded-lg px-2.5 py-1.5" data-testid={`hist-${h.id}`}>
                      <Icon size={13} className="text-muted-foreground shrink-0" />
                      <span className="flex-1 text-[11px] capitalize truncate">{h.game}{h.multiplier ? ` · ${h.multiplier}×` : ""}</span>
                      <span className={`text-[11px] font-bold ${h.net >= 0 ? "text-emerald-400" : "text-crimson"}`}>{h.net >= 0 ? "+" : ""}{h.net.toLocaleString()}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
