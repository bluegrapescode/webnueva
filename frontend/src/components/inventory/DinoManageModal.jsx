import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Check, Dna, Trash2, Store as StoreIcon, Gavel, Rocket, Lock, Activity, Heart, Zap, Drumstick, Droplet, Sparkles, Crown, TrendingUp, Tag, Pencil } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useAuth } from "@/context/AuthContext";
import { HudCorners, HudGrid, SegBar } from "@/components/common/Hud";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import {
  intOrNull, fmtCoin, fmtDur, feePreview, readQuote, EMPTY_QUOTE,
  durationTiers, defaultTier, suggestionRows, suggestionSubtitle, railSentence,
  fallbackBaseNotice, salesHistoryLine, validatePrice, submitBlockReason,
  newRequestId, attemptSettled,
} from "@/lib/marketPricing";

// THE SECOND SELL SURFACE. It posts to the same /market/list as the Mercado
// page, so it reads the same rules from the same payload through the same
// module. It used to carry FIVE constants of its own — two duration lists, two
// listing-fee percentages and a mutation-slot cap — which is two surfaces free
// to disagree with each other AND with the server about what a listing costs.
// All five are gone.
//
// (A jest source pin asserts they stay gone — see lib/marketPricing.test.js.
// It greps this file, so do not reintroduce their names even in a comment.)

const EM = "#7CA842";

const VITALS = [
  { k: "growth", label: "Growth", icon: TrendingUp, color: "#7CA842" },
  { k: "health", label: "Health", icon: Heart, color: "#F4547B" },
  { k: "stamina", label: "Stamina", icon: Zap, color: "#EAB308" },
  { k: "hunger", label: "Hunger", icon: Drumstick, color: "#F59E0B" },
  { k: "thirst", label: "Thirst", icon: Droplet, color: "#38BDF8" },
];

const PRIME_BENEFITS = ["Bonus mutation slot", "Increased Weight, Speed & Bite Force", "Higher Attack, Blood Pool & Fracture HP", "Larger unique adult model"];

const MUT_GROUPS = [
  { key: "child", label: "Child Mutations", prefix: "Child" },
  { key: "parent", label: "Parent Mutations", prefix: "Parent" },
  { key: "elder_a", label: "Elder · Set A", prefix: "Elder A" },
  { key: "elder_b", label: "Elder · Set B", prefix: "Elder B" },
];
// NOTE these are the LEGACY inventory lane's numbers and they intentionally do
// NOT match the vault editor's ladder (owner ruling 2026-07-25: 25/50/75 + a
// Prime-only 4th at 75%). They are left alone on purpose: this modal's save
// posts to /inventory/dino/{id}/mutation-groups, whose server-side twin
// (server.py CHILD_GROWTH_REQ_*) REBUILDS the stored array and drops any slot
// its gate calls locked — so tightening the first rung here would silently
// wipe a stored mutation on the next save of a 20-24% inventory dino. Changing
// this pair is an owner decision, not a display tweak: it must move together
// with server.py and needs a look at what is still in db.inventory first.
const CHILD_REQ_PRIME = [20, 50, 100, 100];
const CHILD_REQ_BASE = [20, 50, 100];
const GROWTH_MULTIPLIER = 3; // server growth rate multiplier
const fmtGrowthMin = (mins) => {
  const t = Math.max(1, Math.round(mins));
  const h = Math.floor(t / 60), m = t % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
};
const GROUP_SLOTS = 4;

