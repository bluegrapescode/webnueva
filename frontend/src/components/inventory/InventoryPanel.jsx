import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { GripVertical, Check, Rocket, Gift, Crown, Sparkles, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SkinIcon } from "@/components/common/SkinIcon";
import { GlitchProx } from "@/components/common/GlitchProx";
import { CrateRoulette } from "@/components/inventory/CrateRoulette";
import { EggRoulette } from "@/components/cosmetics/EggRoulette";
import { DinoManageModal } from "@/components/inventory/DinoManageModal";
import { RedeemModal as TokenRedeemModal, tokenEffect, tierLabel } from "@/components/battlepass/TokenPanel";

const EGG_RARITY_COLOR = { Common: "#9ca3af", Uncommon: "#22c55e", Rare: "#38bdf8", Epic: "#a855f7", Legendary: "#f59e0b" };

// The wheel's Vial GEN-Ø shows the owner's own render, whatever path the
// inventory row was written with (rows granted before the art existed carry
// the old placeholder in Mongo — the art is decided here, not by the doc).
const VIAL_ITEM_ID = "wheel_gen0_vial";
const VIAL_ART = "/tokens/vial-gen0.png";
const itemArt = (it) => (it.item_id === VIAL_ITEM_ID ? VIAL_ART : (it.skin_image || it.image));

