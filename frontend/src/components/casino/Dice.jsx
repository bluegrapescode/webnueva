import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Dice5 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { BetControls, GlowButton, FairnessChip, FeltOverlay } from "./CasinoShared";

export default function Dice({ balance, setBalance, onResolved }) {
  const { play } = useSound();
  const [bet, setBet] = useState(100);
  const [target, setTarget] = useState(50);
  const [dir, setDir] = useState("under");
  const [last, setLast] = useState(null);
  const [proof, setProof] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);

  const chance = dir === "over" ? 100 - target : target;
  const payout = ((100 / chance) * 0.98).toFixed(2);

  const roll = async () => {
    if (bet > balance) { play("error"); return toast.error("Insufficient balance"); }
    setBusy(true); play("coins");
    try {
      const { data } = await api.diceRoll(bet, target, dir);
      setLast(data); setBalance(data.balance); setProof(data.fairness);
      setHist((h) => [{ roll: data.roll, win: data.win }, ...h].slice(0, 12));
      play(data.win ? "reward" : "error");
      onResolved?.();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="glass-strong rounded-2xl p-5 sm:p-7" data-testid="game-dice">
      <div className="rounded-2xl bg-[radial-gradient(120%_100%_at_50%_0%,#12101f,#0a0c12)] border border-white/10 p-6 min-h-[300px] flex flex-col items-center justify-center relative overflow-hidden">
        <FeltOverlay edge="rgba(124, 168, 66,0.16)" />
        <div className="absolute top-3 left-3 z-10"><FairnessChip proof={proof} /></div>
        <div className="absolute top-3 right-3 flex gap-1 max-w-[45%] overflow-hidden z-10" data-testid="dice-history">
          {hist.slice(0, 6).map((h, i) => <span key={i} className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${h.win ? "text-emerald-400 bg-emerald-400/10" : "text-crimson bg-crimson/10"}`}>{h.roll.toFixed(1)}</span>)}
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={last ? last.roll + "-" + Math.random() : "idle"} initial={{ scale: 0.6, opacity: 0, rotate: -15 }} animate={{ scale: 1, opacity: 1, rotate: 0 }}
            className="text-center mb-6 relative z-[2]">
            <Dice5 size={34} className={`mx-auto mb-2 ${last ? (last.win ? "text-emerald-400" : "text-crimson") : "text-gold"}`} />
            <p className={`font-display font-extrabold text-6xl tabular-nums ${last ? (last.win ? "text-emerald-400" : "text-crimson") : "text-foreground"}`} data-testid="dice-roll">
              {last ? last.roll.toFixed(2) : "00.00"}
            </p>
            {last && <p className={`font-bold mt-1 ${last.win ? "text-emerald-400" : "text-crimson"}`} data-testid="dice-outcome">{last.win ? `WIN +${last.payout.toLocaleString()}` : "LOSE"}</p>}
          </motion.div>
        </AnimatePresence>

        {/* track */}
        <div className="w-full max-w-md relative z-[2]">
          <div className="relative h-3 rounded-full overflow-hidden" style={{ background: dir === "under" ? `linear-gradient(90deg,#22c55e ${target}%,#ef4444 ${target}%)` : `linear-gradient(90deg,#ef4444 ${target}%,#22c55e ${target}%)` }}>
            {last && <motion.div initial={{ left: 0 }} animate={{ left: `${last.roll}%` }} className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-full shadow-lg" style={{ boxShadow: "0 0 8px #fff" }} />}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>0</span><span>100</span></div>
        </div>
      </div>

      <div className="mt-5 space-y-3">
        <BetControls bet={bet} setBet={setBet} balance={balance} disabled={busy} testid="dice-bet" />
        <div className="grid grid-cols-2 gap-3">
          <div className="glass rounded-xl p-3">
            <div className="flex justify-between mb-2"><span className="label-overline text-[10px] text-muted-foreground">Target {dir}</span><span className="text-gold font-bold text-sm" data-testid="dice-target">{target}</span></div>
            <input type="range" min={2} max={98} value={target} onChange={(e) => setTarget(parseInt(e.target.value))} data-testid="dice-slider" className="w-full accent-gold cursor-pointer" />
          </div>
          <div className="glass rounded-xl p-3 grid grid-cols-2 gap-2">
            <button onClick={() => setDir("under")} data-testid="dice-under" className={`rounded-lg py-2 text-xs font-bold transition-all ${dir === "under" ? "bg-gold text-background" : "glass text-muted-foreground"}`}>Under</button>
            <button onClick={() => setDir("over")} data-testid="dice-over" className={`rounded-lg py-2 text-xs font-bold transition-all ${dir === "over" ? "bg-gold text-background" : "glass text-muted-foreground"}`}>Over</button>
            <div className="col-span-2 text-center text-[11px] text-muted-foreground">Win chance {chance}% · Pays <b className="text-gold">{payout}×</b></div>
          </div>
        </div>
        <GlowButton color="gold" onClick={roll} disabled={busy || bet > balance} data-testid="dice-play" className="w-full text-lg"><Dice5 size={18} /> Roll · {bet.toLocaleString()}</GlowButton>
      </div>
    </div>
  );
}
