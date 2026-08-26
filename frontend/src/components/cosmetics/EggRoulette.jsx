import React, { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Egg as EggIcon, RefreshCw, ListTree, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";
import { RarityBadge } from "@/components/common/RarityBadge";
import { FairnessProof } from "@/components/common/ProvablyFair";
import { useSound } from "@/context/SoundContext";
import { DecoPreview } from "@/components/cosmetics/deco";

const RARITY_BAR = {
  Common: "#9ca3af", Uncommon: "#22c55e", Rare: "#38bdf8",
  Epic: "#a855f7", Legendary: "#f59e0b", Apex: "#ef4444",
};
const ITEM_W = 116;
const GAP = 12;
const STEP = ITEM_W + GAP;
const EGG_TIERS_META = [
  { tier: "common", name: "Común", color: "#9ca3af" },
  { tier: "uncommon", name: "Poco Común", color: "#22c55e" },
  { tier: "rare", name: "Raro", color: "#38bdf8" },
  { tier: "epic", name: "Épico", color: "#a855f7" },
  { tier: "legendary", name: "Legendario", color: "#f59e0b" },
];

function ReelItem({ item }) {
  const color = RARITY_BAR[item.rarity] || "#9ca3af";
  return (
    <div className="relative shrink-0 overflow-hidden bg-white/[0.03] flex items-center justify-center" style={{ width: ITEM_W, height: ITEM_W, borderRadius: 2 }}>
      {item.type === "coins"
        ? <img src={item.image || MEDIA.coinNormal} alt="" className="w-12 h-12 object-contain" />
        : <div className="px-1.5 w-full flex items-center justify-center"><DecoPreview item={item} size={54} /></div>}
      <div className="absolute inset-0" style={{ boxShadow: `inset 0 -40px 30px -20px ${color}55` }} />
      <span className="absolute bottom-0 inset-x-0 h-1" style={{ background: color }} />
      <span className="absolute top-1.5 left-1.5 text-[9px] font-bold px-1.5 py-0.5" style={{ background: color + "22", color, borderRadius: 2 }}>{item.rarity}</span>
    </div>
  );
}

export const EggRoulette = ({ egg, onClose, onDone }) => {
  const { play } = useSound();
  const [phase, setPhase] = useState("idle"); // idle | spinning | done
  const [reel, setReel] = useState([]);
  const [reward, setReward] = useState(null);
  const [proof, setProof] = useState(null);
  const [remaining, setRemaining] = useState(egg?.owned ?? 0);
  const [tx, setTx] = useState(0);
  const [transition, setTransition] = useState("none");
  const [poolOpen, setPoolOpen] = useState(false);
  const [poolCache, setPoolCache] = useState({});
  const [poolTier, setPoolTier] = useState(egg?.tier || "common");
  const [expanded, setExpanded] = useState(null);
  const viewportRef = useRef(null);
  const accent = egg?.color || "#7CA842";

  const selectTier = async (t) => {
    setPoolTier(t); setExpanded(null); play("click");
    if (!poolCache[t]) { try { const { data } = await api.eggPool(t); setPoolCache((c) => ({ ...c, [t]: data })); } catch { /* ignore */ } }
  };
  const showPool = async () => { setPoolOpen(true); play("click"); selectTier(egg.tier); };

  const close = () => { if (phase === "spinning") return; play("close"); onClose(); };

  const spin = async () => {
    if (remaining <= 0) { play("error"); toast.error("No te quedan huevos de este tipo."); return; }
    setPhase("spinning"); setReward(null);
    try {
      const { data } = await api.eggOpen(egg.tier);
      setProof(data.fairness || null);
      const tierInfo = (data.eggs || []).find((e) => e.tier === egg.tier);
      const center = (viewportRef.current?.clientWidth || 560) / 2;
      const target = data.win_index * STEP + ITEM_W / 2 - center;
      setReel(data.reel);
      setTx(0); setTransition("none");
      play("coins");
      requestAnimationFrame(() => requestAnimationFrame(() => {
        setTransition("transform 5.8s cubic-bezier(0.08, 0.72, 0.04, 1)");
        setTx(-target);
      }));
      setTimeout(async () => {
        setPhase("done"); setReward(data.reward);
        setRemaining(tierInfo ? tierInfo.owned : Math.max(0, remaining - 1));
        play(["Legendary", "Apex"].includes(data.reward.rarity) ? "reward" : "success");
        await onDone?.();
      }, 5950);
    } catch (e) {
      setPhase("idle"); play("error");
      toast.error(e?.response?.data?.detail || "No se pudo abrir el huevo.");
    }
  };

  const spinAgain = () => { setPhase("idle"); setReward(null); setProof(null); setReel([]); setTx(0); setTransition("none"); };

  return (
    <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="egg-roulette-modal">
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={close} />
      <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.94, y: 20 }}
        className="relative w-full max-w-2xl overflow-hidden border" style={{ borderRadius: 2, borderColor: `${accent}55`, background: "linear-gradient(160deg,#14110a,#0a0806)" }}>
        {phase !== "spinning" && <button onClick={close} data-testid="egg-roulette-close" className="absolute top-4 right-4 z-10 p-2 hover:bg-white/10" style={{ borderRadius: 2 }}><X size={18} /></button>}
        <div className="p-6 sm:p-8">
          {poolOpen && (() => {
            const pool = poolCache[poolTier];
            return (
            <div className="absolute inset-0 z-30 flex flex-col" style={{ background: "linear-gradient(160deg,#14110a,#0a0806)" }} data-testid="egg-pool-panel">
              <div className="flex items-center justify-between p-4 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <ListTree size={16} className="text-gold" />
                  <h4 className="font-display font-bold text-lg">Posibilidades</h4>
                </div>
                <button onClick={() => { setPoolOpen(false); play("close"); }} data-testid="egg-pool-close" className="p-2 hover:bg-white/10" style={{ borderRadius: 2 }}><X size={16} /></button>
              </div>
              <div className="flex gap-1 px-3 pt-3 flex-wrap">
                {EGG_TIERS_META.map((t) => {
                  const act = poolTier === t.tier;
                  return (
                    <button key={t.tier} onClick={() => selectTier(t.tier)} data-testid={`pool-tier-${t.tier}`}
                      className="px-3 py-1.5 text-[11px] font-bold transition-all" style={{ borderRadius: 2, background: act ? t.color : "rgba(255,255,255,0.05)", color: act ? "#0a0806" : "#9a9a9a" }}>
                      {t.name}
                    </button>
                  );
                })}
              </div>
              <p className="px-4 pt-2 text-[10px] text-muted-foreground">El resto de las aperturas otorgan PrimeMeat (créditos).</p>
              <div className="flex-1 overflow-y-auto p-4 pt-2 space-y-2">
                {!pool ? <p className="text-center text-muted-foreground text-sm py-8">Cargando…</p> : pool.buckets.length === 0 ? <p className="text-center text-muted-foreground text-sm py-8">Sin cosméticos en este huevo.</p> : pool.buckets.map((b, i) => (
                  <div key={i} className="border border-white/10" style={{ borderRadius: 2 }}>
                    <button type="button" onClick={() => setExpanded(expanded === i ? null : i)}
                      className="w-full flex items-center gap-3 p-3 hover:bg-white/[0.03] transition-colors text-left" data-testid={`pool-bucket-${b.rarity}`}>
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: b.color }} />
                      <span className="font-bold text-sm" style={{ color: b.color }}>{b.rarity}</span>
                      <span className="text-[11px] text-muted-foreground">· {b.count} objetos · {b.per_item}% c/u</span>
                      <span className="ml-auto font-display font-bold tabular-nums" style={{ color: b.color }}>{b.chance}%</span>
                      <ChevronDown size={14} className={`text-muted-foreground transition-transform ${expanded === i ? "rotate-180" : ""}`} />
                    </button>
                    <div className="h-1" style={{ background: `linear-gradient(90deg, ${b.color} ${Math.min(100, b.chance)}%, transparent ${Math.min(100, b.chance)}%)` }} />
                    {expanded === i && b.items && (
                      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 p-3 border-t border-white/10">
                        {b.items.map((it) => (
                          <div key={it.id} className={`flex flex-col items-center gap-1.5 p-2 border ${it.owned ? "border-emerald-500/40 bg-emerald-500/[0.05]" : "border-white/[0.06]"}`} style={{ borderRadius: 2 }}>
                            <div className="h-12 flex items-center justify-center"><DecoPreview item={it} size={40} /></div>
                            <span className="text-[10px] text-center truncate w-full text-muted-foreground">{it.name}</span>
                            {it.owned && <span className="text-[9px] font-bold text-emerald-400">✓ Tienes</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            );
          })()}
          <div className="flex items-center gap-4 mb-6">
            <img src={egg.image} alt="" className="w-16 h-16 object-contain" />
            <div className="flex-1">
              <p className="label-overline text-[10px]" style={{ color: accent }}>{egg.rarity} · Gacha de decoraciones</p>
              <h3 className="font-display font-bold text-2xl">{egg.name}</h3>
            </div>
            <div className="text-right">
              <p className="label-overline text-[9px] text-muted-foreground">Te quedan</p>
              <p className="font-display font-bold text-2xl tabular-nums" style={{ color: accent }} data-testid="egg-remaining">{remaining}</p>
            </div>
          </div>

          <button type="button" onClick={showPool} data-testid="egg-pool-toggle"
            className="w-full mb-4 inline-flex items-center justify-center gap-2 text-xs font-semibold py-2 border border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20 transition-all" style={{ borderRadius: 2 }}>
            <ListTree size={14} /> Ver todas las posibilidades y probabilidades
          </button>

          <div ref={viewportRef} className="relative h-32 overflow-hidden bg-black/40 border border-white/10 mb-6" style={{ borderRadius: 2 }} data-testid="egg-reel">
            <div className="absolute left-1/2 top-0 bottom-0 w-0.5 z-20 -translate-x-1/2" style={{ background: accent, boxShadow: `0 0 12px ${accent}` }} />
            <div className="absolute left-1/2 top-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-t-[9px] border-l-transparent border-r-transparent" style={{ borderTopColor: accent }} />
            <div className="absolute left-1/2 bottom-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-b-[9px] border-l-transparent border-r-transparent" style={{ borderBottomColor: accent }} />
            {reel.length === 0 ? (
              <div className="h-full flex items-center justify-center text-muted-foreground text-sm"><Sparkles size={16} className="mr-2" style={{ color: accent }} /> Listo para abrir</div>
            ) : (
              <div className="absolute top-1/2 flex items-center" style={{ gap: GAP, left: 0, transform: `translateY(-50%) translateX(${tx}px)`, transition }}>
                {reel.map((it, idx) => <ReelItem key={idx} item={it} />)}
              </div>
            )}
            <div className="absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-black to-transparent z-10 pointer-events-none" />
            <div className="absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-black to-transparent z-10 pointer-events-none" />
          </div>

          <AnimatePresence>
            {phase === "done" && reward && (
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}
                className="p-5 mb-6 flex items-center gap-4 border border-white/10" style={{ borderRadius: 2, boxShadow: `0 0 40px ${RARITY_BAR[reward.rarity]}44` }} data-testid="egg-reward">
                <div className="w-16 h-16 flex items-center justify-center shrink-0 bg-white/[0.03]" style={{ borderRadius: 2 }}>
                  {reward.type === "coins" ? <img src={reward.image || MEDIA.coinNormal} alt="" className="w-11 h-11 object-contain" /> : <DecoPreview item={reward} size={54} />}
                </div>
                <div className="flex-1">
                  <RarityBadge rarity={reward.rarity} />
                  <p className="font-display font-bold text-xl mt-1">{reward.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {reward.type === "coins" ? "PrimeMeat añadido a tu balance"
                      : reward.duplicate ? `Duplicado · +${(reward.refund || 0).toLocaleString()} PrimeMeat de reembolso`
                        : "¡Nueva decoración desbloqueada! Equípala abajo."}
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {phase === "done" && proof && <div className="mb-6"><FairnessProof proof={proof} /></div>}

          {phase === "done" ? (
            <div className="flex gap-3">
              <button onClick={close} data-testid="egg-collect" className="flex-1 bg-white/5 border border-white/10 text-foreground font-bold py-3 hover:bg-white/10 transition-all" style={{ borderRadius: 2 }}>Cerrar</button>
              <button onClick={spinAgain} disabled={remaining <= 0} data-testid="egg-again" className="flex-1 inline-flex items-center justify-center gap-2 font-bold py-3 hover:brightness-110 transition-all disabled:opacity-50" style={{ borderRadius: 2, background: accent, color: "#0a0806" }}>
                <RefreshCw size={16} /> Abrir otro ({remaining})
              </button>
            </div>
          ) : (
            <button onClick={spin} disabled={phase === "spinning" || remaining <= 0} data-testid="egg-spin"
              className="w-full inline-flex items-center justify-center gap-2 font-bold py-3.5 hover:brightness-110 transition-all disabled:opacity-60" style={{ borderRadius: 2, background: accent, color: "#0a0806" }}>
              <EggIcon size={18} /> {phase === "spinning" ? "Abriendo…" : remaining <= 0 ? "Sin huevos" : "Abrir Huevo"}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
};
