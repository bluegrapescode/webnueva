import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Spade, Plus, Hand, ChevronsUp } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { PlayingCard, BetControls, FairnessChip, FeltOverlay } from "./CasinoShared";

const RESULT_TXT = {
  blackjack: { t: "BLACKJACK! Pays 3:2", c: "text-gold" },
  win: { t: "You win!", c: "text-emerald-400" },
  lose: { t: "Dealer wins", c: "text-crimson" },
  push: { t: "Push — bet returned", c: "text-muted-foreground" },
};
const HOUSE_RULES = [
  { t: "Blackjack pays", v: "3:2" },
  { t: "Dealer stands on all 17s" },
  { t: "Double down on first two cards" },
  { t: "No insurance, no split" },
];
const fmtChip = (n) => (n >= 1000 ? `${Math.round(n / 1000)}K` : `${n}`);

function HandRow({ tag, label, value, cards, testid, showValue }) {
  return (
    <div className="relative z-[2]">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-6 h-6 rounded-full border border-emerald-400/40 text-emerald-300 flex items-center justify-center text-[10px] font-bold">{tag}</span>
        <span className="label-overline text-[10px] text-emerald-300/70">{label}</span>
        {showValue && <span className="w-7 h-6 rounded-md bg-black/40 border border-emerald-400/20 text-emerald-200 flex items-center justify-center text-xs font-bold tabular-nums">{value}</span>}
      </div>
      <div className="flex gap-2 min-h-[108px] items-center" data-testid={testid}>{cards}</div>
    </div>
  );
}

