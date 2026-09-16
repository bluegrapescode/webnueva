import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Crosshair, Skull, AlertTriangle } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { fmtNum, dinoGlyph } from "@/lib/bountyMeta";

// Modal para poner precio a la cabeza de un objetivo elegido.
export function ContractModal({ target, config, wallet, onConfirm, onClose, busy }) {
  const minPrime = (config && config.min_contract_prime) || 20000;
  const minAmber = (config && config.min_contract_amber) || 0;
  const [prime, setPrime] = useState(minPrime);
  const [amber, setAmber] = useState(minAmber);

  const coins = (wallet && wallet.coins) || 0;
  const vip = (wallet && wallet.vip_coins) || 0;
  const p = Math.max(0, Number(prime) || 0);
  const a = Math.max(0, Number(amber) || 0);
  const errPrime = p < minPrime;
  const errAmber = a < minAmber;
  const noFunds = p > coins || a > vip;
  const invalid = errPrime || errAmber || noFunds || busy;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose} data-testid="bounty-contract-modal"
      >
        <motion.div
          className="relative w-full max-w-md rounded-2xl border overflow-hidden"
          style={{ background: "linear-gradient(180deg, #17070a, #0b0b0d)", borderColor: "rgba(225,29,42,0.4)", boxShadow: "0 0 60px -18px rgba(225,29,42,0.6)" }}
          initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="absolute inset-0 pointer-events-none bounty-scan opacity-20" />
          <button data-testid="bounty-contract-close" onClick={onClose} className="absolute top-3 right-3 z-10 p-1.5 rounded text-white/40 hover:text-white/80">
            <X className="w-4 h-4" />
          </button>

          <div className="relative p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-14 h-14 rounded-full flex items-center justify-center shrink-0" style={{ background: "radial-gradient(circle, rgba(225,29,42,0.18), transparent 70%)", border: "1px solid rgba(225,29,42,0.3)" }}>
                <span className="text-3xl">{dinoGlyph(target.slug)}</span>
              </div>
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.25em] text-[#ff6b74] font-bold flex items-center gap-1"><Skull className="w-3 h-3" /> Poner precio a</p>
                <h3 className="text-xl font-black text-white truncate">{target.name}</h3>
                <p className="text-[11px] text-white/45">{target.species}</p>
              </div>
            </div>

            <label className="block mb-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs uppercase tracking-wider text-white/50">🥩 Prime Meat</span>
                <span className="text-[10px] text-white/35">tienes {fmtNum(coins)}</span>
              </div>
              <input data-testid="bounty-contract-prime" type="number" min={minPrime} value={prime} onChange={(e) => setPrime(e.target.value)}
                className={`w-full bg-black/40 border rounded-lg px-3 py-2.5 text-white outline-none transition-colors ${errPrime || p > coins ? "border-[#E11D2A]/70" : "border-white/10 focus:border-[#E11D2A]/50"}`} />
              {errPrime && <p className="text-[11px] text-[#ff6b74] mt-1">Mínimo {fmtNum(minPrime)} PrimeMeat</p>}
            </label>

            <label className="block mb-5">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs uppercase tracking-wider text-white/50 flex items-center gap-1"><img src={MEDIA.coinVip} alt="" className="w-3.5 h-3.5" /> Amberium (opcional)</span>
                <span className="text-[10px] text-white/35">tienes {fmtNum(vip)}</span>
              </div>
              <input data-testid="bounty-contract-amber" type="number" min={0} value={amber} onChange={(e) => setAmber(e.target.value)}
                className={`w-full bg-black/40 border rounded-lg px-3 py-2.5 text-white outline-none transition-colors ${a > vip ? "border-[#E11D2A]/70" : "border-white/10 focus:border-[#F0B429]/50"}`} />
            </label>

            {noFunds && (
              <div className="flex items-center gap-2 text-[#ff6b74] text-xs mb-4" data-testid="bounty-contract-nofunds">
                <AlertTriangle className="w-4 h-4" /> No tienes fondos suficientes.
              </div>
            )}

            <div className="flex items-center justify-between p-3 rounded-lg bg-white/[0.03] border border-white/8 mb-5">
              <span className="text-xs uppercase tracking-wider text-white/40">Se descontará de tu billetera</span>
              <span className="text-sm font-bold text-white flex items-center gap-2">🥩 {fmtNum(p)}{a > 0 && <><img src={MEDIA.coinVip} alt="" className="w-4 h-4" />{fmtNum(a)}</>}</span>
            </div>

            <button
              data-testid="bounty-contract-confirm" disabled={invalid} onClick={() => onConfirm(p, a)}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: "linear-gradient(180deg, #E11D2A, #a10f1a)", color: "#fff", boxShadow: "0 10px 30px -10px rgba(225,29,42,0.8)" }}
            >
              <Crosshair className="w-4 h-4" /> {busy ? "Publicando…" : "Publicar bounty"}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export default ContractModal;
