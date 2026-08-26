import React, { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Package, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { RarityBadge } from "@/components/common/RarityBadge";
import { SkinIcon } from "@/components/common/SkinIcon";
import { GlitchProx } from "@/components/common/GlitchProx";
import { FairnessProof } from "@/components/common/ProvablyFair";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";

const RARITY_BAR = {
  Common: "#8b8b94", Uncommon: "#34D399", Rare: "#38bdf8",
  Epic: "#a855f7", Legendary: "#7CA842", Mythic: "#E24A4A", Apex: "#E24A4A",
};
const ITEM_W = 116;
const GAP = 12;
const STEP = ITEM_W + GAP;

function ReelItem({ item }) {
  const color = RARITY_BAR[item.rarity] || "#8b8b94";
  return (
    <div className="relative shrink-0 rounded-xl overflow-hidden glass" style={{ width: ITEM_W, height: ITEM_W }}>
      {item.type === "skin" ? <SkinIcon rarity={item.rarity} />
        : item.type === "glitch" ? <GlitchProx proximity={item.proximity} accent={item.accent_hex} compact />
        : <img src={item.image} alt={item.label} className="w-full h-full object-contain p-1.5" />}
      <div className="absolute inset-0" style={{ boxShadow: `inset 0 -40px 30px -20px ${color}55` }} />
      <span className="absolute bottom-0 inset-x-0 h-1" style={{ background: color }} />
      <span className="absolute top-1.5 left-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: color + "22", color }}>{item.rarity}</span>
    </div>
  );
}

export const CrateRoulette = ({ item, onClose, onDone }) => {
  const { play } = useSound();
  const { applyBalance, holdAutoRefresh, releaseAutoRefresh } = useAuth();
  const [phase, setPhase] = useState("idle"); // idle | spinning | done
  const [reel, setReel] = useState([]);
  const [reward, setReward] = useState(null);
  const [proof, setProof] = useState(null);
  const [tx, setTx] = useState(0);
  const [transition, setTransition] = useState("none");
  const viewportRef = useRef(null);

  const close = () => { if (phase === "spinning") return; play("close"); onClose(); };

  const spin = async () => {
    setPhase("spinning"); setReward(null);
    holdAutoRefresh(); // hold the balance steady through the reel (applied at reveal)
    try {
      const { data } = await api.openCrate(item.id);
      setProof(data.fairness || null);
      const center = (viewportRef.current?.clientWidth || 560) / 2;
      const jitter = Math.floor((Math.random() - 0.5) * (ITEM_W - 30));
      const target = data.win_index * STEP + ITEM_W / 2 - center + jitter;
      setReel(data.reel);
      setTx(0); setTransition("none");
      play("coins");
      requestAnimationFrame(() => requestAnimationFrame(() => {
        setTransition("transform 5.8s cubic-bezier(0.08, 0.72, 0.04, 1)");
        setTx(-target);
      }));
      setTimeout(async () => {
        try {
          setPhase("done"); setReward(data.reward);
          applyBalance(data.balance); // PrimeMeat/Amberium ticks the instant the reel lands
          play(data.reward.rarity === "Legendary" || data.reward.rarity === "Mythic" ? "reward" : "success");
          await onDone?.();
        } finally {
          releaseAutoRefresh(); // unconditional: a malformed payload must never latch the hold
        }
      }, 5950);
    } catch (e) {
      releaseAutoRefresh(); // never leave the balance held after a failed open
      setPhase("idle"); play("error");
      toast.error(e?.response?.data?.detail || "No se pudo abrir la caja.");
    }
  };

  return (
    <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="crate-roulette-modal">
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={close} />
      <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.94, y: 20 }}
        className="relative glass-strong rounded-3xl w-full max-w-2xl overflow-hidden">
        {phase !== "spinning" && <button onClick={close} data-testid="crate-roulette-close" className="absolute top-4 right-4 z-10 p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>}
        <div className="p-6 sm:p-8">
          <div className="flex items-center gap-4 mb-6">
            <img src={item.image} alt="" className="w-14 h-14 object-contain" />
            <div>
              <p className="label-overline text-[10px] text-gold">Abrir desde inventario</p>
              <h3 className="font-display font-bold text-2xl">{item.name}</h3>
            </div>
          </div>

          <div ref={viewportRef} className="relative h-32 rounded-2xl overflow-hidden glass mb-6" data-testid="crate-reel">
            <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-gold z-20 -translate-x-1/2 gold-glow" />
            <div className="absolute left-1/2 top-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-t-[9px] border-l-transparent border-r-transparent border-t-gold" />
            <div className="absolute left-1/2 bottom-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-b-[9px] border-l-transparent border-r-transparent border-b-gold" />
            {reel.length === 0 ? (
              <div className="h-full flex items-center justify-center text-muted-foreground text-sm"><Sparkles size={16} className="mr-2 text-gold" /> Lista para abrir</div>
            ) : (
              <div className="absolute top-1/2 -translate-y-1/2 flex items-center" style={{ gap: GAP, left: "0px", transform: `translateX(${tx}px)`, transition }}>
                {reel.map((it, idx) => <ReelItem key={idx} item={it} />)}
              </div>
            )}
            <div className="absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none" />
            <div className="absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none" />
          </div>

          <AnimatePresence>
            {phase === "done" && reward && (
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}
                className="glass rounded-2xl p-5 mb-6 flex items-center gap-4" data-testid="crate-reward"
                style={{ boxShadow: `0 0 40px ${RARITY_BAR[reward.rarity]}44` }}>
                <div className="w-16 h-16 rounded-xl overflow-hidden shrink-0">
                  {reward.type === "skin" ? <SkinIcon rarity={reward.rarity}
                  /> : reward.type === "glitch" ? <GlitchProx proximity={reward.proximity} accent={reward.accent_hex} compact
                  /> : <img src={reward.image} alt="" className="w-full h-full object-contain p-1.5" />}
                </div>
                <div className="flex-1">
                  <RarityBadge rarity={reward.rarity} />
                  <p className="font-display font-bold text-xl mt-1">{reward.label}</p>
                  <p className="text-xs text-muted-foreground">{reward.type === "skin" ? "Skin universal · añadida al inventario" : reward.type === "egg" ? "Huevo · añadido a tu inventario" : reward.type === "glitch" ? "Skin glitch · guardada en tus skins" : "Añadido a tu saldo"}</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {phase === "done" && proof && <div className="mb-6"><FairnessProof proof={proof} /></div>}

          {phase === "done" ? (
            <button onClick={close} data-testid="crate-done" className="w-full bg-gold text-background font-bold py-3 rounded-xl hover:brightness-110 transition-all">Recoger</button>
          ) : (
            <button onClick={spin} disabled={phase === "spinning"} data-testid="crate-spin"
              className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all disabled:opacity-70">
              <Package size={18} /> {phase === "spinning" ? "Abriendo…" : "Abrir caja"}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
};