export default function Blackjack({ balance, setBalance, onResolved }) {
  const { play } = useSound();
  const [game, setGame] = useState(null);
  const [bet, setBet] = useState(100);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.bjCurrent().then((r) => { setGame(r.data.game); setBalance(r.data.balance); }).catch(() => {}); }, []);

  const act = async (fn, sound = "click") => {
    if (busy) return; setBusy(true); play(sound);
    try {
      const { data } = await fn();
      setGame(data.game); setBalance(data.balance);
      if (data.game?.status === "finished") {
        const r = data.game.result;
        play(r === "lose" ? "error" : r === "push" ? "close" : "reward");
        onResolved?.();
      }
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Action failed"); }
    finally { setBusy(false); }
  };

  const playing = game?.status === "playing";
  const finished = game?.status === "finished";
  const curBet = game?.bet ?? bet;

  return (
    <div data-testid="game-blackjack">
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-11 h-11 rounded-xl border border-emerald-500/40 bg-emerald-500/10 flex items-center justify-center"><Spade size={22} className="text-emerald-400" /></div>
        <div>
          <h2 className="font-display font-extrabold text-2xl leading-tight">Dino Blackjack</h2>
          <p className="text-xs text-muted-foreground italic">Beat the dealer. Don't bust.</p>
        </div>
      </div>

      <div className="grid xl:grid-cols-[1fr_290px] gap-4 items-start">
        {/* TABLE */}
        <div>
          <div className="relative rounded-2xl overflow-hidden p-5 sm:p-7 min-h-[440px] border-2 border-amber-900/40"
            style={{ background: "#06170f" }}>
            <div className="absolute inset-0" style={{ background: "radial-gradient(115% 90% at 50% 8%, #14472f, #06170f 70%)" }} />
            <FeltOverlay edge="rgba(16,185,129,0.18)" />
            {/* rules watermark */}
            <div className="absolute top-4 inset-x-0 text-center pointer-events-none z-[1]">
              <p className="font-display font-bold tracking-[0.22em] text-emerald-300/15 text-sm">BLACKJACK PAYS 3 TO 2</p>
              <p className="font-display font-semibold tracking-[0.22em] text-emerald-300/10 text-xs mt-1">DEALER MUST STAND ON 17</p>
            </div>
            {game?.fairness && <div className="absolute top-3 right-3 z-10"><FairnessChip proof={game.fairness} /></div>}

            {/* dealer */}
            <div className="mt-8">
              <HandRow tag="D" label="Dealer" value={game?.dealer_value} showValue={!!game}
                testid="bj-dealer-cards"
                cards={game ? game.dealer.map((c, i) => <PlayingCard key={i} card={c} index={i} hidden={c === "??"} />) : <span className="text-emerald-300/45 text-sm">Place a bet to deal</span>} />
            </div>

            {/* center chip */}
            {game && (
              <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[1]" data-testid="bj-chip">
                <div className="w-16 h-16 rounded-full flex items-center justify-center font-display font-bold text-emerald-50 text-sm"
                  style={{ background: "radial-gradient(circle at 50% 35%, #34d399, #0f7a52)", border: "3px dashed rgba(255,255,255,0.5)", boxShadow: "0 4px 18px rgba(16,185,129,0.5)" }}>
                  {fmtChip(curBet)}
                </div>
              </div>
            )}

            {/* result banner */}
            <AnimatePresence>
              {finished && (
                <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ opacity: 0 }}
                  className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20" data-testid="bj-result">
                  <div className={`glass-strong rounded-xl px-6 py-3 text-center ${RESULT_TXT[game.result]?.c}`}>
                    <p className="font-display font-extrabold text-2xl">{RESULT_TXT[game.result]?.t}</p>
                    {game.payout > 0 && <p className="text-xs mt-0.5">+{game.payout.toLocaleString()} coins</p>}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* player */}
            <div className="absolute bottom-6 left-5 sm:left-7 right-5">
              <HandRow tag="Y" label="Your hand" value={game?.player_value} showValue={!!game}
                testid="bj-player-cards"
                cards={game ? game.player.map((c, i) => <PlayingCard key={i} card={c} index={i} />) : null} />
            </div>
          </div>
          {game?.fairness?.server_seed_hash && (
            <p className="text-[11px] font-mono text-emerald-400/50 mt-2 truncate">🔒 {game.fairness.server_seed_hash}</p>
          )}
        </div>

        {/* YOUR MOVE PANEL */}
        <div className="space-y-4">
          <div className="glass-strong rounded-2xl p-5" data-testid="bj-move-panel">
            <p className="label-overline text-[10px] text-emerald-400 mb-4 text-center tracking-[0.2em]">— Your Move —</p>

            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 flex items-center justify-between mb-4">
              <span className="text-sm text-muted-foreground">Current Bet</span>
              <span className="font-display font-bold text-gold text-lg tabular-nums">{curBet.toLocaleString()} CC</span>
            </div>

            {playing ? (
              <>
                <div className="grid grid-cols-2 gap-2.5">
                  <button onClick={() => act(api.bjHit)} disabled={busy} data-testid="bj-hit"
                    className="rounded-xl py-3.5 font-display font-bold inline-flex items-center justify-center gap-2 border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 transition-all disabled:opacity-40"><Plus size={17} /> Hit</button>
                  <button onClick={() => act(api.bjStand)} disabled={busy} data-testid="bj-stand"
                    className="rounded-xl py-3.5 font-display font-bold inline-flex items-center justify-center gap-2 border border-crimson/40 bg-crimson/10 text-crimson hover:bg-crimson/20 transition-all disabled:opacity-40"><Hand size={17} /> Stand</button>
                </div>
                <button onClick={() => act(api.bjDouble)} disabled={busy || !game.can_double} data-testid="bj-double"
                  className="mt-2.5 w-full rounded-xl py-3.5 font-display font-bold inline-flex items-center justify-center gap-2 border border-gold/50 bg-gold/10 text-gold hover:bg-gold/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed">
                  <ChevronsUp size={17} /> Double {game.can_double ? `(+${curBet.toLocaleString()})` : ""}</button>
              </>
            ) : (
              <>
                <BetControls bet={bet} setBet={setBet} balance={balance} disabled={busy} testid="bj-bet" />
                <button onClick={() => act(() => api.bjDeal(bet), "coins")} disabled={busy || bet > balance} data-testid="bj-deal"
                  className="mt-3 w-full rounded-xl py-3.5 font-display font-bold text-lg inline-flex items-center justify-center gap-2 bg-gradient-to-b from-gold to-[#b8860b] text-background hover:brightness-110 transition-all disabled:opacity-40">
                  <Spade size={18} /> Deal · {bet.toLocaleString()}</button>
              </>
            )}
          </div>

          {/* House rules */}
          <div className="glass rounded-2xl p-5" data-testid="bj-house-rules">
            <p className="label-overline text-[10px] text-muted-foreground mb-3">House Rules</p>
            <ul className="space-y-2.5">
              {HOUSE_RULES.map((r, i) => (
                <li key={i} className="flex items-center gap-2 text-sm text-foreground/80">
                  <span className="w-1.5 h-1.5 rounded-full bg-gold/60 shrink-0" />
                  {r.t}{r.v && <span className="font-bold text-gold">{r.v}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