// The full inventory surface (category tabs + item grid + equip/manage/open flows +
// drag reorder). Extracted from pages/Inventory.jsx so the Dino en Vivo Estadísticas
// tab offers the same equipment without duplicating any behavior.
export function InventoryPanel() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [inv, setInv] = useState([]);
  const [dragOver, setDragOver] = useState(null);
  const dragIndex = useRef(null);
  const [invCat, setInvCat] = useState("all");
  const [equippedSkinId, setEquippedSkinId] = useState(null);
  const [equipping, setEquipping] = useState(null);
  const [skinColors, setSkinColors] = useState({});
  const [activeDinoSlug, setActiveDinoSlug] = useState(null);
  const [inGame, setInGame] = useState(false);
  const [crateOpen, setCrateOpen] = useState(null);
  const [eggOpen, setEggOpen] = useState(null);
  const [manageDino, setManageDino] = useState(null);
  const [rewardSkins, setRewardSkins] = useState([]); // won glitch skins (db.reward_skins)
  const [applyingGlitch, setApplyingGlitch] = useState(null);
  // Battle Pass tokens live in the SAME inventory (category "Tokens") and are
  // usable from here too (owner ask 2026-08-07: "everything should go here").
  const [tokenActive, setTokenActive] = useState(null);
  // Vial GEN-Ø (wheel prize): a two-press confirm, then the wheel's use lane.
  const [vialConfirm, setVialConfirm] = useState(null);
  const [vialBusy, setVialBusy] = useState(false);
  const drinkVial = async (invId) => {
    if (vialBusy) return;
    setVialBusy(true);
    try {
      const r = await api.wheelUseVial(invId);
      play("zombieRoar");
      toast.success(r.data?.message || "El virus GEN-Ø recorre tus venas.");
      setVialConfirm(null);
      await reloadInventory();
    } catch (e) {
      play("error");
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "No se pudo usar el vial.");
    } finally { setVialBusy(false); }
  };
  const [bpLiveTokens, setBpLiveTokens] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.inventory().then((r) => setInv(r.data)).catch(() => {});
    api.bpStatus().then((r) => setBpLiveTokens(!!r.data?.live_tokens_enabled)).catch(() => {});
    api.activeDino().then((r) => {
      setEquippedSkinId(r.data.active?.skin?.inv_id || null);
      setActiveDinoSlug(r.data.active?.slug || null);
      setInGame(!!r.data.in_game);
    }).catch(() => {});
    api.skins().then((r) => {
      const map = {};
      r.data.forEach((s) => { map[s.name] = s.color; });
      setSkinColors(map);
    }).catch(() => {});
    api.rewardSkins().then((r) => setRewardSkins(r.data?.skins || [])).catch(() => {});
  }, [user]);

  const equipSkin = async (it) => {
    setEquipping(it.id);
    try {
      const r = await api.equipSkin(it.id);
      setEquippedSkinId(it.id);
      play("success");
      if (r?.data?.applied_ingame) {
        toast.success("¡Skin aplicada a tu dino en vivo! (-1 uso)", { description: `${it.name} se pintó en tu dinosaurio dentro del juego. Puede tardar unos segundos en verse.` });
      } else {
        toast.success("¡Skin equipada! (-1 uso)", { description: `${it.name} aplicada. Revisa Dino en Vivo.` });
      }
      api.inventory().then((r2) => setInv(r2.data)).catch(() => {});
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo equipar la skin");
    } finally { setEquipping(null); }
  };

  // Won glitch skins apply through their OWN IPC lane (not the equip lane, which
  // would corrupt the glitch payload). No charge — the skin is already owned,
  // but every apply spends 1 of its limited uses; at 0 the skin disappears.
  const applyGlitchSkin = async (s) => {
    setApplyingGlitch(s.glitch_id);
    play("click");
    try {
      const r = await api.applyRewardSkin(s.glitch_id);
      const left = r.data?.uses_left;
      play("success");
      if (left === 0) {
        setRewardSkins((prev) => prev.filter((x) => x.glitch_id !== s.glitch_id));
        toast.success("Skin glitch enviada a tu dinosaurio (último uso)", { description: `${s.name} se está aplicando. Sin usos restantes — la skin desapareció de tu inventario.` });
      } else {
        if (typeof left === "number") setRewardSkins((prev) => prev.map((x) => (x.glitch_id === s.glitch_id ? { ...x, uses: left } : x)));
        toast.success("Skin glitch enviada a tu dinosaurio (-1 uso)", { description: `${s.name} se está aplicando. ${left === 1 ? "Te queda 1 uso" : `Te quedan ${left} usos`} de esta skin. Puede tardar unos minutos en verse dentro del juego.` });
      }
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo aplicar la skin glitch");
      // The card may be stale (opened in another tab / out of uses) — re-sync.
      api.rewardSkins().then((r2) => setRewardSkins(r2.data?.skins || [])).catch(() => {});
    } finally { setApplyingGlitch(null); }
  };

  const reloadInventory = async () => {
    await refresh();
    api.inventory().then((r) => setInv(r.data)).catch(() => {});
    api.activeDino().then((r) => { setActiveDinoSlug(r.data.active?.slug || null); setInGame(!!r.data.in_game); }).catch(() => {});
  };

  // "Consumables" (the wheel's Vial GEN-Ø) sits with the Fichas: one tab for
  // everything a player USES rather than wears or hatches.
  const bucket = (c) => (c === "Dinosaurs" ? "Dinos" : c === "Skins" ? "Skins" : c === "Eggs" ? "Eggs" : c === "Crates" ? "Cajas" : (c === "Tokens" || c === "Consumables") ? "Fichas" : "Misc");
  // The live tab equips skins, hatches eggs and spends Battle Pass tokens
  // (owner asks 2026-07-16 + 2026-08-07): dinosaurs are managed in La Bóveda
  // and crates inside the Casino, so Dinos / Cajas / Misc stay unsurfaced.
  const visibleInv = inv.filter((it) => {
    const b = bucket(it.category);
    return b === "Skins" || b === "Eggs" || b === "Fichas";
  });
  const displayedInv = invCat === "all" ? visibleInv : visibleInv.filter((it) => bucket(it.category) === invCat);
  // Won glitch skins live under the SAME "Skins" tab as universal skins
  // (owner ask 2026-07-14 — no separate Recompensas tab).
  const showGlitchSkins = (invCat === "all" || invCat === "Skins") && rewardSkins.length > 0;

  const onDragEnter = (i) => {
    setDragOver(i);
    const from = dragIndex.current;
    if (from === null || from === i) return;
    setInv((prev) => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(i, 0, moved);
      return next;
    });
    dragIndex.current = i;
  };

  const persistOrder = async () => {
    setDragOver(null);
    dragIndex.current = null;
    try { await api.inventoryReorder(inv.map((x) => x.id)); play("success"); } catch { /* noop */ }
  };

  if (!user) return null;

  return (
    <>
      {visibleInv.length === 0 && rewardSkins.length === 0 ? (
        <p className="text-muted-foreground py-12 text-center">Tu inventario está vacío. Visita la tienda para adquirir objetos.</p>
      ) : (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
            <div className="flex gap-2" data-testid="inv-category-tabs">
              {["all", "Skins", "Eggs", "Fichas"].map((cat) => (
                <button key={cat} onClick={() => { setInvCat(cat); play("click"); }} data-testid={`inv-cat-${cat.toLowerCase()}`}
                  className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-all ${invCat === cat ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`}>
                  {cat === "all" ? "All" : cat}
                </button>
              ))}
            </div>
            {invCat === "all" && <p className="text-xs text-muted-foreground inline-flex items-center gap-1.5"><GripVertical size={13} /> Drag to reorder</p>}
          </div>
          {displayedInv.length === 0 && !showGlitchSkins ? (
            <p className="text-muted-foreground py-12 text-center">No hay objetos en esta categoría.</p>
          ) : (
          <>
          {displayedInv.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4" data-testid="inventory-grid">
            {displayedInv.map((it) => {
              const i = inv.indexOf(it);
              const canDrag = invCat === "all";
              return (
              <motion.div
                key={it.id}
                layout
                draggable={canDrag}
                onDragStart={canDrag ? () => { dragIndex.current = i; play("click"); } : undefined}
                onDragEnter={canDrag ? () => onDragEnter(i) : undefined}
                onDragOver={canDrag ? (e) => e.preventDefault() : undefined}
                onDragEnd={canDrag ? persistOrder : undefined}
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3 }}
                className={`group relative glass rounded-xl overflow-hidden hover:border-gold/40 transition-all ${canDrag ? "cursor-grab active:cursor-grabbing" : ""} ${dragOver === i ? "ring-2 ring-gold scale-[1.03]" : ""}`}
                data-testid={`inv-item-${it.id}`}
              >
                <div className="aspect-square overflow-hidden">
                  {it.category === "Skins" || !itemArt(it)
                    ? <SkinIcon rarity={it.rarity} color={it.color || skinColors[it.name]} />
                    : <img src={itemArt(it)} alt={it.name} onError={(e) => { e.currentTarget.style.display = "none"; }} className="w-full h-full object-contain p-2 group-hover:scale-105 transition-transform duration-500 pointer-events-none" />}
                  <div className="absolute inset-0 bg-gradient-to-t from-background/90 to-transparent" />
                </div>
                <div className="absolute top-2 right-2"><RarityBadge rarity={it.rarity} className="text-[8px] px-1.5 py-0" /></div>
                {it.category === "Dinosaurs" && (it.prime || it.tier === "prime") && (
                  <span className="absolute top-2 left-2 text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 inline-flex items-center gap-0.5" data-testid={`inv-prime-${it.id}`}><Crown size={9} /> PRIME</span>
                )}
                <div className="absolute bottom-0 inset-x-0 p-3">
                  {it.universal && <span className="inline-block mb-1 text-[8px] font-bold px-1.5 py-0.5 rounded bg-gold/20 text-gold">UNIVERSAL</span>}
                  <p className="text-xs font-bold leading-tight line-clamp-2">{it.custom_name || it.name}</p>
                  {it.category === "Skins"
                    ? <span className="text-[10px] text-gold font-semibold">{it.uses ?? 0} uses</span>
                    : (it.quantity > 1 && <span className="text-[10px] text-gold">x{it.quantity}</span>)}
                  {it.category === "Dinosaurs" && it.recovery_id && (
                    <span className="block text-[9px] text-muted-foreground font-mono mt-0.5">ID {it.recovery_id}</span>
                  )}
                  {it.category === "Skins" && (
                    equippedSkinId === it.id ? (
                      <span className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-emerald/15 text-emerald border border-emerald/30" data-testid={`skin-equipped-${it.id}`}>
                        <Check size={11} /> Equipped
                      </span>
                    ) : (
                      <button onClick={(e) => { e.stopPropagation(); equipSkin(it); }} disabled={equipping === it.id} data-testid={`equip-skin-${it.id}`}
                        className="mt-2 w-full text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-60">
                        {equipping === it.id ? "Aplicando…" : "Aplicar al dino"}
                      </button>
                    )
                  )}
                  {it.category === "Dinosaurs" && (
                    <button onClick={(e) => { e.stopPropagation(); play("open"); setManageDino(it); }} data-testid={`manage-inv-dino-${it.id}`}
                      className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all">
                      <Rocket size={11} /> Manage
                    </button>
                  )}
                  {it.category === "Crates" && (
                    <button onClick={(e) => { e.stopPropagation(); play("open"); setCrateOpen(it); }} data-testid={`open-inv-crate-${it.id}`}
                      className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all">
                      <Gift size={11} /> Abrir caja
                    </button>
                  )}
                  {it.category === "Eggs" && (
                    <button onClick={(e) => { e.stopPropagation(); play("open"); setEggOpen({ tier: it.tier, name: it.name, rarity: it.rarity, image: it.image, color: EGG_RARITY_COLOR[it.rarity] || "#7CA842", owned: it.quantity || 1 }); }} data-testid={`open-inv-egg-${it.id}`}
                      className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg text-background hover:brightness-110 transition-all" style={{ background: EGG_RARITY_COLOR[it.rarity] || "#7CA842" }}>
                      <Gift size={11} /> Abrir huevo
                    </button>
                  )}
                  {it.category === "Tokens" && (
                    <>
                      <span className="block text-[9px] text-muted-foreground leading-tight mt-0.5">
                        {tokenEffect(it.token, it.token_tier)} · {tierLabel(it.token_tier)}
                      </span>
                      <button onClick={(e) => { e.stopPropagation(); play("open"); setTokenActive({ ...it, tier: it.token_tier, inv_id: it.id }); }} data-testid={`use-inv-token-${it.id}`}
                        className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all">
                        <Rocket size={11} /> Usar
                      </button>
                    </>
                  )}
                  {it.item_id === VIAL_ITEM_ID && (
                    <>
                      <span className="block text-[9px] text-muted-foreground leading-tight mt-0.5">
                        Infección GEN-Ø al 100% · tu próximo dino vivo se transforma
                      </span>
                      {vialConfirm === it.id ? (
                        <div className="mt-2 flex gap-1">
                          <button disabled={vialBusy} onClick={(e) => { e.stopPropagation(); drinkVial(it.id); }} data-testid={`use-inv-vial-confirm-${it.id}`}
                            className="flex-1 inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg text-white hover:brightness-110 transition-all disabled:opacity-60" style={{ background: "#DC2626" }}>
                            {vialBusy ? "…" : "Confirmar"}
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); setVialConfirm(null); }} className="px-2 py-1.5 rounded-lg glass text-[10px] font-bold">No</button>
                        </div>
                      ) : (
                        <button onClick={(e) => { e.stopPropagation(); play("open"); setVialConfirm(it.id); }} data-testid={`use-inv-vial-${it.id}`}
                          className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg text-white hover:brightness-110 transition-all" style={{ background: "#DC2626" }}>
                          <FlaskConical size={11} /> Beber vial
                        </button>
                      )}
                    </>
                  )}
                </div>
              </motion.div>
              );
            })}
          </div>
          )}
          {showGlitchSkins && (
            <div className={displayedInv.length > 0 ? "mt-6" : ""} data-testid="glitch-skins-section">
              {displayedInv.length > 0 && (
                <div className="flex items-center gap-3 mb-4">
                  <span className="h-px flex-1 bg-white/10" />
                  <p className="label-overline text-[11px] text-gold inline-flex items-center gap-1.5 shrink-0"><Sparkles size={12} /> Skins Glitch</p>
                  <span className="h-px flex-1 bg-white/10" />
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4" data-testid="glitch-skins-grid">
                {rewardSkins.map((s) => (
                  <div key={s.glitch_id} className="group relative glass rounded-xl overflow-hidden hover:border-gold/40 transition-all" data-testid={`inv-glitch-${s.glitch_id}`}>
                    <div className="aspect-square overflow-hidden">
                      {/* Name + colour proximity, never a picture (fleet order 2026-08-11). */}
                      <GlitchProx proximity={s.proximity} accent={s.accent_hex} />
                      <div className="absolute inset-0 bg-gradient-to-t from-background/90 to-transparent" />
                    </div>
                    <div className="absolute top-2 right-2"><RarityBadge rarity={s.rarity} className="text-[8px] px-1.5 py-0" /></div>
                    {s.quantity > 1 && <span className="absolute top-2 left-2 text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-black/60 border border-white/20 tabular-nums" data-testid={`inv-glitch-qty-${s.glitch_id}`}>x{s.quantity}</span>}
                    <div className="absolute bottom-0 inset-x-0 p-3">
                      <span className="inline-block mb-1 text-[8px] font-bold px-1.5 py-0.5 rounded" style={{ background: `${s.accent_hex || "#7CA842"}22`, color: s.accent_hex || "#7CA842" }}>GLITCH</span>
                      <p className="text-xs font-bold leading-tight line-clamp-2">{s.name}</p>
                      <span className="text-[10px] text-gold font-semibold" data-testid={`inv-glitch-uses-${s.glitch_id}`}>{(s.uses ?? 0) === 1 ? "1 uso" : `${s.uses ?? 0} usos`}</span>
                      {inGame ? (
                        <button onClick={() => applyGlitchSkin(s)} disabled={applyingGlitch === s.glitch_id} data-testid={`apply-glitch-${s.glitch_id}`}
                          className="mt-2 w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-60">
                          <Sparkles size={11} /> {applyingGlitch === s.glitch_id ? "Aplicando…" : "Aplicar al dino"}
                        </button>
                      ) : (
                        <span className="mt-2 block text-[9px] text-muted-foreground text-center">Entra al juego para aplicarla</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          </>
          )}
        </>
      )}

      <AnimatePresence>
        {crateOpen && <CrateRoulette item={crateOpen} onClose={() => setCrateOpen(null)} onDone={reloadInventory} />}
      </AnimatePresence>

      <AnimatePresence>
        {eggOpen && <EggRoulette egg={eggOpen} onClose={() => setEggOpen(null)} onDone={reloadInventory} />}
      </AnimatePresence>

      <AnimatePresence>
        {manageDino && <DinoManageModal item={manageDino} activeDinoSlug={activeDinoSlug} inGame={inGame} play={play} onClose={() => setManageDino(null)} onDone={reloadInventory} />}
      </AnimatePresence>

      <AnimatePresence>
        {tokenActive && (
          <TokenRedeemModal
            token={{ ...tokenActive, liveEnabled: bpLiveTokens }}
            onClose={() => setTokenActive(null)}
            onDone={(effects) => {
              setTokenActive(null);
              play("reward");
              toast.success("Token usado", { description: (effects || []).join(" · ") || "Aplicado." });
              reloadInventory();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

export default InventoryPanel;