export const DinoManageModal = ({ item, onClose, onDone, play, activeDinoSlug, inGame: inGameProp }) => {
  const { refresh } = useAuth();
  const [tab, setTab] = useState("overview");
  const [allMuts, setAllMuts] = useState(null);
  const [groups, setGroups] = useState(() => {
    if (item.mutation_groups) return { child: [], parent: [], elder_a: [], elder_b: [], ...item.mutation_groups };
    const flat = item.mutations || [];
    return { child: flat.slice(0, 4), parent: flat.slice(4, 8), elder_a: [], elder_b: [] };
  });
  const [editSlot, setEditSlot] = useState(null); // { group, i } | null
  const [entombCount, setEntombCount] = useState(item.entomb_count || 0);
  const [species, setSpecies] = useState(null);
  const [saving, setSaving] = useState(false);
  const [sellMode, setSellMode] = useState(null); // null | "sale" | "auction"
  const [confirmRelease, setConfirmRelease] = useState(false);
  const [quote, setQuote] = useState(EMPTY_QUOTE);
  const [quoteState, setQuoteState] = useState("idle"); // idle | loading | ready | error
  const [mineCount, setMineCount] = useState(null);
  const seededRef = React.useRef(false);
  const reqIdRef = React.useRef(null);

  useEffect(() => {
    if (!sellMode || !item?.id) return;
    let cancelled = false;
    // Sale and auction are DIFFERENT attempts: carrying an id across the switch
    // would let a replay hand back the other type's stored result.
    reqIdRef.current = null;
    setQuoteState("loading");
    // The dino's IDENTITY, never a mutation count — the server counts the row
    // itself. The price is the SELLER's: the suggestion seeds the field ONCE
    // and is then left alone.
    api.marketSuggestedPrice({ inv_id: item.id, slug: item.dino_slug })
      .then((r) => {
        if (cancelled) return;
        const q = readQuote(r.data);
        setQuote(q);
        setQuoteState(q.ok ? "ready" : "error");
        if (q.suggested !== null && !seededRef.current) {
          seededRef.current = true;
          setPrice(String(q.suggested));
        }
      })
      .catch(() => { if (!cancelled) { setQuote(EMPTY_QUOTE); setQuoteState("error"); } });
    api.marketMine().then((r) => setMineCount((r.data || []).length)).catch(() => setMineCount(null));
    return () => { cancelled = true; };
  }, [sellMode, item?.id, item?.dino_slug]);
  const [title, setTitle] = useState(item.custom_name || (item.name || "").replace(/ Slot$/, ""));
  const [displayName, setDisplayName] = useState(item.custom_name || (item.name || "").replace(/ Slot$/, ""));
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [price, setPrice] = useState("");
  // Seeded from the payload's own tier list — this panel no longer keeps a copy.
  const [durationHours, setDurationHours] = useState("");

  const isPrime = item.tier === "prime";
  const cleanName = useMemo(() => (item.name || "").replace(/ Slot$/, ""), [item.name]);
  // Moving to the vault has no in-game/species precondition — the vault's own
  // Recuperar gate enforces the Evrima same-species rule at redeem time.
  const sameSpecies = activeDinoSlug && activeDinoSlug === item.dino_slug;
  const inGame = !!inGameProp;                       // real RCON presence on the game server
  // While in-game: first deploy is free; if you already play a dino you may only restore the SAME species.
  const canDeploy = inGame && (!activeDinoSlug || sameSpecies);
  const growth = Math.round(item.saved_growth ?? item.growth ?? 0);
  const vitalVal = (k) => (k === "growth" ? growth : (item[k] ?? 100));

  useEffect(() => {
    if (item.dino_slug) api.dinosaur(item.dino_slug).then((r) => setSpecies(r.data)).catch(() => {});
  }, [item.dino_slug]);
  // Ask for THIS species' catalog. Without the slug the route answers with the
  // unfiltered list, and since that list became the full catalog it would offer a
  // herbivore the carnivore-only mutations - which move-to-vault then drops silently,
  // so the player would lose a pick they were shown and allowed to save.
  useEffect(() => {
    if (tab === "mutations" && allMuts === null) {
      api.mutations(item.dino_slug).then((r) => setAllMuts(r.data.mutations)).catch(() => setAllMuts([]));
    }
  }, [tab, allMuts, item.dino_slug]);

  const mutName = (k) => allMuts?.find((m) => m.key === k)?.name || k;
  const usedKeys = new Set(MUT_GROUPS.flatMap((g) => (groups[g.key] || []).filter(Boolean)));
  const totalMuts = usedKeys.size;
  const childReqs = isPrime ? CHILD_REQ_PRIME : CHILD_REQ_BASE;
  const groupSlotCount = (gk) => (gk === "child" ? childReqs.length : GROUP_SLOTS);
  const slotUnlocked = (gk, i) => {
    if (gk === "child") return growth >= (childReqs[i] ?? 999);
    if (gk === "parent") return true;
    if (gk === "elder_a") return isPrime && entombCount >= 1;
    if (gk === "elder_b") return isPrime && entombCount >= 2;
    return false;
  };
  const slotLock = (gk, i) => {
    if (gk === "child") return { label: `Crece ${childReqs[i]}%`, kind: "grow" };
    return { label: "Bloqueada", kind: "locked" };
  };
  const setSlot = (gk, i, key) => {
    setGroups((prev) => {
      const arr = [...(prev[gk] || [])];
      while (arr.length <= i) arr.push(null);
      arr[i] = key;
      return { ...prev, [gk]: arr };
    });
    setEditSlot(null);
    play?.("click");
  };
  const startRename = () => { setNameDraft(displayName); setEditingName(true); play?.("click"); };
  const saveName = async () => {
    const nm = nameDraft.trim().slice(0, 40);
    try {
      await api.renameDino(item.id, nm);
      const finalName = nm || (item.name || "").replace(/ Slot$/, "");
      setDisplayName(finalName); setTitle(finalName); setEditingName(false);
      play?.("success"); toast.success("Nombre actualizado");
      await onDone?.();
    } catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "No se pudo renombrar"); }
  };
  const saveMuts = async () => {
    setSaving(true);
    try { await api.editDinoMutationGroups(item.id, groups); play?.("success"); toast.success("Mutaciones actualizadas"); await onDone?.(); onClose(); }
    catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };
  // Moves the dino into La Bóveda, where Recuperar actually spawns it. This
  // used to claim "canjeado en tu partida" while nothing reached the game.
  const deploy = async () => {
    setSaving(true);
    try {
      await api.deployDino(item.id);
      play?.("success");
      toast.success(`${cleanName} está en tu Bóveda`, {
        description: "Entra al juego como esa especie y pulsa Recuperar para tenerlo.",
      });
      await onDone?.();
      onClose();
    } catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "No se pudo mover a la Bóveda"); }
    finally { setSaving(false); }
  };
  const release = async () => {
    setSaving(true);
    try { await api.releaseDino(item.id); play?.("close"); toast.success(`${cleanName} released`); setConfirmRelease(false); await onDone?.(); onClose(); }
    catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "Failed"); setConfirmRelease(false); }
    finally { setSaving(false); }
  };
  const durs = durationTiers(quote, sellMode);
  const durKey = durs ? durs.join(",") : "";
  // Snap the chosen duration into whatever the payload says is legal.
  useEffect(() => {
    if (!durs) return;
    setDurationHours((h) => (durs.includes(Number(h)) ? h : defaultTier(durs)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durKey, sellMode]);
  // ...and DERIVE it too, so the one render between switching sale<->auction and
  // that effect firing can neither display nor SUBMIT the other list's tier.
  const hours = durs
    ? (durs.includes(Number(durationHours)) ? Number(durationHours) : defaultTier(durs))
    : null;

  const receipt = feePreview(intOrNull(price), quote.taxPct);
  const sellBlocked = sellMode
    ? submitBlockReason(quote, sellMode, quoteState === "ready" || quoteState === "error")
    : null;
  const priceCheck = validatePrice(price, quote);
  const priceError = String(price).trim() !== "" && !priceCheck.ok ? priceCheck.detail : null;
  const sugRows = suggestionRows(quote, cleanName);
  const sugSubtitle = suggestionSubtitle(quote, cleanName);
  const railLine = railSentence(quote);
  const fallbackLine = fallbackBaseNotice(quote);
  const historyLine = salesHistoryLine(quote, cleanName);

  const listDino = async () => {
    if (sellBlocked) { play?.("error"); toast.error(sellBlocked); return; }
    const v = validatePrice(price, quote);
    if (!v.ok) { play?.("error"); toast.error(v.detail); return; }
    if (!Number.isFinite(hours) || hours <= 0) {
      play?.("error"); toast.error("Elige una duración para la publicación."); return;
    }
    setSaving(true);
    // One id per ATTEMPT, kept across a dropped socket so an honest second click
    // replays instead of creating a second listing.
    if (!reqIdRef.current) reqIdRef.current = newRequestId();
    const rid = reqIdRef.current;
    try {
      await api.marketCreate({
        inv_id: item.id, type: sellMode, price: v.price,
        duration_hours: hours, title: title.trim(), client_request_id: rid,
      });
      reqIdRef.current = null;
      play?.("purchase");
      toast.success("¡Publicación creada!", { description: `${cleanName} ya está en ${sellMode === "auction" ? "subasta" : "el mercado"}.` });
      await refresh(); await onDone?.(); onClose();
    } catch (e) {
      if (attemptSettled(e)) reqIdRef.current = null;
      play?.("error"); toast.error(e?.response?.data?.detail || "No se pudo publicar");
    } finally { setSaving(false); }
  };

  const TABS = [
    { k: "overview", label: "Overview", icon: Activity },
    { k: "perks", label: "Perks", icon: Sparkles },
    { k: "mutations", label: "Mutations", icon: Dna },
    { k: "prime", label: "Prime", icon: Crown },
  ];
  const footerBtn = "relative inline-flex items-center justify-center gap-1.5 px-2 py-3 text-[11px] font-bold uppercase tracking-wider transition-all";

  return (
    <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={() => { onClose(); play?.("close"); }} />
      <motion.div initial={{ scale: 0.96, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 16 }}
        className="relative w-full max-w-2xl overflow-hidden max-h-[92vh] flex flex-col border border-gold/25"
        style={{ background: "#080d0b", borderRadius: 2 }} data-testid="dino-manage-modal">
        <HudCorners />

        {/* Terminal header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gold/15 shrink-0 font-mono">
          <p className="text-[11px] tracking-widest uppercase">
            <span className="text-gold">● Specimen Dossier</span>
            <span className="text-muted-foreground/60"> · UID {item.recovery_id || String(item.id).slice(0, 24)}</span>
          </p>
          <button onClick={() => { onClose(); play?.("close"); }} data-testid="dino-manage-close" className="p-1.5 hover:bg-white/10 transition-colors"><X size={16} /></button>
        </div>

        {/* Hero */}
        <div className="relative h-44 shrink-0 overflow-hidden border-b border-white/5">
          <HudGrid />
          <span className="absolute inset-0 flex items-center justify-center font-display font-black uppercase tracking-tighter text-gold/[0.07] leading-none select-none pointer-events-none whitespace-nowrap" style={{ fontSize: "7rem" }}>{item.dino_slug}</span>
          <img src={item.image} alt="" className="relative w-full h-full object-contain p-3" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#080d0b] via-transparent to-transparent" />
          <div className="absolute bottom-3 left-5 right-5 flex items-end justify-between">
            <div className="min-w-0">
              <p className="label-overline text-[10px] text-gold">{cleanName.toUpperCase()}</p>
              {editingName ? (
                <div className="flex items-center gap-1.5 mt-1">
                  <input autoFocus value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} maxLength={40}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") setEditingName(false); }}
                    className="bg-black/50 border border-gold/50 px-2 py-1 text-lg font-display font-extrabold focus:outline-none focus:border-gold w-48" style={{ borderRadius: 2 }} data-testid="rename-input" />
                  <button onClick={saveName} data-testid="rename-save" className="p-1.5 bg-gold text-background" style={{ borderRadius: 2 }}><Check size={15} /></button>
                  <button onClick={() => setEditingName(false)} className="p-1.5 border border-white/20" style={{ borderRadius: 2 }}><X size={15} /></button>
                </div>
              ) : (
                <button onClick={startRename} data-testid="rename-btn" className="group inline-flex items-center gap-2 mt-1" title="Renombrar dino">
                  <h3 className="font-display font-extrabold text-3xl leading-none truncate max-w-[16rem]">{displayName}</h3>
                  <Pencil size={15} className="text-muted-foreground group-hover:text-gold transition-colors shrink-0" />
                </button>
              )}
              <div className="mt-1.5"><RarityBadge rarity={item.rarity} /></div>
            </div>
            <div className="text-right">
              <p className="label-overline text-[9px] text-muted-foreground">Crecimiento</p>
              <p className="font-display font-black text-3xl text-gold leading-none">{growth}<span className="text-base">%</span></p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/10 shrink-0">
          {TABS.map((t) => (
            <button key={t.k} onClick={() => { setTab(t.k); play?.("hover"); }} data-testid={`manage-tab-${t.k}`}
              className={`relative flex-1 inline-flex items-center justify-center gap-1.5 py-3 text-[11px] font-bold uppercase tracking-wider transition-colors ${tab === t.k ? "text-gold" : "text-muted-foreground hover:text-foreground"}`}>
              <t.icon size={13} /> {t.label}
              {tab === t.k && <span className="absolute -bottom-px left-3 right-3 h-0.5 bg-gold" style={{ boxShadow: `0 0 8px ${EM}` }} />}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1">
          {tab === "overview" && (
            <div className="space-y-4" data-testid="manage-overview">
              {VITALS.map((v) => {
                const val = vitalVal(v.k);
                return (
                  <div key={v.k}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"><v.icon size={13} style={{ color: v.color }} /> {v.label}</span>
                      <span className="font-display font-bold text-[13px] tabular-nums" style={{ color: v.color }}>{val}%</span>
                    </div>
                    <SegBar value={val} color={v.color} />
                  </div>
                );
              })}
              {species && (
                <div className="grid grid-cols-3 gap-2 pt-1">
                  {[["SPD", species.stats?.speed], ["WGT", species.stats?.weight], ["DMG", species.stats?.damage]].map(([l, val]) => (
                    <div key={l} className="border border-white/10 bg-white/[0.02] py-2 text-center" style={{ borderRadius: 2 }}>
                      <p className="font-display font-bold tabular-nums">{val?.toLocaleString?.() ?? val ?? "—"}</p>
                      <p className="text-[9px] label-overline text-muted-foreground">{l}</p>
                    </div>
                  ))}
                </div>
              )}
              {species?.growth_minutes && (
                <div className="flex items-center justify-between border border-gold/20 bg-gold/[0.03] px-3 py-2.5 mt-1" style={{ borderRadius: 2 }} data-testid="manage-growth-time">
                  <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"><TrendingUp size={13} className="text-gold" /> Tiempo de crecimiento</span>
                  <span className="text-right">
                    <span className="font-display font-bold text-gold tabular-nums">{fmtGrowthMin(species.growth_minutes / GROWTH_MULTIPLIER)}</span>
                    <span className="text-[10px] text-muted-foreground"> · x{GROWTH_MULTIPLIER}</span>
                    <span className="block text-[9px] text-muted-foreground/70 tabular-nums">vainilla {species.stats?.growth_time}</span>
                  </span>
                </div>
              )}
            </div>
          )}

          {tab === "perks" && (
            <div className="space-y-2" data-testid="manage-perks">
              {(species?.abilities || []).length === 0 && <p className="text-sm text-muted-foreground text-center py-6">Loading species perks…</p>}
              {(species?.abilities || []).map((a, i) => (
                <div key={i} className="flex items-center gap-3 border border-gold/15 bg-gold/[0.04] px-3 py-2.5" style={{ borderRadius: 2 }}>
                  <span className="w-7 h-7 flex items-center justify-center bg-gold/10 border border-gold/30 shrink-0" style={{ borderRadius: 2 }}><Sparkles size={13} className="text-gold" /></span>
                  <span className="text-sm font-semibold">{a}</span>
                </div>
              ))}
              <p className="text-[11px] text-muted-foreground pt-1">{species?.diet ? `${species.diet} · ` : ""}{species?.type}</p>
            </div>
          )}

          {tab === "mutations" && (
            <div data-testid="manage-mutations" className="relative">
              <div className="flex items-center justify-between mb-3">
                <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Dna size={12} className="text-gold" /> Mutaciones</p>
                <span className="text-[11px] tabular-nums text-gold" data-testid="manage-mut-count">{totalMuts}/16 activas</span>
              </div>

              {/* Entomb lineage status (read-only — Entomb is an in-game action) */}
              <div className="flex items-center justify-between gap-2 border border-gold/20 bg-gold/[0.03] px-3 py-2 mb-4" style={{ borderRadius: 2 }} data-testid="manage-entomb-bar">
                <div className="min-w-0">
                  <p className="label-overline text-[9px] text-gold inline-flex items-center gap-1"><Crown size={11} /> Linaje Entomb · Gen {entombCount}/2</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">
                    {entombCount >= 2 ? "Linaje máximo · Elder Set A y B desbloqueados" : entombCount === 1 ? "Elder · Set A desbloqueado · haz Entomb en el juego para el Set B" : "Sobrevive hasta Elder y haz Entomb en el juego para desbloquear los Elder Sets"}
                  </p>
                </div>
                <span className="shrink-0 flex items-center gap-1">
                  {[1, 2].map((g) => (
                    <span key={g} className={`w-2.5 h-2.5 border ${entombCount >= g ? "bg-gold border-gold" : "border-white/25"}`} style={{ borderRadius: 1 }} data-testid={`entomb-pip-${g}`} />
                  ))}
                </span>
              </div>

              {allMuts === null ? <p className="text-xs text-muted-foreground py-4 text-center">Cargando…</p> : (
                <div className="space-y-4 mb-4">
                  {MUT_GROUPS.map((g) => {
                    const vals = groups[g.key] || [];
                    const n = groupSlotCount(g.key);
                    return (
                      <div key={g.key} data-testid={`manage-mut-group-${g.key}`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5 whitespace-nowrap"><Dna size={11} /> {g.label}</p>
                          <span className="h-px flex-1 bg-white/10" />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {Array.from({ length: n }).map((_, i) => {
                            const val = vals[i];
                            const unlocked = slotUnlocked(g.key, i);
                            const lk = unlocked ? null : slotLock(g.key, i);
                            return (
                              <div key={i} className={`flex items-center gap-2 border px-2.5 py-2 ${val ? "border-gold/30 bg-gold/[0.04]" : unlocked ? "border-white/10 bg-white/[0.02]" : "border-white/[0.06] bg-white/[0.01]"}`} style={{ borderRadius: 2 }} data-testid={`manage-mut-slot-${g.key}-${i}`}>
                                <span className="label-overline text-[8px] text-muted-foreground shrink-0 whitespace-nowrap">{g.prefix} #{i + 1}</span>
                                <span className={`flex-1 min-w-0 text-[11px] font-semibold leading-tight truncate ${val ? "" : "text-muted-foreground/40 italic"}`}>{val ? mutName(val) : "— Ninguna —"}</span>
                                {unlocked ? (
                                  <button onClick={() => { setEditSlot({ group: g.key, i }); play?.("click"); }} data-testid={`manage-mut-edit-${g.key}-${i}`}
                                    className="shrink-0 border border-gold/40 text-gold text-[9px] font-bold uppercase tracking-wider px-1.5 py-1 hover:bg-gold/10 transition-colors" style={{ borderRadius: 2 }}>Editar</button>
                                ) : (
                                  <span className={`shrink-0 inline-flex items-center gap-1 border text-[9px] font-bold uppercase tracking-wider px-1.5 py-1 ${lk.kind === "grow" ? "border-white/15 text-muted-foreground/70" : "border-white/10 text-muted-foreground/45"}`} style={{ borderRadius: 2 }} data-testid={`manage-mut-lock-${g.key}-${i}`}>
                                    {lk.kind === "grow" ? <><TrendingUp size={9} /> {lk.label}</> : <><Lock size={9} /> {lk.label}</>}
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <button onClick={saveMuts} disabled={saving} data-testid="manage-save-mutations" className="w-full bg-gold text-background font-bold py-2.5 text-sm hover:brightness-110 transition-all disabled:opacity-60" style={{ borderRadius: 2 }}>{saving ? "Guardando…" : "Guardar mutaciones"}</button>

              {/* Slot picker */}
              <AnimatePresence>
                {editSlot !== null && allMuts && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-20 flex flex-col" data-testid="manage-mut-picker">
                    <div className="absolute inset-0 bg-[#0b0906]/95 backdrop-blur-sm" onClick={() => setEditSlot(null)} />
                    <div className="relative flex items-center justify-between mb-2 pt-1">
                      <p className="label-overline text-[10px] text-gold">{MUT_GROUPS.find((g) => g.key === editSlot.group)?.prefix} #{editSlot.i + 1} · elige mutación</p>
                      <button onClick={() => setEditSlot(null)} className="p-1 hover:bg-white/10" style={{ borderRadius: 2 }}><X size={14} /></button>
                    </div>
                    <div className="relative flex-1 overflow-y-auto space-y-1.5 pr-1">
                      <button onClick={() => setSlot(editSlot.group, editSlot.i, null)} className="w-full flex items-center gap-2 border border-crimson/40 text-crimson px-2.5 py-2 text-left hover:bg-crimson/10 transition-colors" style={{ borderRadius: 2 }}>
                        <Trash2 size={13} /> <span className="text-[12px] font-semibold">Vaciar ranura</span>
                      </button>
                      {allMuts.map((m) => {
                        const cur = (groups[editSlot.group] || [])[editSlot.i];
                        const used = usedKeys.has(m.key) && cur !== m.key;
                        const sel = cur === m.key;
                        return (
                          <button key={m.key} onClick={() => !used && setSlot(editSlot.group, editSlot.i, m.key)} disabled={used} data-testid={`manage-mut-pick-${m.key}`}
                            className={`w-full flex items-center gap-2 border px-2.5 py-2 text-left transition-all ${sel ? "border-gold bg-gold/10" : used ? "border-white/5 opacity-35 cursor-not-allowed" : "border-white/10 hover:border-gold/40"}`} style={{ borderRadius: 2 }}>
                            <span className={`w-4 h-4 shrink-0 flex items-center justify-center border ${sel ? "bg-gold border-gold text-background" : "border-white/25"}`} style={{ borderRadius: 2 }}>{sel ? <Check size={11} /> : null}</span>
                            <span className="flex-1 min-w-0"><span className="block text-[12px] font-semibold leading-tight">{m.name}</span><span className="block text-[10px] text-muted-foreground line-clamp-1">{m.desc}</span></span>
                          </button>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {tab === "prime" && (
            <div data-testid="manage-prime">
              {isPrime ? (
                <div className="border border-gold/40 bg-gold/[0.08] p-4" style={{ borderRadius: 2 }}>
                  <p className="font-display font-bold text-gold inline-flex items-center gap-2 mb-2"><Crown size={16} /> Prime Elder</p>
                  <ul className="space-y-1.5">
                    {PRIME_BENEFITS.map((b) => (
                      <li key={b} className="text-[12px] text-muted-foreground inline-flex items-center gap-2"><Check size={13} className="text-gold shrink-0" /> {b}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="border border-white/10 p-4 text-center" style={{ borderRadius: 2 }}>
                  <Crown size={22} className="text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm font-semibold">Not a Prime Elder</p>
                  <p className="text-xs text-muted-foreground mt-1">Deploy this dino and complete the Prime Elder objectives in Live Dino to promote it.</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="grid grid-cols-5 border-t border-white/10 shrink-0 divide-x divide-white/10">
          <div className={`${footerBtn} ${inGame ? "text-gold" : "text-crimson"}`} data-testid="manage-ingame-status">
            <span className={`w-1.5 h-1.5 rounded-full ${inGame ? "bg-gold" : "bg-crimson"}`} /> {inGame ? "En Juego" : "No En Juego"}
          </div>
          <button onClick={() => { setSellMode("sale"); play?.("click"); }} data-testid="manage-sell-market" className={`${footerBtn} text-gold hover:bg-gold/10`}><StoreIcon size={13} /> Sell</button>
          <button onClick={() => { setSellMode("auction"); play?.("click"); }} data-testid="manage-auction" className={`${footerBtn} text-gold hover:bg-gold/10`}><Gavel size={13} /> Auction</button>
          <button onClick={() => { setConfirmRelease(true); play?.("click"); }} disabled={saving} data-testid="manage-release" className={`${footerBtn} text-crimson hover:bg-crimson/10 disabled:opacity-40`}><Trash2 size={13} /> Release</button>
          <button onClick={deploy} disabled={saving} data-testid="manage-deploy"
            title="Mover este dino a tu Bóveda para recuperarlo en el juego"
            className={`${footerBtn} bg-gold text-background hover:brightness-110 disabled:opacity-40`}>
            <Rocket size={13} /> A la Bóveda
          </button>
        </div>

        {/* Sell overlay */}
        <ConfirmModal
          open={confirmRelease}
          onClose={() => setConfirmRelease(false)}
          onConfirm={release}
          loading={saving}
          tone="danger"
          title={`¿Liberar a ${cleanName}?`}
          message={<>Este dinosaurio y todo su progreso (crecimiento y mutaciones) se eliminarán de tu inventario para siempre.</>}
          warning="ESTO NO SE PUEDE DESHACER"
          confirmLabel="Liberar"
          abortLabel="Abortar"
        />
        <AnimatePresence>          {sellMode && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-30 flex items-center justify-center p-4" data-testid="manage-sell">
              <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => setSellMode(null)} />
              <motion.div initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, y: 10 }}
                className="relative w-full max-w-sm max-h-[90vh] overflow-y-auto border border-gold/30 flex flex-col"
                style={{ background: "#0b0906", borderRadius: 2, borderTop: `2px solid ${EM}` }}>
                {/* Header */}
                <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
                  <span className="w-9 h-9 flex items-center justify-center border border-gold/40 bg-gold/[0.08] shrink-0" style={{ borderRadius: 2 }}>
                    {sellMode === "auction" ? <Gavel size={16} className="text-gold" /> : <Tag size={16} className="text-gold" />}
                  </span>
                  <div>
                    <h4 className="font-display font-extrabold text-base leading-none">{sellMode === "auction" ? "Publicar Subasta" : "Publicar en el Mercado"}</h4>
                    <p className="text-[12px] text-muted-foreground mt-0.5">{displayName}</p>
                  </div>
                </div>

                <div className="px-4 pb-4 space-y-3">
                  {/* The suggestion, itemised, so the number is a claim the
                      seller can check rather than a magic figure. */}
                  <div className="border border-gold/25 bg-gold/[0.04] p-3" style={{ borderRadius: 2 }} data-testid="suggested-price-box">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="inline-flex items-center gap-1.5 label-overline text-[10px] text-gold font-bold"><TrendingUp size={12} /> Precio sugerido</span>
                      <span className="font-display font-extrabold text-gold text-[13px] tabular-nums shrink-0" data-testid="suggested-price-value">
                        {quoteState === "loading" ? "Calculando…" : fmtCoin(quote.suggested)}
                      </span>
                    </div>
                    {sugRows.length > 0 && (
                      <div className="space-y-1 border-t border-gold/20 pt-2" data-testid="suggested-price-breakdown">
                        {sugRows.map((r) => (
                          <div key={r.key} className="flex items-baseline justify-between gap-2 text-[11px]">
                            <span className="min-w-0 truncate text-muted-foreground">{r.label}</span>
                            <span className="shrink-0 tabular-nums font-semibold">{r.sign}{fmtCoin(r.value)}</span>
                          </div>
                        ))}
                        <div className="flex items-baseline justify-between gap-2 border-t border-gold/20 pt-1 text-[11px]">
                          <span className="text-muted-foreground font-bold">Total</span>
                          <span className="shrink-0 tabular-nums font-display font-extrabold text-gold">{fmtCoin(quote.suggested)}</span>
                        </div>
                      </div>
                    )}
                    {sugSubtitle && <p className="mt-2 text-[10px] leading-snug text-muted-foreground">{sugSubtitle}</p>}
                    <button type="button" onClick={() => { if (quote.suggested !== null) { setPrice(String(quote.suggested)); play?.("click"); } }}
                      disabled={quote.suggested === null} data-testid="suggested-price-btn"
                      className="mt-2.5 w-full border border-gold/40 bg-gold/[0.06] text-gold font-bold uppercase tracking-wider text-[11px] py-2 hover:bg-gold/15 transition-all disabled:opacity-50" style={{ borderRadius: 2 }}>
                      Usar este precio
                    </button>
                  </div>

                  {fallbackLine && (
                    <p className="text-[11px] leading-snug text-gold" data-testid="list-base-fallback">{fallbackLine}</p>
                  )}
                  {historyLine && (
                    <p className="text-[10px] leading-snug text-muted-foreground/80" data-testid="list-sales-history">{historyLine}</p>
                  )}

                  {/* THE PRICE IS THE SELLER'S. min/max are the server's rails. */}
                  <div>
                    <label className="label-overline text-[10px] text-gold font-bold block mb-1">{sellMode === "auction" ? "Puja inicial" : "Precio"} (PrimeMeat)</label>
                    <input type="number" inputMode="numeric" step={1} data-testid="list-price"
                      className="w-full bg-black/40 border border-white/12 px-3 py-2.5 text-base font-display font-bold tabular-nums focus:outline-none focus:border-gold/60"
                      style={{ borderRadius: 2 }}
                      value={price} onChange={(e) => setPrice(e.target.value)}
                      min={quote.min !== null ? quote.min : undefined}
                      max={quote.max !== null ? quote.max : undefined}
                      placeholder={quote.suggested !== null ? String(quote.suggested) : (quoteState === "loading" ? "Calculando…" : "")} />
                    {railLine && <p className="text-[10px] text-muted-foreground mt-1 leading-snug" data-testid="list-rail">{railLine}</p>}
                    {priceError && <p className="text-[10px] text-crimson mt-1 leading-snug" data-testid="list-price-error">{priceError}</p>}
                  </div>

                  {/* Duration — the tiers are the payload's, never a local copy */}
                  {durs ? (
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="label-overline text-[10px] text-gold font-bold">Duración{sellMode === "auction" ? " (subasta)" : ""}</span>
                        <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                          {fmtDur(hours)}{quote.taxPct !== null ? ` · ${quote.taxPct}% comisión` : ""}
                        </span>
                      </div>
                      <input type="range" min={0} max={durs.length - 1} step={1}
                        value={Math.max(0, durs.indexOf(hours))}
                        onChange={(e) => setDurationHours(durs[Number(e.target.value)])}
                        className="w-full accent-gold" data-testid="list-duration" />
                      <div className="flex justify-between text-[9px] text-muted-foreground/70 mt-1 tabular-nums">
                        {durs.map((h) => (
                          <span key={h} className={hours === h ? "text-gold font-bold" : ""}>{fmtDur(h)}</span>
                        ))}
                      </div>
                    </div>
                  ) : quoteState === "ready" ? (
                    <p className="text-[10px] leading-snug text-crimson" data-testid="list-duration-missing">
                      No pudimos leer las duraciones permitidas para este tipo de publicación. Avísale a un administrador.
                    </p>
                  ) : null}

                  {/* The net is the headline, not the percentage. */}
                  <div className="border border-white/10 bg-black/30 p-3 space-y-1.5 text-[13px]" style={{ borderRadius: 2 }} data-testid="list-receipt">
                    <div className="flex justify-between gap-2"><span className="text-muted-foreground">Precio de venta</span><span className="font-display font-bold tabular-nums shrink-0">{fmtCoin(intOrNull(price))}</span></div>
                    <div className="flex justify-between gap-2"><span className="min-w-0 text-muted-foreground">Comisión de plataforma{quote.taxPct !== null ? ` (${quote.taxPct}%)` : ""}</span><span className="font-semibold text-crimson tabular-nums shrink-0">{receipt.ok ? `−${fmtCoin(receipt.tax)}` : "—"}</span></div>
                    <div className="border-t border-white/10 pt-1.5 flex justify-between gap-2"><span className="font-bold">Recibes al vender</span><span className="font-display font-extrabold text-gold tabular-nums shrink-0" data-testid="list-proceeds">{receipt.ok ? fmtCoin(receipt.net) : "—"}</span></div>
                  </div>

                  {sellBlocked && <p className="text-[10px] leading-snug text-crimson" data-testid="list-blocked">{sellBlocked}</p>}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-white/10 mt-auto">
                  <span className="label-overline text-[10px] text-gold tabular-nums" data-testid="list-active-count">{mineCount ?? 0} activas</span>
                  <div className="flex gap-2">
                    <button onClick={() => setSellMode(null)} className="border border-white/15 px-4 py-2 text-[12px] font-bold uppercase tracking-wide hover:bg-white/5 transition-colors" style={{ borderRadius: 2 }}>Cancelar</button>
                    <button onClick={listDino} disabled={saving || !!sellBlocked} data-testid="confirm-list-dino" className="inline-flex items-center gap-1.5 bg-gold text-background font-bold uppercase tracking-wide text-[12px] px-4 py-2 hover:brightness-110 transition-all disabled:opacity-60" style={{ borderRadius: 2 }}>
                      {sellMode === "auction" ? <Gavel size={14} /> : <Tag size={14} />} {saving ? "Publicando…" : sellMode === "auction" ? "Iniciar subasta" : "Publicar venta"}
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
};
