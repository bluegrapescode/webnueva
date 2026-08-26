import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Gem, Bomb, HandCoins } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { BetControls, GlowButton, FairnessChip, FeltOverlay } from "./CasinoShared";

export default function Mines({ balance, setBalance, onResolved }) {
  const { play } = useSound();
  const [bet, setBet] = useState(100);
  const [mines, setMines] = useState(3);
  const [game, setGame] = useState(null);
  const [revealed, setRevealed] = useState({});
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState(null);

  useEffect(() => { api.minesCurrent().then((r) => { if (r.data.game) { setGame(r.data.game); const rv = {}; r.data.game.revealed.forEach((i) => rv[i] = "gem"); setRevealed(rv); } setBalance(r.data.balance); }).catch(() => {}); }, []);

  const active = game && !ended;

  const start = async () => {
    if (bet > balance) { play("error"); return toast.error("Insufficient balance"); }
    play("coins"); setBusy(true);
    try {
      const { data } = await api.minesStart(bet, mines);
      setGame(data.game); setBalance(data.balance); setRevealed({}); setEnded(null);
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const reveal = async (i) => {
    if (!active || busy || revealed[i] != null) return;
    setBusy(true);
    try {
      const { data } = await api.minesReveal(i);
      setBalance(data.balance);
      if (data.result === "lose") {
        const rv = { ...revealed }; data.mine_positions.forEach((m) => rv[m] = "bomb"); rv[data.hit] = "bomb";
        setRevealed(rv); setEnded({ result: "lose", mines: data.mine_positions }); play("error"); onResolved?.();
      } else if (data.result === "cashout") {
        setRevealed((r) => ({ ...r, [i]: "gem" })); setGame((g) => ({ ...g, multiplier: data.multiplier }));
        setEnded({ result: "cashout", payout: data.payout }); play("reward"); toast.success(`Cleared! +${data.payout.toLocaleString()}`); onResolved?.();
      } else {
        setRevealed((r) => ({ ...r, [i]: "gem" }));
        setGame((g) => ({ ...g, multiplier: data.multiplier, next_multiplier: data.next_multiplier })); play("success");
      }
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const cashout = async () => {
    if (!active || busy) return; setBusy(true);
    try {
      const { data } = await api.minesCashout(); setBalance(data.balance);
      const rv = { ...revealed }; data.mine_positions.forEach((m) => { if (rv[m] == null) rv[m] = "bombdim"; });
      setRevealed(rv); setEnded({ result: "cashout", payout: data.payout }); play("reward");
      toast.success(`Cashed out ${data.multiplier}× · +${data.payout.toLocaleString()}`); onResolved?.();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="glass-strong rounded-2xl p-5 sm:p-7" data-testid="game-mines">
      <div className="rounded-2xl bg-[radial-gradient(120%_100%_at_50%_0%,#101820,#0a0c10)] border border-white/10 p-4 sm:p-6 relative overflow-hidden">
        <FeltOverlay edge="rgba(124, 168, 66,0.16)" />
        {game?.fairness && <div className="absolute top-3 left-3 z-10"><FairnessChip proof={game.fairness} /></div>}
        <div className="grid grid-cols-5 gap-2 sm:gap-2.5 max-w-md mx-auto relative z-[2]" data-testid="mines-grid">
          {Array.from({ length: 25 }).map((_, i) => {
            const st = revealed[i];
            return (
              <motion.button key={i} whileTap={{ scale: 0.9 }} onClick={() => reveal(i)} disabled={!active || busy || st != null}
                data-testid={`mines-tile-${i}`}
                className={`aspect-square rounded-lg flex items-center justify-center transition-all ${st === "gem" ? "bg-emerald-500/20 border border-emerald-400/50" : st === "bomb" ? "bg-crimson/25 border border-crimson/60" : st === "bombdim" ? "bg-crimson/10 border border-crimson/20" : "bg-white/5 border border-white/10 hover:bg-white/10 hover:border-gold/40"} ${!active ? "cursor-default" : "cursor-pointer"}`}>
                {st === "gem" && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }}><Gem size={20} className="text-emerald-400" /></motion.span>}
                {(st === "bomb" || st === "bombdim") && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }}><Bomb size={20} className={st === "bomb" ? "text-crimson" : "text-crimson/40"} /></motion.span>}
              </motion.button>
            );
          })}
        </div>
        {game && (
          <div className="flex items-center justify-center gap-6 mt-4 text-sm relative z-[2]">
            <span className="text-muted-foreground">Current <b className="text-gold" data-testid="mines-mult">{(game.multiplier || 1).toFixed(2)}×</b></span>
            {active && <span className="text-muted-foreground">Next <b className="text-emerald-400">{(game.next_multiplier || 0).toFixed(2)}×</b></span>}
          </div>
        )}
      </div>

      <div className="mt-5 space-y-3">
        {!active && (
          <>
            <BetControls bet={bet} setBet={setBet} balance={balance} disabled={busy} testid="mines-bet" />
            <div className="glass rounded-xl p-3">
              <div className="flex items-center justify-between mb-2"><span className="label-overline text-[10px] text-muted-foreground">Mines</span><span className="text-gold font-bold text-sm">{mines}</span></div>
              <input type="range" min={1} max={24} value={mines} onChange={(e) => setMines(parseInt(e.target.value))} data-testid="mines-count" className="w-full accent-crimson cursor-pointer" />
            </div>
            <GlowButton color="gold" onClick={start} disabled={busy || bet > balance} data-testid="mines-start" className="w-full text-lg"><Gem size={18} /> Start · {bet.toLocaleString()}</GlowButton>
          </>
        )}
        {active && (
          <GlowButton color="green" onClick={cashout} disabled={busy || Object.keys(revealed).length === 0} data-testid="mines-cashout" className="w-full text-lg">
            <HandCoins size={18} /> Cash out · {Math.floor(game.bet * (game.multiplier || 1)).toLocaleString()}
          </GlowButton>
        )}
        <p className="text-center text-[11px] text-muted-foreground">Find gems, avoid mines · cash out anytime</p>
      </div>
    </div>
  );
}
