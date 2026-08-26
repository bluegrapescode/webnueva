import React from "react";
import { motion } from "framer-motion";
import { Coins, ChevronsUp, ShieldCheck } from "lucide-react";

const SUIT = { S: "♠", H: "♥", D: "♦", C: "♣" };

const FELT_TEXTURE = "/img-mirror/9925c70c7465d970.jpg";

// Premium felt/vignette overlay for casino tables. Purely decorative & non-interactive.
export function FeltOverlay({ edge = "rgba(124, 168, 66,0.14)" }) {
  return (
    <>
      <div className="absolute inset-0 pointer-events-none opacity-[0.14] mix-blend-soft-light" style={{ backgroundImage: `url(${FELT_TEXTURE})`, backgroundSize: "cover", backgroundPosition: "center" }} />
      <div className="absolute inset-0 pointer-events-none" style={{ boxShadow: "inset 0 0 150px rgba(0,0,0,0.6)" }} />
      <div className="absolute inset-[10px] rounded-2xl pointer-events-none" style={{ boxShadow: `inset 0 0 0 1px ${edge}` }} />
      <div className="absolute inset-x-6 top-3 h-px pointer-events-none bg-gradient-to-r from-transparent via-white/10 to-transparent" />
    </>
  );
}

// Large faded emblem watermark for the center of a table (idle-state richness).
export function TableEmblem({ icon: Icon, label }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none select-none" data-testid="table-emblem">
      <Icon className="text-white/[0.045]" style={{ width: 150, height: 150 }} />
      {label && <span className="mt-2 font-display font-extrabold tracking-[0.3em] text-white/[0.05] text-lg uppercase">{label}</span>}
    </div>
  );
}


export function PlayingCard({ card, index = 0, hidden }) {
  const isHidden = hidden || card === "??";
  const suit = isHidden ? "" : card.slice(-1);
  const rank = isHidden ? "" : card.slice(0, -1);
  const red = suit === "H" || suit === "D";
  return (
    <motion.div
      initial={{ opacity: 0, y: -30, rotateY: 90 }}
      animate={{ opacity: 1, y: 0, rotateY: 0 }}
      transition={{ delay: index * 0.12, type: "spring", stiffness: 240, damping: 20 }}
      className={`relative w-16 h-24 sm:w-[72px] sm:h-[104px] rounded-lg shrink-0 shadow-xl ${isHidden ? "bg-gradient-to-br from-crimson/80 to-crimson/40 border border-crimson/50" : "bg-white"}`}
      data-testid={`card-${isHidden ? "hidden" : card}`}
    >
      {isHidden ? (
        <div className="absolute inset-1.5 rounded-md border-2 border-white/20 bg-[repeating-linear-gradient(45deg,rgba(255,255,255,0.08),rgba(255,255,255,0.08)_6px,transparent_6px,transparent_12px)]" />
      ) : (
        <>
          <span className={`absolute top-1.5 left-2 font-bold text-sm leading-none ${red ? "text-red-600" : "text-neutral-900"}`}>{rank}</span>
          <span className={`absolute inset-0 flex items-center justify-center text-3xl ${red ? "text-red-600" : "text-neutral-900"}`}>{SUIT[suit]}</span>
          <span className={`absolute bottom-1.5 right-2 font-bold text-sm leading-none rotate-180 ${red ? "text-red-600" : "text-neutral-900"}`}>{rank}</span>
        </>
      )}
    </motion.div>
  );
}

export function BetControls({ bet, setBet, balance, disabled, testid = "bet" }) {
  const set = (v) => setBet(Math.max(10, Math.min(100000, Math.floor(v) || 10)));
  return (
    <div className="glass rounded-xl p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="label-overline text-[10px] text-muted-foreground">Monto de apuesta</span>
        <span className="text-[10px] text-muted-foreground inline-flex items-center gap-1"><Coins size={11} className="text-gold" /> {balance?.toLocaleString?.() ?? balance}</span>
      </div>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 flex items-center gap-1.5 bg-black/30 rounded-lg px-3 py-2">
          <Coins size={14} className="text-gold" />
          <input type="number" min={10} value={bet} disabled={disabled} onChange={(e) => set(parseInt(e.target.value))}
            data-testid={`${testid}-input`} className="w-full bg-transparent text-sm font-bold focus:outline-none disabled:opacity-60" />
        </div>
        {[["½", () => set(bet / 2)], ["2×", () => set(bet * 2)], ["Max", () => set(balance)]].map(([l, fn]) => (
          <button key={l} onClick={fn} disabled={disabled} data-testid={`${testid}-${l}`}
            className="px-2.5 py-2 rounded-lg glass text-xs font-bold text-muted-foreground hover:text-gold transition-colors disabled:opacity-40">{l}</button>
        ))}
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {[100, 1000, 10000, 50000].map((v) => (
          <button key={v} onClick={() => set(v)} disabled={disabled} data-testid={`${testid}-quick-${v}`}
            className="py-1.5 rounded-lg bg-white/5 text-[11px] font-bold text-muted-foreground hover:text-gold hover:bg-gold/10 transition-colors disabled:opacity-40">
            {v >= 1000 ? `${v / 1000}K` : v}
          </button>
        ))}
      </div>
    </div>
  );
}

export function FairnessChip({ proof }) {
  if (!proof?.server_seed_hash) return null;
  return (
    <div className="inline-flex items-center gap-1.5 glass rounded-md px-2 py-1 text-[10px] font-mono text-emerald-400/90" data-testid="fairness-chip" title={`Hash: ${proof.server_seed_hash}\nClient: ${proof.client_seed}\nNonce: ${proof.nonce}`}>
      <ShieldCheck size={11} /> Provably Fair · {proof.server_seed_hash.slice(0, 8)}…
    </div>
  );
}

export function GlowButton({ children, className = "", color = "gold", ...props }) {
  const colors = {
    gold: "bg-gold text-background hover:brightness-110 hover:gold-glow",
    green: "bg-emerald-500 text-background hover:brightness-110",
    red: "bg-crimson text-white hover:brightness-110",
    ghost: "glass text-foreground hover:border-white/25",
  };
  return (
    <button {...props} className={`inline-flex items-center justify-center gap-2 font-bold py-3 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed ${colors[color]} ${className}`}>
      {children}
    </button>
  );
}
