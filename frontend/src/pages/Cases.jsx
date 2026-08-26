import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Package, Sparkles, ChevronRight, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CoinChip } from "@/components/common/CoinChip";
import { RarityBadge } from "@/components/common/RarityBadge";
import { SkeletonCard } from "@/components/common/PageLoader";
import { SkinIcon } from "@/components/common/SkinIcon";
import { GlitchProx } from "@/components/common/GlitchProx";
import { HudCorners, HudGrid } from "@/components/common/Hud";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { FairnessButton, FairnessProof } from "@/components/common/ProvablyFair";

const RARITY_BAR = {
  Common: "#8b8b94", Uncommon: "#34D399", Rare: "#38bdf8",
  Epic: "#a855f7", Legendary: "#7CA842", Mythic: "#E24A4A", Apex: "#E24A4A",
};

const ITEM_W = 116;
const GAP = 12;
const STEP = ITEM_W + GAP;
const SPIN_MS = 5800;

function ReelItem({ item, size = ITEM_W, dim }) {
  const color = RARITY_BAR[item.rarity] || "#8b8b94";
  return (
    <div className={`relative shrink-0 rounded-xl overflow-hidden glass transition-opacity ${dim ? "opacity-40" : "opacity-100"}`} style={{ width: size, height: size, border: `1px solid ${color}33` }}>
      {item.type === "skin" ? <SkinIcon rarity={item.rarity} />
        : item.type === "glitch" ? <GlitchProx proximity={item.proximity} accent={item.accent_hex} compact />
        : <img src={item.image} alt={item.label} className="w-full h-full object-contain p-1.5" />}
      <div className="absolute inset-0" style={{ boxShadow: `inset 0 -40px 30px -20px ${color}66` }} />
      <span className="absolute bottom-0 inset-x-0 h-1.5" style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
      {size >= 90 && <span className="absolute top-1.5 left-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: color + "22", color }}>{item.rarity}</span>}
    </div>
  );
}

// A self-contained CS:GO-style roulette row that animates to its own winner.
function RouletteRow({ reel, winIndex, spin, height = 128, itemSize = ITEM_W, settled, testid }) {
  const vpRef = useRef(null);
  const [tx, setTx] = useState(0);
  const [transition, setTransition] = useState("none");

  useEffect(() => {
    if (!spin || !reel?.length) return;
    const step = itemSize + GAP;
    const measure = () => {
      const center = (vpRef.current?.clientWidth || 600) / 2;
      // land the winning item under the center line, with a small in-item jitter
      const jitter = Math.round((Math.random() - 0.5) * (itemSize * 0.5));
      return winIndex * step + itemSize / 2 - center + jitter;
    };
    setTx(0); setTransition("none");
    const id = requestAnimationFrame(() => requestAnimationFrame(() => {
      setTransition(`transform ${SPIN_MS}ms cubic-bezier(0.12, 0.8, 0.12, 1)`);
      setTx(-measure());
    }));
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line
  }, [spin, reel, winIndex]);

  return (
    <div ref={vpRef} className="relative rounded-xl overflow-hidden border border-white/10 bg-black/50" style={{ height }} data-testid={testid}>
      {/* center marker */}
      <div className="absolute left-1/2 top-0 bottom-0 w-[3px] bg-gold z-20 -translate-x-1/2" style={{ boxShadow: "0 0 15px rgba(124, 168, 66,0.9)" }} />
      <div className="absolute left-1/2 top-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-t-[10px] border-l-transparent border-r-transparent border-t-gold" />
      <div className="absolute left-1/2 bottom-0 -translate-x-1/2 z-20 border-l-[7px] border-r-[7px] border-b-[10px] border-l-transparent border-r-transparent border-b-gold" />
      {!reel?.length ? (
        <div className="h-full flex items-center justify-center text-muted-foreground text-sm"><Sparkles size={16} className="mr-2 text-gold" /> Lista para abrir</div>
      ) : (
        <div className="absolute inset-0 flex items-center overflow-hidden">
          <div className="flex items-center will-change-transform" style={{ gap: GAP, transform: `translateX(${tx}px)`, transition }}>
            {reel.map((it, idx) => <ReelItem key={idx} item={it} size={itemSize} dim={settled && idx !== winIndex} />)}
          </div>
        </div>
      )}
      <div className="absolute inset-y-0 left-0 w-14 bg-gradient-to-r from-black/80 to-transparent z-10 pointer-events-none" />
      <div className="absolute inset-y-0 right-0 w-14 bg-gradient-to-l from-black/80 to-transparent z-10 pointer-events-none" />
    </div>
  );
}

export default function Cases({ embedded = false }) {
  const { user, applyBalance, holdAutoRefresh, releaseAutoRefresh } = useAuth();
  const { play } = useSound();
  const [cases, setCases] = useState(null);
  const [active, setActive] = useState(null);
  const [phase, setPhase] = useState("idle"); // idle | spinning | done
  const [reels, setReels] = useState([]); // [{reel, win_index, reward}]
  const [reward, setReward] = useState(null);
  const [rewards, setRewards] = useState(null);
  const [proof, setProof] = useState(null);
  const [proofs, setProofs] = useState(null);
  const [count, setCount] = useState(1);

  useEffect(() => { api.cases().then((r) => setCases(r.data)).catch(() => setCases([])); }, []);

  const balance = (cur) => (cur === "vip" ? user?.vip_coins : user?.coins) ?? 0;

  const resetSpin = () => { setPhase("idle"); setReels([]); setReward(null); setRewards(null); setProof(null); setProofs(null); };

  const openModal = (c) => { play("open"); setActive(c); setCount(1); resetSpin(); };
  const closeModal = () => { if (phase === "spinning") return; play("close"); setActive(null); };

  const spin = async () => {
    if (!user) { play("error"); toast.error("Inicia sesión para abrir cajas."); return; }
    if (balance(active.currency) < active.price * count) { play("error"); toast.error("Insufficient balance."); return; }
    setPhase("spinning"); setReward(null); setRewards(null);
    // Hold the balance steady through the reel; the authoritative post-open balance is
    // applied the instant it lands, so a PrimeMeat win visibly ticks AT the reveal.
    holdAutoRefresh();
    try {
      const { data } = count > 1 ? await api.openCaseBulk(active.id, count) : await api.openCase(active.id);
      const rowData = count > 1
        ? data.reels
        : [{ reel: data.reel, win_index: data.win_index, reward: data.reward }];
      setReels(rowData);
      play("coins");
      setTimeout(async () => {
        try {
          setPhase("done");
          applyBalance(data.balance); // authoritative — the number jumps when the reel stops
          if (count > 1) {
            setRewards(data.rewards); setProofs(data.fairness);
            const best = data.rewards.some((r) => ["Legendary", "Mythic", "Apex"].includes(r.rarity));
            play(best ? "reward" : "success");
          } else {
            setReward(data.reward); setProof(data.fairness || null);
            play(["Legendary", "Mythic"].includes(data.reward.rarity) ? "reward" : "success");
          }
        } finally {
          releaseAutoRefresh(); // unconditional: a malformed payload must never latch the hold
        }
      }, SPIN_MS + 150);
    } catch (e) {
      releaseAutoRefresh(); // never leave the balance held after a failed open
      setPhase("idle"); play("error");
      toast.error(e?.response?.data?.detail || "No se pudo abrir la caja.");
    }
  };

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Desbloquea cajas" sub="Inicia sesión para abrir cajas y ganar PrimeMeat, skins y huevos coleccionables." /></div>;

  const bulk = count > 1;

  return (
    <div className={embedded ? "" : "max-w-7xl mx-auto px-6 py-14"}>
      {!embedded && (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="flex flex-wrap items-end justify-between gap-4 mb-10">
        <div>
          <p className="label-overline text-xs text-gold mb-2">Botín</p>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Cajas</h1>
          <p className="text-muted-foreground mt-3 max-w-xl">Abre cajas para ganar <span className="text-gold">PrimeMeat</span>, <span className="text-gold">skins universales</span> y <span className="text-gold">huevos coleccionables</span>. Las skins se guardan en tu inventario y las aplicas a tu dinosaurio cuando quieras.</p>
        </div>
        <div className="flex gap-3">
          <FairnessButton />
          <div className="glass rounded-xl px-4 py-2"><CoinChip type="normal" amount={user.coins} size="md" /></div>
          <div className="glass rounded-xl px-4 py-2"><CoinChip type="vip" amount={user.vip_coins} size="md" /></div>
        </div>
      </motion.div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="cases-grid">
        {cases === null ? Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} className="aspect-[4/5]" />)
          : cases.map((c, i) => {
            const rar = c.id === "uncommon" || c.name.toLowerCase().includes("poco común") ? { label: "POCO COMÚN", color: "#34D399" } : { label: "COMÚN", color: "#8b8b94" };
            return (
            <motion.div key={c.id} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.08 }}
              className="group relative overflow-hidden bg-black/40 border p-4 flex flex-col hover:-translate-y-1 transition-transform duration-300"
              style={{ borderRadius: 3, borderColor: `${rar.color}33` }} data-testid={`case-card-${c.id}`}>
              <HudCorners color={`${rar.color}aa`} />

              {/* top row: rarity + price */}
              <div className="relative z-10 flex items-start justify-between mb-1">
                <span className="text-[10px] font-bold tracking-widest px-2.5 py-1 border bg-black/50"
                  style={{ borderRadius: 2, color: rar.color, borderColor: `${rar.color}55` }}>{rar.label}</span>
                <span className="inline-flex items-center gap-1.5 text-sm font-bold px-2.5 py-1 border border-white/10 bg-black/50" style={{ borderRadius: 2 }}>
                  <img src={MEDIA.coinNormal} alt="" className="w-4 h-4 object-contain" />{Number(c.price).toLocaleString()}
                </span>
              </div>

              {/* chest stage */}
              <div className="relative aspect-square overflow-hidden">
                <HudGrid color={`${rar.color}12`} />
                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3/4 h-3/4 rounded-full blur-3xl transition-opacity duration-500 opacity-70 group-hover:opacity-100" style={{ background: `${rar.color}33` }} />
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-1/2 h-4 rounded-[50%] blur-lg" style={{ background: `${rar.color}55` }} />
                <img src={c.image} alt={c.name} className="relative w-full h-full object-contain p-6 animate-levitate drop-shadow-[0_18px_28px_rgba(0,0,0,0.6)]" />
              </div>

              {/* info */}
              <p className="text-[10px] font-bold tracking-[0.2em] mt-1" style={{ color: rar.label === "UNCOMMON" ? rar.color : "#8b8b94" }}>NORMAL</p>
              <div className="flex items-end justify-between gap-2 mt-1">
                <h3 className="font-display font-bold text-xl leading-tight">{c.name}</h3>
                <span className="shrink-0"><b className="text-xl tabular-nums" style={{ color: rar.color }}>{c.drops}</b><span className="text-[10px] text-muted-foreground tracking-widest ml-1">PREMIOS</span></span>
              </div>

              <div className="border-t border-white/10 my-3" />
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground tracking-wider tabular-nums">{Number(c.opened || 0).toLocaleString()} ABIERTAS</span>
                <button onClick={() => openModal(c)} onMouseEnter={() => play("hover")} data-testid={`open-case-${c.id}`}
                  className="inline-flex items-center gap-1.5 font-bold text-sm px-4 py-2 transition-all hover:brightness-110"
                  style={{ borderRadius: 2, background: rar.color, color: "#0a0a0a" }}>
                  <Package size={15} /> Abrir <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          );})}
      </div>

      {/* Opening modal */}
      <AnimatePresence>
        {active && (
          <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="case-modal">
            <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={closeModal} />
            <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.94, y: 20 }}
              className="relative glass-strong rounded-3xl w-full max-w-3xl max-h-[92vh] overflow-y-auto">
              {phase !== "spinning" && <button onClick={closeModal} data-testid="case-modal-close" className="absolute top-4 right-4 z-10 p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>}

              <div className="p-6 sm:p-8">
                <div className="flex items-center gap-4 mb-6">
                  <img src={active.image} alt="" className="w-16 h-16 object-contain" />
                  <div>
                    <h3 className="font-display font-bold text-2xl">{active.name}</h3>
                    <CoinChip type={active.currency} amount={active.price} size="sm" />
                  </div>
                </div>

                {/* Reel viewport(s) */}
                {reels.length <= 1 ? (
                  <div className="mb-6" data-testid="case-reel">
                    <RouletteRow reel={reels[0]?.reel || []} winIndex={reels[0]?.win_index ?? 0} spin={phase !== "idle"} height={144} settled={phase === "done"} testid="case-reel-row-0" />
                  </div>
                ) : (
                  <div className="flex flex-col gap-3 mb-6" data-testid="case-reels-bulk">
                    <p className="label-overline text-[10px] text-muted-foreground -mb-1">Abriendo {reels.length}× · {phase === "done" ? "resultados bajo la línea" : "girando…"}</p>
                    {reels.map((row, idx) => (
                      <RouletteRow key={idx} reel={row.reel} winIndex={row.win_index} spin={phase !== "idle"} height={86} itemSize={78} settled={phase === "done"} testid={`case-reel-row-${idx}`} />
                    ))}
                  </div>
                )}

                {/* Reward reveal — single */}
                <AnimatePresence>
                  {phase === "done" && reward && (
                    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}
                      className="glass rounded-2xl p-5 mb-6 flex items-center gap-4" data-testid="case-reward"
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

                {/* Reward reveal — bulk summary */}
                {phase === "done" && rewards && (
                  <div className="mb-6" data-testid="case-rewards-bulk">
                    <p className="label-overline text-[10px] text-muted-foreground mb-3">Abriste {rewards.length} objetos</p>
                    <div className="grid grid-cols-5 gap-2.5">
                      {rewards.map((r, idx) => (
                        <motion.div key={idx} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.08 }}
                          className="glass rounded-xl p-2 text-center" data-testid={`case-bulk-reward-${idx}`}
                          style={{ boxShadow: `0 0 20px ${RARITY_BAR[r.rarity]}33`, border: `1px solid ${RARITY_BAR[r.rarity]}44` }}>
                          <div className="w-full aspect-square rounded-lg overflow-hidden mb-1.5">
                            {r.type === "skin" ? <SkinIcon rarity={r.rarity}
                            /> : r.type === "glitch" ? <GlitchProx proximity={r.proximity} accent={r.accent_hex} compact
                            /> : <img src={r.image} alt="" className="w-full h-full object-contain p-1.5" />}
                          </div>
                          <p className="text-[10px] font-semibold truncate" style={{ color: RARITY_BAR[r.rarity] }}>{r.label}</p>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}

                {phase === "done" && proof && <div className="mb-6"><FairnessProof proof={proof} /></div>}
                {phase === "done" && proofs && (
                  <div className="mb-6 glass rounded-lg px-3 py-2 text-[11px] font-mono text-muted-foreground" data-testid="case-bulk-fairness">
                    <span className="text-emerald-400 font-sans font-semibold text-[10px]">JUEGO JUSTO · {proofs.length} tiradas</span>
                    <span className="ml-2">nonces {proofs[0]?.nonce}–{proofs[proofs.length - 1]?.nonce} · verifica cada una en tu Perfil</span>
                  </div>
                )}

                {/* Count selector */}
                {phase === "idle" && (
                  <div className="flex items-center gap-2 mb-4" data-testid="case-count-selector">
                    <span className="text-xs text-muted-foreground mr-1">Cantidad:</span>
                    {[1, 5].map((n) => (
                      <button key={n} onClick={() => { setCount(n); play("click"); }} data-testid={`case-count-${n}`}
                        className={`px-4 py-1.5 rounded-lg text-sm font-bold transition-all ${count === n ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`}>
                        {n}×
                      </button>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-3">
                  {phase === "done" ? (
                    <>
                      <button onClick={closeModal} data-testid="case-done" className="flex-1 glass font-semibold py-3 rounded-xl hover:border-white/20 transition-colors">Cerrar</button>
                      <button onClick={resetSpin} data-testid="case-again"
                        className="flex-1 inline-flex items-center justify-center gap-2 bg-gold text-background font-bold py-3 rounded-xl hover:brightness-110 transition-all">
                        Abrir otra <ChevronRight size={16} />
                      </button>
                    </>
                  ) : (
                    <button onClick={spin} disabled={phase === "spinning"} data-testid="case-spin"
                      className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all disabled:opacity-70">
                      <Package size={18} /> {phase === "spinning" ? "Abriendo…" : <>Abrir {bulk ? `${count}× ` : ""}por <CoinChip type={active.currency} amount={active.price * count} size="sm" className="!text-background" /></>}
                    </button>
                  )}
                </div>

                {/* Odds */}
                {phase === "idle" && (
                  <div className="mt-6">
                    <p className="label-overline text-[10px] text-muted-foreground mb-3">Contenido y probabilidades</p>
                    <div className="flex flex-wrap gap-2">
                      {active.pool.map((p, idx) => (
                        <div key={idx} className="inline-flex items-center gap-2 glass rounded-lg px-2.5 py-1.5">
                          <div className="w-10 h-10 rounded-md overflow-hidden shrink-0">
                            {p.type === "skin" ? <SkinIcon rarity={p.rarity} iconClass="w-5 h-5"
                            /> : p.type === "glitch" ? <GlitchProx proximity={p.proximity} accent={p.accent_hex} compact
                            /> : <img src={p.image} alt="" className="w-full h-full object-contain p-1" />}
                          </div>
                          <span className="text-xs">{p.label}</span>
                          <span className="text-[10px] text-muted-foreground">{p.chance}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
