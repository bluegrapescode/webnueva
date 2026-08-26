import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import { Gavel, Tag, Clock, Plus, X, ShoppingBag, Crown, Sparkles, Dna, TrendingUp, Undo2, ShieldCheck, Activity, Wheat, AlertTriangle, ArrowLeftRight, Handshake } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CoinChip } from "@/components/common/CoinChip";
import { RarityBadge } from "@/components/common/RarityBadge";
import { SkeletonCard } from "@/components/common/PageLoader";
import { SkinIcon } from "@/components/common/SkinIcon";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { SpeciesViewer3D } from "@/components/skin3d/SpeciesViewer3D";
import { useViewerSlot } from "@/components/skin3d/useViewerSlot";
import {
  URGENT_SECS, intOrNull, fmtCoin, fmtDur, fmtMutations,
  feePreview, readQuote, EMPTY_QUOTE, readListing, durationTiers, defaultTier,
  suggestionRows, suggestionSubtitle, railSentence, fallbackBaseNotice, salesHistoryLine,
  validatePrice, submitBlockReason, pickerLabel, gateEmptyState,
  nextBidLine, antisnipeLine, withdrawMessage, minBidRefusal, maxBidRefusal,
  newRequestId, attemptSettled,
} from "@/lib/marketPricing";
import { readTradeConfig, readMine, networkRefusal } from "@/lib/tradeRules";
import {
  readBoard, publishBlockReason, publishConfirm, closeCardConfirm,
  cardStatusLine, cardValueLine, boardEmptyState,
} from "@/lib/tradeBoard";
import TradeOffersPanel from "@/components/market/TradeOffersPanel";
import TradeOfferModal from "@/components/market/TradeOfferModal";

// Every rule this page quotes — the platform cut, the price rails, the legal
// durations, the bid step, the anti-snipe window, the withdraw fee, the growth
// minimum — is READ FROM THE SERVER PAYLOAD. This file used to keep its own
// listing-fee percentages and its own copies of the two duration tier lists,
// and that is how an input and a validator drift apart until the page promises
// a number the server refuses. The arithmetic and the copy now live in one
// place, @/lib/marketPricing, shared with the inventory sell panel so the two
// surfaces cannot describe the same listing two different ways.
//
// (A jest source pin asserts those literals stay gone — see marketPricing.test.
// It greps this file, so do not reintroduce their names even in a comment.)

// Remaining time on an ISO timestamp, recomputed every second. A missing or
// malformed `ends_at` reads as ended rather than rendering "NaNh NaNm NaNs" —
// a listing that is already gone must still render something sensible.
function countdownState(iso) {
  const end = new Date(iso).getTime();
  if (!Number.isFinite(end)) return { text: "—", secondsLeft: null, ended: true };
  const diff = end - Date.now();
  if (diff <= 0) return { text: "Finalizada", secondsLeft: 0, ended: true };
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return { text: `${h}h ${m}m ${s}s`, secondsLeft: Math.floor(diff / 1000), ended: false };
}

function useCountdown(iso) {
  const [state, setState] = useState(() => countdownState(iso));
  useEffect(() => {
    const tick = () => setState(countdownState(iso));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [iso]);
  return state;
}

// The clock turns crimson in the last minute. A colour change only: no new
// animation, so nothing here moves for a reduced-motion visitor that did not
// already move.
function ClockText({ text, secondsLeft, ended }) {
  const urgent = !ended && secondsLeft !== null && secondsLeft <= URGENT_SECS;
  return <span className={`tabular-nums ${urgent ? "text-crimson font-bold" : ""}`}>{text}</span>;
}

// Standalone clock, for the cards that need nothing else from the countdown.
// A card that ALSO needs the remaining seconds calls useCountdown once itself
// and renders <ClockText> off it, rather than running a second timer for the
// same fact.
function Countdown({ iso }) {
  return <ClockText {...useCountdown(iso)} />;
}

// Bóveda-card-parity media block for a listing: live walk-animated 3D model in
// the listing's exact stored skin (viewport- and slot-gated, same budget as the
// vault grid), falling back to the flat catalog image / generic icon. PRIME and
// ELDER read from the listing like the vault card reads its stored row.
function ListingMedia({ l }) {
  const boxRef = useRef(null);
  const inView = useInView(boxRef, { amount: 0.15 });
  const [viewerFailed, setViewerFailed] = useState(false);
  const slot = useViewerSlot(inView && !viewerFailed && !!l.species);
  const img = l.skin_image || l.image;
  return (
    <div ref={boxRef} className="aspect-square overflow-hidden relative" style={{ background: "#080d0b" }}>
      {slot ? (
        <SpeciesViewer3D
          species={l.species}
          active={!!l.species}
          skin={l.skin_view}
          interactive={false}
          liveSnapshotFallback={false}
          preferClip="walk"
          onStatus={(s) => { if (s === "error") setViewerFailed(true); }}
        />
      ) : img ? (
        <img src={img} alt={l.dino_name} className="w-full h-full object-contain p-2" />
      ) : (
        <SkinIcon rarity={l.rarity || "Common"} />
      )}
      <div className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-background/90 to-transparent pointer-events-none" />
      <div className="absolute top-3 right-3"><RarityBadge rarity={l.rarity} className="glass-strong px-2 py-1" /></div>
      <div className="absolute top-10 left-3 flex flex-col gap-1 pointer-events-none">
        {(l.prime || l.tier === "prime") && (
          <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 inline-flex items-center gap-0.5" data-testid={`market-prime-${l.id}`}><Crown size={9} /> PRIME</span>
        )}
        {l.is_elder && (
          <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-sky-400/20 text-sky-300 border border-sky-400/40 inline-flex items-center gap-0.5" data-testid={`market-elder-${l.id}`}><Sparkles size={9} /> ELDER</span>
        )}
      </div>
    </div>
  );
}

// Vault-card-style meta line: species + growth on the left, mutation count chip
// on the right. Growth is FLOORED and the count is the PRICED count — the same
// two numbers the gate and the price were built from, so a card can never
// advertise "80%" for an animal the 80% gate refuses, nor "4 mutaciones" for
// the 4+8 Deinosuchus the buyer is actually paying twelve for.
function ListingMeta({ l }) {
  const r = readListing(l);
  return (
    <div className="flex items-center justify-between gap-2 mb-3 mt-1 text-[11px] text-muted-foreground">
      <span className="truncate">
        {l.dino_name}{r.growthPct !== null ? ` · Crecimiento ${r.growthPct}%` : ""}
      </span>
      {r.mutations !== null && (
        <span className="inline-flex items-center gap-0.5 shrink-0" title="Mutaciones"><Dna size={10} /> {r.mutations}</span>
      )}
    </div>
  );
}

// The game's "|"-delimited mutation string ("Titan|None|Feral") -> real chips.
function mutChips(raw) {
  return String(raw || "").split("|").map((s) => s.trim()).filter((s) => s && s !== "None");
}

function InspectVitalRow({ label, color, cur, max }) {
  const hasMax = typeof max === "number" && Number.isFinite(max) && max > 0;
  const hasCur = typeof cur === "number" && Number.isFinite(cur);
  const pct = hasMax && hasCur ? Math.max(0, Math.min(100, (cur / max) * 100)) : null;
  if (pct === null) return null;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-display font-bold text-[11px] tabular-nums w-10 text-right" style={{ color }}>{Math.round(pct)}%</span>
    </div>
  );
}

function MutGroup({ label, chips, testId, note }) {
  return (
    <div data-testid={testId}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">{label} · {chips.length}</p>
      {chips.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">Ninguna</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {chips.map((m, i) => (
            <span key={`${m}-${i}`} className="text-[10px] font-semibold px-2 py-0.5 rounded-full glass border border-emerald/30 text-emerald inline-flex items-center gap-1">
              <Dna size={9} /> {m}
            </span>
          ))}
        </div>
      )}
      {note && <p className="text-[10px] text-muted-foreground/70 mt-1 leading-snug">{note}</p>}
    </div>
  );
}

// Buyer-side verification modal: renders the ESCROWED vault payload facts the
// backend derives server-side (listing.verify) — the exact mutations, vitals
// and diet the buyer will receive — so a mutation claim can be checked before
// paying. Only vault-sourced listings carry verify data.
//
// The headline count is the PRICED count, the same number the card advertises
// and the same number the price was built from. Inherited mutations are still
// shown, because the buyer is receiving them, but they are labelled as not
// priced — otherwise the buyer counts sixteen chips against a card that says
// twelve and reasonably concludes one of us is lying.
function InspectModal({ l, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!l) return null;
  const v = l.verify || {};
  const r = readListing(l);
  const own = mutChips(v.mutations);
  const inherited = mutChips(v.parent_mutations);
  const elder = mutChips(v.elder_mutations);
  const priced = r.mutations !== null ? r.mutations : own.length + elder.length;
  const stats = v.stats || {};
  const diet = v.diet || {};
  const dietPct = v.diet_pct || {};
  const growthPct = intOrNull(v.growth_pct) !== null ? intOrNull(v.growth_pct) : r.growthPct;
  const dietRows = [["a", "Carbohidratos"], ["b", "Proteínas"], ["c", "Lípidos"]];
  return (
    <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="market-inspect-modal">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
      <motion.div initial={{ scale: 0.95, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
        className="relative glass-strong rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-white/10 shrink-0">
          <div className="min-w-0">
            <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5"><ShieldCheck size={11} /> Inspección verificada</p>
            <h3 className="font-display font-extrabold text-2xl tracking-tight leading-tight truncate">{l.title || l.dino_name}</h3>
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              {(l.prime || l.tier === "prime") && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 inline-flex items-center gap-1"><Crown size={10} /> PRIME</span>}
              {l.is_elder && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded bg-sky-400/20 text-sky-300 border border-sky-400/40 inline-flex items-center gap-1"><Sparkles size={10} /> ELDER</span>}
              {growthPct !== null && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded glass border border-white/15">Crecimiento {growthPct}%</span>}
              {(v.elder_stacks || 0) > 0 && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded glass border border-white/15">Acumulaciones de Anciano: {v.elder_stacks}</span>}
            </div>
          </div>
          <button onClick={onClose} data-testid="market-inspect-close" className="p-2 rounded-lg glass hover:bg-white/10 transition-colors shrink-0"><X size={18} /></button>
        </div>
        <div className="flex-1 min-h-0 flex flex-col md:flex-row overflow-y-auto md:overflow-hidden">
          <div className="relative md:w-[46%] shrink-0 min-h-[260px] md:min-h-0 md:self-stretch border-b md:border-b-0 md:border-r border-white/10"
            style={{ background: "radial-gradient(closest-side at 50% 62%, rgba(124,168,66,0.10), rgba(8,13,11,0) 78%), #080d0b" }}>
            <SpeciesViewer3D species={l.species} active={!!l.species} skin={l.skin_view} interactive liveSnapshotFallback={false} preferClip="walk" />
          </div>
          <div className="md:w-[54%] px-6 py-5 space-y-4 md:overflow-y-auto">
            <div className="glass rounded-lg px-3 py-2.5 text-[11px] text-muted-foreground">
              {l.type === "trade"
                ? "Estos datos se leen directamente del dinosaurio de su dueño — es exactamente lo que recibirías en tu bóveda si acepta tu intercambio. No está en custodia: sigue siendo suyo hasta que acepte."
                : `Estos datos se leen directamente del dinosaurio en custodia — es exactamente lo que recibirás en tu bóveda al ${l.type === "auction" ? "ganar la subasta" : "comprar"}.`}
            </div>
            <div className="space-y-3" data-testid="market-inspect-mutations">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Dna size={11} /> Mutaciones verificadas · {priced}</p>
              <MutGroup label="Propias" chips={own} testId="inspect-muts-own" />
              <MutGroup label="Heredadas" chips={inherited} testId="inspect-muts-inherited"
                note="Vienen del linaje de los padres y no cuentan para el precio." />
              {(elder.length > 0 || (v.elder_stacks || 0) > 0) && <MutGroup label="Anciano" chips={elder} testId="inspect-muts-elder" />}
            </div>
            <div className="space-y-1.5">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Activity size={11} /> Constantes almacenadas</p>
              <InspectVitalRow label="Salud" color="#E24A4A" cur={stats.health} max={stats.max_health} />
              <InspectVitalRow label="Estamina" color="#38bdf8" cur={stats.stamina} max={stats.max_stamina} />
              <InspectVitalRow label="Hambre" color="#7CA842" cur={stats.hunger} max={stats.max_hunger} />
              <InspectVitalRow label="Sed" color="#34D399" cur={stats.thirst} max={stats.max_thirst} />
              <InspectVitalRow label="Oxígeno" color="#a78bfa" cur={stats.oxygen} max={stats.max_oxygen} />
            </div>
            {dietRows.some(([k]) => typeof diet[k] === "number" && Number.isFinite(diet[k])) && (
              <div>
                <p className="label-overline text-[10px] text-muted-foreground mb-1.5 inline-flex items-center gap-1.5"><Wheat size={11} /> Dieta almacenada</p>
                <div className="grid grid-cols-3 gap-2">
                  {dietRows.map(([k, label]) => (
                    <div key={k} className="glass rounded-lg px-2 py-1.5 text-center">
                      <p className="font-display font-bold text-sm tabular-nums">{typeof dietPct[k] === "number" ? `${dietPct[k]}%` : "—"}</p>
                      <p className="text-[9px] text-muted-foreground mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2">
            {/* A trade has no price. Quoting one here — or drawing a coin chip
                on a null — would tell the player something that is not true of
                this card. What it HAS is a value, and that is what the fairness
                band is measured in. */}
            <span className="text-[11px] text-muted-foreground">{l.type === "trade" ? "Valor" : l.type === "auction" ? (l.current_bid ? "Puja actual" : "Puja inicial") : "Precio"}</span>
            <CoinChip type="normal" amount={l.type === "trade" ? intOrNull(l.value) : r.currentAmount} size="md" />
          </div>
          <button onClick={onClose} className="px-4 py-2 rounded-lg glass border border-white/15 font-bold text-sm hover:border-gold/40 transition-all">Cerrar</button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ───────────────────────────── the sell panel ───────────────────────────── */

// Normalise the two picker sources into ONE shape, so the vault branch and the
// inventory branch stop disagreeing about the same two facts. The server-side
// fields (mutations_total, growth_pct_market, market_eligible) are preferred
// wherever the route publishes them; the older fields are the fallback.
//
// The gate FAILS OPEN here on purpose. The server's growth gate fails CLOSED
// and its 409 carries the exact wording; a client that greys out a seller the
// server would have accepted is a support ticket for zero benefit.
function vaultOption(o) {
  const growth = intOrNull(o.growth_pct_market) !== null
    ? intOrNull(o.growth_pct_market)
    : intOrNull(o.growth_pct);
  const muts = intOrNull(o.mutations_total) !== null
    ? intOrNull(o.mutations_total)
    : intOrNull(o.mutations_count);
  return {
    key: `vault:${o.id}`, source: "vault", item: o,
    species: o.species || "", customName: o.custom_name || "",
    speciesLabel: o.species || "",
    growthPct: growth, mutations: muts, prime: !!o.is_prime,
    eligible: o.market_eligible === false ? false : true,
    blockReason: o.market_block_reason || null,
  };
}

// The inventory lane has no server-side eligibility flag, so the client applies
// the SERVER'S OWN threshold to the SERVER'S OWN growth number — it still pins
// nothing of its own, and with no threshold published it blocks nobody.
function inventoryOption(o, minGrowthPct) {
  const clean = (o.name || "").replace(/ Slot$/, "");
  const g = intOrNull(o.saved_growth) !== null
    ? intOrNull(o.saved_growth)
    : (Number.isFinite(Number(o.saved_growth)) ? Math.floor(Number(o.saved_growth)) : null);
  const groups = o.mutation_groups;
  let muts = intOrNull(o.mutations_total);
  if (muts === null && groups && typeof groups === "object") {
    // The parent group is deliberately excluded: a player is not paid for
    // their grandparent's genes, and the price does not count them either.
    muts = ["child", "elder_a", "elder_b"].reduce(
      (n, k) => n + (Array.isArray(groups[k]) ? groups[k].filter(Boolean).length : 0), 0);
  }
  if (muts === null) muts = Array.isArray(o.mutations) ? o.mutations.length : null;
  const short = minGrowthPct !== null && g !== null && g < minGrowthPct;
  return {
    key: `inv:${o.id}`, source: "inventory", item: o,
    species: clean, customName: o.custom_name || "", speciesLabel: clean,
    growthPct: g, mutations: muts, prime: o.tier === "prime",
    eligible: !short,
    blockReason: short ? `growth_low_${g}` : null,
  };
}

// THE ONE PUBLISH PANEL. Sale, auction and TRADE are three types of the same
// action — "put this dinosaur on the Mercado" — and they share one picker, one
// growth gate and one value. Trading got its own page in the first build and
// that is precisely what the owner asked us to undo: a player who is looking at
// what their animal is worth is exactly the player deciding whether to sell it
// or swap it, and that decision belongs in one place.
//
// WHAT THE TRADE TYPE CHANGES: no price, no duration, no fee — a card is an
// advertisement, not a sale — and the picker narrows to La Bóveda, because a
// website-inventory dinosaur has no parked row and the trade lane moves parked
// rows. The value stays on screen: it is what the fairness band is measured in.
function SellModal({ board, tradeCfg, onClose, onDone, onPublished }) {
  const { play } = useSound();
  const { refresh } = useAuth();
  const [ownedInv, setOwnedInv] = useState([]);
  const [ownedVault, setOwnedVault] = useState([]);
  const [vaultMinGrowth, setVaultMinGrowth] = useState(null);
  const [selKey, setSelKey] = useState("");
  // duration_hours starts EMPTY: it is seeded from the payload's own tier list.
  // The panel no longer carries a copy of the tiers to fall back on.
  const [form, setForm] = useState({ type: "sale", price: "", duration_hours: "", title: "", note: "" });
  const [busy, setBusy] = useState(false);
  // The trade lane confirms before it publishes; the sale lane does not, and
  // that difference is deliberate. A card is the first thing on this page that
  // invites STRANGERS to act on one of your animals, so it says so once.
  const [confirming, setConfirming] = useState(false);
  const [quote, setQuote] = useState(EMPTY_QUOTE);
  const [quoteState, setQuoteState] = useState("idle"); // idle | loading | ready | error
  const [reloadTick, setReloadTick] = useState(0);
  const seededRef = useRef(null);   // which selection has already seeded the price
  const reqIdRef = useRef(null);    // the current attempt id, kept across a dropped socket

  useEffect(() => {
    api.inventory().then((r) => {
      const dinos = (r.data || []).filter((i) => i.category === "Dinosaurs" && (i.dino_slug || (i.item_id || "").startsWith("dino_")));
      setOwnedInv(dinos);
    }).catch(() => setOwnedInv([]));
    // La Bóveda (vault) dinos — merged into the same picker as an additive
    // source. Skip anything with a redeem in progress: it would just 409.
    api.meVault().then((r) => {
      setOwnedVault((r.data?.dinos || []).filter((d) => !d.redeem_pending));
      setVaultMinGrowth(intOrNull(r.data?.min_growth_pct));
    }).catch(() => { setOwnedVault([]); setVaultMinGrowth(null); });
  }, []);

  // The gate threshold: the vault summary publishes it for the whole market,
  // and a loaded quote confirms it per animal. Absent from both -> the picker
  // states the rule without a number and blocks nobody.
  const minGrowth = quote.minGrowthPct !== null ? quote.minGrowthPct : vaultMinGrowth;

  const isTrade = form.type === "trade";
  const options = useMemo(() => [
    // A TRADE MOVES A PARKED ROW, so the inventory lane is not offered for one:
    // a website-inventory dinosaur has no row for the vault escrow to take, and
    // offering it here would build a picker whose choice the API cannot accept.
    ...(isTrade ? [] : ownedInv.map((o) => inventoryOption(o, minGrowth))),
    ...ownedVault.map((o) => vaultOption(o)),
  ], [ownedInv, ownedVault, minGrowth, isTrade]);

  const sellable = options.filter((o) => o.eligible);
  const nothingOwned = options.length === 0;
  const nothingSellable = !nothingOwned && sellable.length === 0;

  // Preselect the first animal the market will actually take — and RE-select
  // when the current choice leaves the list, which is what switching to a trade
  // does to an inventory dinosaur. Without the second half the panel sits on a
  // selection that no longer exists and quotes nothing.
  useEffect(() => {
    if (sellable.length === 0) return;
    if (selKey && options.some((o) => o.key === selKey)) return;
    const first = sellable[0];
    setSelKey(first.key);
    setForm((f) => ({ ...f, price: "", title: first.customName || first.species || "" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ownedInv, ownedVault, isTrade]);

  const selectedOpt = options.find((o) => o.key === selKey) || null;

  // ONE quote per selection. The server counts the mutations itself off the row
  // — a client-sent count is a client-sent price with extra steps.
  useEffect(() => {
    if (!selectedOpt) { setQuote(EMPTY_QUOTE); setQuoteState("idle"); return; }
    let cancelled = false;
    setQuoteState("loading");
    const params = selectedOpt.source === "vault"
      ? { dino_id: selectedOpt.item.id, species: selectedOpt.item.species }
      : { inv_id: selectedOpt.item.id, slug: selectedOpt.item.dino_slug };
    api.marketSuggestedPrice(params)
      .then((r) => {
        if (cancelled) return;
        const q = readQuote(r.data);
        setQuote(q);
        setQuoteState(q.ok ? "ready" : "error");
        // SEEDED ONCE PER SELECTION, then the seller is left alone: a later
        // refetch must never overwrite a number they typed themselves.
        if (q.suggested !== null && seededRef.current !== selectedOpt.key) {
          seededRef.current = selectedOpt.key;
          setForm((f) => ({ ...f, price: String(q.suggested) }));
        }
      })
      .catch(() => {
        if (cancelled) return;
        setQuote(EMPTY_QUOTE);
        setQuoteState("error");
      });
    return () => { cancelled = true; };
    // selectedOpt?.key (a derived primitive identifying the current selection) is
    // the intentional dependency, matching this file's pre-existing convention.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOpt?.key, reloadTick]);

  const tiers = durationTiers(quote, form.type);
  const tiersKey = tiers ? tiers.join(",") : "";

  // Snap the chosen duration into whatever the payload says is legal. The panel
  // never holds a duration the server did not publish.
  useEffect(() => {
    if (!tiers) return;
    setForm((f) => (tiers.includes(Number(f.duration_hours)) ? f : { ...f, duration_hours: defaultTier(tiers) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tiersKey, form.type]);

  // ...and DERIVE it as well as storing it, so the one render between switching
  // sale<->auction and that effect firing can neither display nor SUBMIT a tier
  // belonging to the other list.
  const hours = tiers
    ? (tiers.includes(Number(form.duration_hours)) ? Number(form.duration_hours) : defaultTier(tiers))
    : null;

  const speciesLabel = selectedOpt?.speciesLabel || "";
  const rows = suggestionRows(quote, speciesLabel);
  const subtitle = suggestionSubtitle(quote, speciesLabel);
  const rail = railSentence(quote);
  const fallbackNote = fallbackBaseNotice(quote);
  const history = salesHistoryLine(quote, speciesLabel);
  const receipt = feePreview(intOrNull(form.price), quote.taxPct);
  // The trade lane has its OWN block list: no price to validate and no duration
  // to pick, but a card cap and a knob the market's own reader never touches.
  const blockReason = isTrade
    ? publishBlockReason({ cfg: tradeCfg, board, option: selectedOpt })
    : submitBlockReason(quote, form.type, quoteState === "ready" || quoteState === "error");
  // Shown live while they type, but never nagging at an empty field.
  const priceCheck = validatePrice(form.price, quote);
  const liveError = String(form.price).trim() !== "" && !priceCheck.ok ? priceCheck.detail : null;

  const useSuggested = () => {
    if (quote.suggested === null) return;
    setForm((f) => ({ ...f, price: String(quote.suggested) }));
    play("click");
  };

  // THE TRADE PUBLISH. Deliberately its own function and not a branch inside
  // `submit`: it sends a different body to a different route, and the only
  // thing it shares with a sale is which animal was picked.
  const publish = async () => {
    if (!selectedOpt || selectedOpt.source !== "vault") {
      play("error");
      toast.error("Elige un dinosaurio de La Bóveda para intercambiar.");
      return;
    }
    setBusy(true);
    if (!reqIdRef.current) reqIdRef.current = newRequestId();
    const rid = reqIdRef.current;
    try {
      await api.tradeBoardCreate({
        dino_id: selectedOpt.item.id,
        title: form.title.trim(),
        note: form.note.trim() || null,
        client_request_id: rid,
      });
      reqIdRef.current = null;
      play("success");
      toast.success("Publicado para intercambio.", {
        description: "No sale de tu bóveda. Quítalo cuando quieras desde Mis publicaciones.",
      });
      if (onPublished) onPublished();
      onDone();
    } catch (err) {
      if (attemptSettled(err)) reqIdRef.current = null;
      play("error");
      toast.error(networkRefusal(err, "No se pudo publicar. Vuelve a intentarlo."));
    } finally { setBusy(false); setConfirming(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!selectedOpt) { play("error"); toast.error("Elige un dinosaurio para publicar."); return; }
    if (blockReason) { play("error"); toast.error(blockReason); return; }
    if (isTrade) { play("click"); setConfirming(true); return; }
    const v = validatePrice(form.price, quote);
    if (!v.ok) { play("error"); toast.error(v.detail); return; }
    if (!Number.isFinite(hours) || hours <= 0) {
      play("error"); toast.error("Elige una duración para la publicación."); return;
    }
    setBusy(true);
    // One id per ATTEMPT. Kept across a dropped socket so an honest second click
    // replays instead of creating a second listing; replaced after any definite
    // answer, so a refused attempt can legitimately be retried.
    if (!reqIdRef.current) reqIdRef.current = newRequestId();
    const rid = reqIdRef.current;
    try {
      const identity = selectedOpt.source === "vault"
        ? { source: "vault", dino_id: selectedOpt.item.id }
        : { inv_id: selectedOpt.item.id };
      await api.marketCreate({
        ...identity,
        type: form.type,
        price: v.price,
        duration_hours: hours,
        title: form.title.trim(),
        client_request_id: rid,
      });
      reqIdRef.current = null;
      play("success"); toast.success("¡Publicación creada!");
      await refresh(); onDone();
    } catch (err) {
      if (attemptSettled(err)) reqIdRef.current = null;
      play("error");
      toast.error(err?.response?.data?.detail || "No se pudo publicar. Vuelve a intentarlo.");
    } finally { setBusy(false); }
  };

  const gate = nothingSellable ? gateEmptyState(options, minGrowth) : null;
  const tradeConfirm = publishConfirm({ cfg: tradeCfg, board, option: selectedOpt });

  return (
    <motion.div className="fixed inset-0 z-[100000] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="sell-modal">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
      <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.94 }} className="relative glass-strong rounded-2xl w-full max-w-md p-6 max-h-[92vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>
        <h3 className="font-display font-bold text-2xl mb-1">Publicar un dinosaurio</h3>
        <p className="text-sm text-muted-foreground mb-5">
          {isTrade
            ? "Ponlo en el Mercado para intercambiar. No sale de tu bóveda: otros jugadores te ofrecen los suyos y tú eliges."
            : "Vende o subasta un dinosaurio de tu inventario o de La Bóveda por PrimeMeat. Tú pones el precio, dentro de lo que vale."}
        </p>

        {nothingOwned ? (
          <p className="text-sm text-muted-foreground py-6 text-center">Aún no tienes dinosaurios. Compra uno en la Tienda, guarda uno en La Bóveda, o abre el Inventario para gestionar los tuyos.</p>
        ) : gate ? (
          <div className="py-4 space-y-2" data-testid="sell-growth-gate">
            <p className="font-display font-bold text-base leading-snug">{gate.headline}</p>
            <p className="text-sm text-muted-foreground leading-snug">{gate.body}</p>
            {gate.biggest && <p className="text-sm text-gold leading-snug" data-testid="sell-gate-biggest">{gate.biggest}</p>}
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <label className="block"><span className="label-overline text-[10px] text-muted-foreground block mb-1.5">Dinosaurio</span>
              <select className="w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent" value={selKey}
                onChange={(e) => {
                  const o = options.find((x) => x.key === e.target.value);
                  setSelKey(e.target.value);
                  // A different animal is a DIFFERENT attempt. Carrying the old
                  // id over would let a replay hand back the previous animal's
                  // stored result, since the server keys idempotency on the
                  // seller and the request id, not on the dino.
                  reqIdRef.current = null;
                  setForm((f) => ({ ...f, price: "", title: o ? (o.customName || o.species) : "" }));
                }} data-testid="sell-dino-select">
                {ownedInv.length > 0 && (
                  <optgroup label="Inventario">
                    {options.filter((o) => o.source === "inventory").map((o) => (
                      <option key={o.key} value={o.key} className="bg-background" disabled={!o.eligible}>
                        {pickerLabel(o, minGrowth)}
                      </option>
                    ))}
                  </optgroup>
                )}
                {ownedVault.length > 0 && (
                  <optgroup label="La Bóveda">
                    {options.filter((o) => o.source === "vault").map((o) => (
                      <option key={o.key} value={o.key} className="bg-background" disabled={!o.eligible}>
                        {pickerLabel(o, minGrowth)}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {selectedOpt && (
                <p className="text-[11px] text-muted-foreground mt-1" data-testid="sell-dino-detail">
                  {selectedOpt.source === "vault" ? "Desde La Bóveda · " : ""}
                  {selectedOpt.growthPct !== null ? `${selectedOpt.growthPct}% crecimiento` : "crecimiento desconocido"}
                  {fmtMutations(selectedOpt.mutations) ? ` · ${fmtMutations(selectedOpt.mutations)}` : ""}
                </p>
              )}
            </label>

            {/* A different listing TYPE is also a different attempt. */}
            <div className="grid grid-cols-3 gap-2">
              {[["sale", "Venta"], ["auction", "Subasta"], ["trade", "Intercambio"]].map(([k, label]) => (
                <button key={k} type="button" data-testid={`sell-type-${k}`}
                  onClick={() => { reqIdRef.current = null; setForm((f) => ({ ...f, type: k })); }}
                  className={`py-2.5 rounded-lg text-sm font-semibold transition-all ${form.type === k ? "bg-gold text-background" : "glass text-muted-foreground"}`}>
                  {label}
                </button>
              ))}
            </div>

            <label className="block"><span className="label-overline text-[10px] text-muted-foreground block mb-1.5">Nombre de la publicación</span>
              <input className="w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={60} placeholder="Ejemplo: Rex Titán con 12 mutaciones" data-testid="sell-title" />
            </label>

            {isTrade && (
              <label className="block"><span className="label-overline text-[10px] text-muted-foreground block mb-1.5">Qué buscas (opcional)</span>
                <input className="w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent" value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })} maxLength={60}
                  placeholder="Ejemplo: busco Deino con muts" data-testid="sell-trade-note" />
                <p className="text-[11px] text-muted-foreground mt-1 leading-snug">
                  Se ve en tu publicación. Aun así, cualquiera puede ofrecerte lo que quiera.
                </p>
              </label>
            )}

            {/* THE PRICE IS THE SELLER'S. min/max are bound to the server's own
                rails — the shape webcore/frontend/js/auction.js:202-207 already
                uses — and step is 1 because the market deals in whole coins and
                a coarser step would have the browser refuse prices the server
                accepts. */}
            {!isTrade && (
            <label className="block"><span className="label-overline text-[10px] text-muted-foreground block mb-1.5">{form.type === "auction" ? "Puja inicial" : "Precio"} — PrimeMeat</span>
              <input type="number" inputMode="numeric" data-testid="sell-price"
                className="w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent font-display font-bold tabular-nums focus:outline-none focus:ring-2 focus:ring-gold/50"
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
                min={quote.min !== null ? quote.min : undefined}
                max={quote.max !== null ? quote.max : undefined}
                step={1}
                placeholder={quote.suggested !== null ? String(quote.suggested) : (quoteState === "loading" ? "Calculando…" : "")} />
              {rail && <p className="text-[11px] text-muted-foreground mt-1" data-testid="sell-rail">{rail}</p>}
              {liveError && <p className="text-[11px] text-crimson mt-1 leading-snug" data-testid="sell-price-error">{liveError}</p>}
            </label>
            )}

            {/* The suggestion, itemised, so the number is a claim the seller can
                check rather than a magic figure. A trade has no price, but the
                SAME number is what the fairness band is measured in — so it
                stays on screen and only its name changes. */}
            <div className="rounded-lg border border-gold/30 bg-gold/[0.06] px-3 py-3" data-testid="suggested-price-box">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-wide text-gold"><TrendingUp size={14} /> {isTrade ? "Lo que vale" : "Precio sugerido"}</span>
                <span className="font-display font-extrabold text-gold text-sm tabular-nums shrink-0" data-testid="suggested-price-value">
                  {quoteState === "loading" ? "Calculando…" : fmtCoin(quote.suggested)}
                </span>
              </div>
              {rows.length > 0 && (
                <div className="mt-2 space-y-1 border-t border-gold/20 pt-2" data-testid="suggested-price-breakdown">
                  {rows.map((r) => (
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
              {subtitle && <p className="mt-2 text-[10px] leading-snug text-muted-foreground">{subtitle}</p>}
              {isTrade ? (
                <p className="mt-2 text-[10px] leading-snug text-muted-foreground" data-testid="sell-trade-band-note">
                  Las ofertas que recibas tienen que valer algo parecido a esto. Nadie paga
                  PrimeMeat en un intercambio: es dinosaurio por dinosaurio.
                </p>
              ) : (
                <button type="button" onClick={useSuggested} disabled={quote.suggested === null} data-testid="suggested-price-btn"
                  className="mt-2.5 w-full rounded-lg border border-gold/40 bg-gold/[0.08] px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-gold hover:bg-gold/15 transition-all disabled:opacity-50">
                  Usar este precio
                </button>
              )}
            </div>

            {fallbackNote && (
              <p className="text-[11px] leading-snug text-gold inline-flex items-start gap-1.5" data-testid="sell-base-fallback">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" /> <span>{fallbackNote}</span>
              </p>
            )}
            {history && <p className="text-[10px] leading-snug text-muted-foreground/80" data-testid="sell-sales-history">{history}</p>}

            {isTrade ? null : tiers ? (
              <label className="block">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="label-overline text-[10px] text-muted-foreground">Duración</span>
                  <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                    {fmtDur(hours)}{quote.taxPct !== null ? ` · ${quote.taxPct}% comisión` : ""}
                  </span>
                </div>
                <input type="range" min={0} max={tiers.length - 1} step={1}
                  value={Math.max(0, tiers.indexOf(hours))}
                  onChange={(e) => setForm({ ...form, duration_hours: tiers[Number(e.target.value)] })}
                  className="w-full accent-gold" data-testid="sell-duration" />
                <div className="flex justify-between text-[9px] text-muted-foreground/70 mt-1 tabular-nums">
                  {tiers.map((h) => (
                    <span key={h} className={hours === h ? "text-gold font-bold" : ""}>{fmtDur(h)}</span>
                  ))}
                </div>
              </label>
            ) : quoteState === "ready" ? (
              <p className="text-[11px] leading-snug text-crimson" data-testid="sell-duration-missing">
                No pudimos leer las duraciones permitidas para este tipo de publicación. Avísale a un administrador.
              </p>
            ) : null}

            {/* The net is the headline, not the percentage. A trade has no
                money in it at all, so it has no receipt. */}
            {!isTrade && (
            <div className="glass rounded-xl p-3 text-xs space-y-1" data-testid="sell-receipt">
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Precio de venta</span>
                <span className="font-semibold tabular-nums shrink-0">{fmtCoin(intOrNull(form.price))}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="min-w-0 text-muted-foreground">Comisión de plataforma{quote.taxPct !== null ? ` (${quote.taxPct}%)` : ""}</span>
                <span className="font-semibold text-crimson tabular-nums shrink-0" data-testid="sell-fee">{receipt.ok ? `-${fmtCoin(receipt.tax)}` : "—"}</span>
              </div>
              <div className="flex justify-between gap-2 border-t border-white/10 pt-1">
                <span className="text-muted-foreground font-bold">Recibes al vender</span>
                <span className="font-semibold text-gold tabular-nums shrink-0" data-testid="sell-net">{receipt.ok ? fmtCoin(receipt.net) : "—"}</span>
              </div>
            </div>
            )}

            {blockReason && (
              <div className="text-[11px] leading-snug text-crimson space-y-2" data-testid="sell-blocked">
                <p>{blockReason}</p>
                {quoteState === "error" && (
                  <button type="button" onClick={() => setReloadTick((n) => n + 1)} data-testid="sell-retry"
                    className="rounded-lg border border-crimson/40 px-3 py-1.5 font-bold uppercase tracking-wider hover:bg-crimson/10 transition-all">Reintentar</button>
                )}
              </div>
            )}

            <button type="submit" disabled={busy || !!blockReason} data-testid="sell-submit" className="w-full bg-gold text-background font-bold py-3 rounded-xl hover:brightness-110 transition-all disabled:opacity-60">{busy ? "Publicando…" : isTrade ? "Publicar para intercambio" : "Crear publicación"}</button>
          </form>
        )}

        {/* The trade confirmation. It says the one thing a seller cannot see
            from the form: that nothing moves, and when the card comes down. */}
        <ConfirmModal
          open={confirming}
          loading={busy}
          onClose={() => setConfirming(false)}
          onConfirm={publish}
          tone="gold"
          icon={<ArrowLeftRight size={28} />}
          title={tradeConfirm.title}
          confirmLabel={tradeConfirm.confirmLabel}
          abortLabel="Volver"
          message={
            <ul className="text-left space-y-2">
              {tradeConfirm.lines.map((l, i) => (
                <li key={i} className="leading-snug break-words">· {l}</li>
              ))}
            </ul>
          }
        />
      </motion.div>
    </motion.div>
  );
}

/* ─────────────────────────── the auction surface ─────────────────────────── */

// One countdown per auction card, shared by the clock, the crimson last minute
// and the anti-snipe notice — all three are the same fact.
function AuctionBody({ l, own, amount, onAmount, onBid, onWithdraw }) {
  const clock = useCountdown(l.ends_at);
  const { secondsLeft } = clock;
  // Only a clock we could actually READ, and that has run out, closes the box.
  // A missing or malformed ends_at leaves bidding live and lets the server —
  // which re-checks the clock at request time — give the exact refusal.
  const closed = secondsLeft === 0;
  const r = readListing(l);
  const ownFee = own ? readListing(own).withdrawFee : null;
  const snipe = antisnipeLine(l, secondsLeft);
  const nextLine = nextBidLine(l);
  return (
    <>
      <div className="flex items-center justify-between text-sm mb-1 gap-2">
        <span className="text-muted-foreground">{r.currentBid !== null ? "Puja actual" : "Puja inicial"}</span>
        <CoinChip type="normal" amount={r.currentAmount} size="sm" />
      </div>
      {l.current_bidder_name && <p className="text-[11px] text-muted-foreground mb-1 truncate">Mejor postor: {l.current_bidder_name}</p>}
      <p className="text-[11px] text-gold inline-flex items-center gap-1 mb-2"><Clock size={11} /> <ClockText {...clock} /></p>
      {snipe && (
        <p className="text-[10px] leading-snug text-crimson font-semibold inline-flex items-start gap-1 mb-2" data-testid={`antisnipe-${l.id}`}>
          <Clock size={11} className="shrink-0 mt-0.5" /> <span>{snipe}</span>
        </p>
      )}
      {own ? (
        own.has_bid ? (
          <p className="text-[11px] text-crimson mt-auto">No se puede retirar (ya tiene pujas)</p>
        ) : (
          <button onClick={onWithdraw} data-testid={`grid-withdraw-${l.id}`}
            className="mt-auto inline-flex items-center justify-center gap-1.5 border border-crimson/40 text-crimson font-bold text-sm px-3.5 py-2 rounded-lg hover:bg-crimson/10 transition-all">
            <Undo2 size={15} /> Retirar{ownFee !== null ? ` (-${fmtCoin(ownFee)})` : ""}
          </button>
        )
      ) : (
        <div className="mt-auto">
          <div className="flex gap-2">
            <input type="number" inputMode="numeric" step={1}
              min={r.minNextBid !== null ? r.minNextBid : undefined}
              max={r.bidMax !== null ? r.bidMax : undefined}
              placeholder={r.minNextBid !== null ? fmtCoin(r.minNextBid) : "Monto"}
              value={amount} onChange={onAmount} disabled={closed} data-testid={`bid-input-${l.id}`}
              className="flex-1 min-w-0 glass rounded-lg px-3 py-2 text-sm bg-transparent tabular-nums focus:outline-none focus:ring-2 focus:ring-gold/50 disabled:opacity-50" />
            <button onClick={onBid} disabled={closed} data-testid={`bid-button-${l.id}`} className="shrink-0 bg-gold text-background font-bold text-sm px-3 py-2 rounded-lg hover:brightness-110 transition-all disabled:opacity-50">Pujar</button>
          </div>
          {nextLine && <p className="text-[10px] leading-snug text-muted-foreground mt-1.5" data-testid={`bid-min-${l.id}`}>{nextLine}</p>}
        </div>
      )}
    </>
  );
}

/* ──────────────────────────── the trade surface ──────────────────────────── */

// ONE CARD IN THE SAME GRID. A trade card is drawn by the SAME media and meta
// components a sale is, off the same server key names — that is why
// `_trade_board_public` mirrors `_market_public` — so a dinosaur that is up for
// swap and a dinosaur that is up for sale read as the same kind of thing,
// because to the player they are.
//
// The chip and the button are the whole difference: no price, no clock to race,
// and an action that hands the decision to the OWNER instead of taking money.
function TradeCard({ card, i, onOffer, onClose, onInspect }) {
  const l = card.raw;
  const status = cardStatusLine(card);
  const worth = cardValueLine(card);
  return (
    <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: Math.min(i * 0.05, 0.4) }}
      className="group relative rounded-2xl overflow-hidden glass hover:border-gold/40 hover:-translate-y-1 transition-all duration-300 flex flex-col" data-testid={`trade-card-${card.id}`}>
      <span className="absolute top-3 left-3 z-10 inline-flex items-center gap-1 label-overline text-[9px] px-2 py-1 rounded-full bg-sky-400 text-background">
        <ArrowLeftRight size={10} /> Intercambio
      </span>
      <ListingMedia l={l} />
      <div className="p-5 flex flex-col flex-1">
        <h3 className="font-display font-bold text-lg leading-tight">{card.title || card.dinoName}</h3>
        <p className="text-xs text-muted-foreground">
          de {card.ownerName || "otro jugador"}
          {card.mine && <span className="ml-1.5 text-[9px] font-extrabold px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 align-middle">TU PUBLICACIÓN</span>}
        </p>
        <ListingMeta l={l} />
        {l.verify && (
          <button onClick={onInspect} data-testid={`inspect-${card.id}`}
            className="mb-3 inline-flex items-center justify-center gap-1.5 w-full border border-emerald/40 text-emerald font-bold text-[11px] px-3 py-1.5 rounded-lg hover:bg-emerald/10 transition-all">
            <ShieldCheck size={13} /> Inspeccionar antes de ofrecer
          </button>
        )}
        {card.note && <p className="text-[11px] text-muted-foreground mb-1 break-words">«{card.note}»</p>}
        {worth && <p className="text-[11px] text-gold tabular-nums" data-testid={`trade-value-${card.id}`}>{worth}</p>}
        {status && <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{status}</p>}
        <div className="mt-auto pt-3">
          {card.mine ? (
            <button onClick={onClose} data-testid={`trade-close-${card.id}`}
              className="w-full inline-flex items-center justify-center gap-1.5 border border-crimson/40 text-crimson font-bold text-sm px-3.5 py-2 rounded-lg hover:bg-crimson/10 transition-all">
              <Undo2 size={15} /> Quitar del Mercado
            </button>
          ) : card.offered ? (
            <button disabled data-testid={`trade-offered-${card.id}`}
              className="w-full inline-flex items-center justify-center gap-1.5 glass text-muted-foreground font-bold text-sm px-3.5 py-2 rounded-lg opacity-60 cursor-not-allowed">
              Oferta enviada
            </button>
          ) : (
            <button onClick={onOffer} data-testid={`trade-offer-${card.id}`}
              className="w-full inline-flex items-center justify-center gap-1.5 bg-gold text-background font-bold text-sm px-3.5 py-2 rounded-lg hover:brightness-110 transition-all">
              <Handshake size={15} /> Ofrecer el mío
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ───────────────────────────────── the page ──────────────────────────────── */

// THE MERCADO IS ONE SURFACE (owner, 2026-08-11: "redesign so dinosaurs get
// traded on the same tab people can see dinos for sale. no need to send anybody
// anything.")
//
// Sales, auctions and trades share this grid, this publish panel and this
// growth gate. `/intercambios` still exists and still works — it opens this
// page with the trade filter already on, so every link, bookmark and Discord
// message that pointed at the old page lands somewhere better rather than
// nowhere.
export default function Marketplace({ initialTab }) {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState(initialTab === "trade" ? "trade" : "all");
  const [selling, setSelling] = useState(false);
  const [bidAmts, setBidAmts] = useState({});
  const [mine, setMine] = useState(null);
  const [withdrawTarget, setWithdrawTarget] = useState(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [inspectId, setInspectId] = useState(null);
  // ── Intercambios ──────────────────────────────────────────────────────────
  const [board, setBoard] = useState(null);
  const [tradeCfg, setTradeCfg] = useState(null);
  const [tradeMine, setTradeMine] = useState(null);
  const [tradeMineError, setTradeMineError] = useState(null);
  const [offerCard, setOfferCard] = useState(null);
  const [closeTarget, setCloseTarget] = useState(null);
  const [closingCard, setClosingCard] = useState(false);
  // Attempt ids for the money lanes, keyed by what makes an attempt distinct.
  // A DROPPED SOCKET keeps the id (the server may have completed the write, so
  // the next click must replay); any definite answer clears it.
  const reqIds = useRef({});

  const load = () => api.market().then((r) => setItems(r.data)).catch(() => setItems([]));
  // Own listings are loaded alongside the public feed (not only on the "mine"
  // tab): the grid needs them to swap Comprar for Retirar on the user's own
  // cards — the public /market feed is anonymous, so id-matching /market/mine
  // is the only reliable "this one is yours" signal.
  const loadMine = () => api.marketMine().then((r) => setMine(r.data)).catch(() => setMine([]));
  useEffect(() => { load(); loadMine(); const t = setInterval(() => { load(); loadMine(); }, 8000); return () => clearInterval(t); }, []);
  useEffect(() => { if (filter === "mine") loadMine(); }, [filter]);

  // The board degrades to an EMPTY-BUT-NOT-OK board, never to an empty one: a
  // board nobody has published to and a board we could not read say different
  // things to a player, and boardEmptyState says the right one.
  const loadBoard = useCallback(() => api.tradeBoard()
    .then((r) => setBoard(readBoard(r.data)))
    .catch(() => setBoard(readBoard(null))), []);
  const loadTradeCfg = useCallback(() => api.tradeConfig()
    .then((r) => setTradeCfg(readTradeConfig(r.data)))
    .catch(() => setTradeCfg(readTradeConfig(null))), []);
  const loadTradeMine = useCallback(() => api.tradeMine()
    .then((r) => { setTradeMine(readMine(r.data)); setTradeMineError(null); })
    .catch((err) => {
      setTradeMine((m) => m || readMine(null));
      setTradeMineError(networkRefusal(err, "No pudimos leer tus intercambios."));
    }), []);

  // A SLOWER CLOCK THAN THE MARKET'S, on purpose. A card has no countdown to
  // race and no bid to be outbid on, and GET /trade/mine is the heavier read of
  // the two. It is also the only thing that expires an offer on a box with no
  // sweeper, which is why it keeps running at all — paused while the tab is
  // hidden, so a page left open overnight is not thousands of requests nobody
  // ever saw.
  useEffect(() => {
    if (!user) return undefined;
    loadBoard(); loadTradeCfg(); loadTradeMine();
    const t = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      loadBoard(); loadTradeMine();
    }, 30000);
    return () => clearInterval(t);
  }, [user, loadBoard, loadTradeCfg, loadTradeMine]);

  // ONE STABLE ARRAY. `board.cards` is already memo-stable between polls, but a
  // bare `|| []` mints a fresh empty array on every render, and the feed below
  // memoises on it — so the whole grid would rebuild on every tick of every
  // other timer on this page.
  const cards = useMemo(() => (board && board.cards) || [], [board]);
  // ONE FEED, newest first, whatever it is. Sorting the two sources together is
  // what makes this a single market rather than a market with a trade annexe.
  const feed = useMemo(() => {
    const listings = (items || [])
      .filter((l) => filter === "all" || l.type === filter)
      .map((l) => ({ kind: "listing", key: `l:${l.id}`, at: l.created_at, l }));
    const trades = (filter === "all" || filter === "trade")
      ? cards.map((c) => ({ kind: "trade", key: `t:${c.id}`, at: (c.raw || {}).created_at, c }))
      : [];
    return listings.concat(trades)
      .sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  }, [items, cards, filter]);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Mercado de Jugadores" sub="Inicia sesión para comprar, subastar e intercambiar dinosaurios." /></div>;

  const mineById = new Map((mine || []).map((m) => [m.id, m]));
  const myCards = cards.filter((c) => c.mine);
  // The open inspector follows the live feed so an auction's current bid stays
  // fresh; the verify block itself is escrow-static by construction. Trade
  // cards are searched too — the inspector is the same modal for both.
  const inspectListing = inspectId == null ? null
    : ((items || []).find((x) => x.id === inspectId)
      || (cards.find((c) => c.id === inspectId) || {}).raw
      || null);
  const incomingCount = ((tradeMine || {}).incoming || []).length;

  const idFor = (key) => {
    if (!reqIds.current[key]) reqIds.current[key] = newRequestId();
    return reqIds.current[key];
  };
  const settle = (key, err) => { if (attemptSettled(err)) delete reqIds.current[key]; };

  const doWithdraw = async () => {
    if (!withdrawTarget) return;
    setWithdrawing(true);
    const key = `withdraw:${withdrawTarget.id}`;
    try {
      const r = await api.marketWithdraw(withdrawTarget.id, { client_request_id: idFor(key) });
      settle(key, null);
      play("success");
      toast.success(`${withdrawTarget.dino_name} devuelto a tu ${withdrawTarget.source === "vault" ? "bóveda" : "inventario"}`, {
        description: `Comisión de retiro: -${fmtCoin(r.data?.fee)}`,
      });
      setWithdrawTarget(null);
      await refresh(); loadMine(); load();
    } catch (e) {
      settle(key, e);
      play("error"); toast.error(e?.response?.data?.detail || "No se pudo retirar");
    } finally { setWithdrawing(false); }
  };

  // Taking a card down. FREE and instant — nothing was ever escrowed, so there
  // is no fee to charge and nothing to give back. That is the whole reason it
  // does not go through the market's withdraw lane.
  const doCloseCard = async () => {
    if (!closeTarget) return;
    setClosingCard(true);
    const key = `card:${closeTarget.id}`;
    try {
      await api.tradeBoardClose(closeTarget.id, { client_request_id: idFor(key) });
      settle(key, null);
      play("success");
      toast.success("Quitado del Mercado. Tu dinosaurio sigue en tu bóveda.");
      setCloseTarget(null);
      await loadBoard();
    } catch (e) {
      settle(key, e);
      play("error");
      toast.error(networkRefusal(e, "No se pudo quitar. Actualiza la página."));
    } finally { setClosingCard(false); }
  };

  const buy = async (l) => {
    const r = readListing(l);
    const key = `buy:${l.id}`;
    try {
      // expected_price is the stale-page guard: the button SENDS the number it
      // SHOWED, so a price that moved under the seller earns an exact refusal
      // instead of a silent overcharge. Omitted when the feed did not carry it.
      await api.marketBuy(l.id, {
        ...(r.price !== null ? { expected_price: r.price } : {}),
        client_request_id: idFor(key),
      });
      settle(key, null);
      play("purchase");
      toast.success(`¡Compraste ${l.dino_name}!`, { description: l.source === "vault" ? "Entregado a tu bóveda de dinosaurios." : "Añadido a tu inventario." });
      await refresh(); load();
    } catch (e) {
      settle(key, e);
      play("error"); toast.error(e?.response?.data?.detail || "No se pudo comprar");
    }
  };

  const bid = async (l) => {
    const r = readListing(l);
    const amount = intOrNull(bidAmts[l.id]);
    if (amount === null) {
      play("error");
      toast.error(minBidRefusal(l) || "Escribe un monto entero de PrimeMeat para pujar.");
      return;
    }
    if (r.minNextBid !== null && amount < r.minNextBid) {
      play("error"); toast.error(minBidRefusal(l)); return;
    }
    if (r.bidMax !== null && amount > r.bidMax) {
      play("error"); toast.error(maxBidRefusal(l)); return;
    }
    const key = `bid:${l.id}:${amount}`;
    try {
      await api.marketBid(l.id, amount, {
        ...(r.minNextBid !== null ? { expected_price: r.minNextBid } : {}),
        client_request_id: idFor(key),
      });
      settle(key, null);
      play("coins"); toast.success("¡Puja realizada!");
      setBidAmts({ ...bidAmts, [l.id]: "" });
      await refresh(); load();
    } catch (e) {
      settle(key, e);
      play("error"); toast.error(e?.response?.data?.detail || "No se pudo pujar");
    }
  };

  const renderListing = (l, i) => {
    const own = mineById.get(l.id);
    const r = readListing(l);
    return (
      <motion.div key={l.id} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: Math.min(i * 0.05, 0.4) }}
        className="group relative rounded-2xl overflow-hidden glass hover:border-gold/40 hover:-translate-y-1 transition-all duration-300 flex flex-col" data-testid={`listing-${l.id}`}>
        <span className={`absolute top-3 left-3 z-10 inline-flex items-center gap-1 label-overline text-[9px] px-2 py-1 rounded-full ${l.type === "auction" ? "bg-crimson text-white" : "bg-emerald text-background"}`}>
          {l.type === "auction" ? <><Gavel size={10} /> Subasta</> : <><Tag size={10} /> Venta</>}
        </span>
        <ListingMedia l={l} />
        <div className="p-5 flex flex-col flex-1">
          <h3 className="font-display font-bold text-lg leading-tight">{l.title || l.dino_name}</h3>
          <p className="text-xs text-muted-foreground">de {l.seller_name}{own && <span className="ml-1.5 text-[9px] font-extrabold px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 align-middle">TU PUBLICACIÓN</span>}</p>
          <ListingMeta l={l} />
          {l.verify && (
            <button onClick={() => { setInspectId(l.id); play("open"); }} data-testid={`inspect-${l.id}`}
              className="mb-3 inline-flex items-center justify-center gap-1.5 w-full border border-emerald/40 text-emerald font-bold text-[11px] px-3 py-1.5 rounded-lg hover:bg-emerald/10 transition-all">
              <ShieldCheck size={13} /> Inspeccionar antes de {l.type === "auction" ? "pujar" : "comprar"}
            </button>
          )}
          {l.type === "auction" ? (
            <AuctionBody
              l={l} own={own}
              amount={bidAmts[l.id] || ""}
              onAmount={(e) => setBidAmts({ ...bidAmts, [l.id]: e.target.value })}
              onBid={() => bid(l)}
              onWithdraw={() => { setWithdrawTarget(own); play("click"); }} />
          ) : (
            <div className="flex items-center justify-between gap-2 mt-auto">
              <CoinChip type="normal" amount={r.price} size="md" />
              {own ? (
                <button onClick={() => { setWithdrawTarget(own); play("click"); }} data-testid={`grid-withdraw-${l.id}`}
                  className="shrink-0 inline-flex items-center gap-1.5 border border-crimson/40 text-crimson font-bold text-sm px-3.5 py-2 rounded-lg hover:bg-crimson/10 transition-all">
                  <Undo2 size={15} /> Retirar
                </button>
              ) : (
                <button onClick={() => buy(l)} data-testid={`buy-listing-${l.id}`} className="shrink-0 inline-flex items-center gap-1.5 bg-gold text-background font-bold text-sm px-3.5 py-2 rounded-lg hover:brightness-110 transition-all"><ShoppingBag size={15} /> Comprar</button>
              )}
            </div>
          )}
        </div>
      </motion.div>
    );
  };

  const renderCard = (c, i) => (
    <TradeCard
      key={c.id} card={c} i={i}
      onOffer={() => { setOfferCard(c); play("open"); }}
      onClose={() => { setCloseTarget(c); play("click"); }}
      onInspect={() => { setInspectId(c.id); play("open"); }} />
  );

  const emptyBoard = boardEmptyState({ board: board || { ok: false }, mineOnly: false });
  const closeCopy = closeTarget ? closeCardConfirm(closeTarget) : null;

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="label-overline text-xs text-gold mb-2">Comercio entre Jugadores</p>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Mercado</h1>
          <p className="text-muted-foreground mt-3 max-w-xl">
            Compra, subasta e intercambia dinosaurios entre jugadores. Con <span className="text-emerald">PrimeMeat</span>, o dinosaurio por dinosaurio.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="glass rounded-xl px-4 py-2"><CoinChip type="normal" amount={user.coins} size="md" /></div>
          <button onClick={() => { setSelling(true); play("open"); }} data-testid="open-sell" className="inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-xl hover:brightness-110 transition-all text-sm"><Plus size={16} /> Publicar un dinosaurio</button>
        </div>
      </motion.div>

      <div className="flex flex-wrap gap-2 mb-8">
        {[["all", "Todas"], ["sale", "Venta Directa"], ["auction", "Subastas"],
          ["trade", "Intercambios"], ["mine", "Mis publicaciones"], ["offers", "Mis ofertas"]].map(([k, label]) => (
          <button key={k} onClick={() => { setFilter(k); play("click"); }} data-testid={`market-filter-${k}`}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${filter === k ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`}>
            {label}
            {k === "offers" && incomingCount > 0 && (
              <span className="ml-1.5 tabular-nums text-[11px] font-extrabold px-1.5 py-0.5 rounded-full bg-crimson text-white" data-testid="offers-badge">{incomingCount}</span>
            )}
          </button>
        ))}
      </div>

      {filter === "offers" ? (
        <TradeOffersPanel
          cfg={tradeCfg}
          mine={tradeMine}
          mineError={tradeMineError}
          loading={tradeMine === null}
          onReload={async () => { await loadTradeMine(); await loadBoard(); }} />
      ) : filter === "mine" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6" data-testid="market-mine-grid">
          {mine === null ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} className="aspect-[4/5]" />)
            : mine.length === 0 && myCards.length === 0 ? <p className="text-muted-foreground col-span-full py-12 text-center">No tienes publicaciones activas.</p>
            : [
              ...mine.map((l) => { const r = readListing(l); return (
                <div key={l.id} className="group relative rounded-2xl overflow-hidden glass flex flex-col" data-testid={`mine-listing-${l.id}`}>
                  <span className={`absolute top-3 left-3 z-10 inline-flex items-center gap-1 label-overline text-[9px] px-2 py-1 rounded-full ${l.type === "auction" ? "bg-crimson text-white" : "bg-emerald text-background"}`}>
                    {l.type === "auction" ? <><Gavel size={10} /> Subasta</> : <><Tag size={10} /> Venta</>}
                  </span>
                  <ListingMedia l={l} />
                  <div className="p-5 flex flex-col flex-1">
                    <h3 className="font-display font-bold text-lg leading-tight">{l.title || l.dino_name}</h3>
                    <ListingMeta l={l} />
                    <p className="text-[11px] text-muted-foreground mb-1">{l.type === "auction" ? (r.currentBid !== null ? "Puja actual" : "Puja inicial") : "Precio"}</p>
                    <CoinChip type="normal" amount={r.currentAmount} size="md" />
                    {l.type === "auction" && <p className="text-[11px] text-gold inline-flex items-center gap-1 mt-2"><Clock size={11} /> <Countdown iso={l.ends_at} /></p>}
                    {l.has_bid ? (
                      <p className="text-[11px] text-crimson mt-3">No se puede retirar (ya tiene pujas)</p>
                    ) : (
                      <button onClick={() => { setWithdrawTarget(l); play("click"); }} data-testid={`withdraw-${l.id}`}
                        className="mt-3 inline-flex items-center justify-center gap-1.5 border border-crimson/40 text-crimson font-bold text-sm px-3.5 py-2 rounded-lg hover:bg-crimson/10 transition-all">
                        <Undo2 size={15} /> Retirar{r.withdrawFee !== null ? ` (-${fmtCoin(r.withdrawFee)})` : ""}
                      </button>
                    )}
                  </div>
                </div>
              ); }),
              ...myCards.map((c, i) => renderCard(c, i)),
            ]}
        </div>
      ) : (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6" data-testid="market-grid">
        {items === null ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} className="aspect-[4/5]" />)
          : feed.length === 0 ? (
            filter === "trade" ? (
              <div className="col-span-full py-12 text-center" data-testid="trade-empty">
                <p className="font-display font-bold text-base mb-1">{emptyBoard.headline}</p>
                <p className="text-sm text-muted-foreground leading-snug max-w-md mx-auto">{emptyBoard.body}</p>
              </div>
            ) : <p className="text-muted-foreground col-span-full py-12 text-center">No hay publicaciones ahora mismo. ¡Sé el primero en publicar!</p>
          )
          : feed.map((row, i) => (row.kind === "trade" ? renderCard(row.c, i) : renderListing(row.l, i)))}
      </div>
      )}

      <ConfirmModal
        open={!!withdrawTarget}
        onClose={() => setWithdrawTarget(null)}
        onConfirm={doWithdraw}
        loading={withdrawing}
        tone="gold"
        title={withdrawTarget ? `¿Retirar ${withdrawTarget.dino_name}?` : ""}
        message={withdrawTarget ? withdrawMessage(withdrawTarget, withdrawTarget.source) : null}
        confirmLabel="Retirar dinosaurio"
        abortLabel="Cancelar"
      />

      <ConfirmModal
        open={!!closeTarget}
        onClose={() => setCloseTarget(null)}
        onConfirm={doCloseCard}
        loading={closingCard}
        tone="danger"
        icon={<ArrowLeftRight size={28} />}
        title={closeCopy ? closeCopy.title : ""}
        confirmLabel={closeCopy ? closeCopy.confirmLabel : "Quitar"}
        abortLabel="Volver"
        message={closeCopy ? (
          <ul className="text-left space-y-2">
            {closeCopy.lines.map((l, i) => (<li key={i} className="leading-snug break-words">· {l}</li>))}
          </ul>
        ) : null}
      />

      <AnimatePresence>
        {selling && (
          <SellModal
            board={board}
            tradeCfg={tradeCfg}
            onClose={() => { setSelling(false); play("close"); }}
            onDone={() => { setSelling(false); load(); loadMine(); }}
            onPublished={() => { loadBoard(); setFilter("trade"); }} />
        )}
      </AnimatePresence>
      {offerCard && (
        <TradeOfferModal
          card={offerCard}
          cfg={tradeCfg}
          mine={tradeMine}
          onClose={() => { setOfferCard(null); play("close"); }}
          onDone={() => { setOfferCard(null); loadBoard(); loadTradeMine(); }} />
      )}
      <AnimatePresence>
        {inspectListing && <InspectModal l={inspectListing} onClose={() => { setInspectId(null); play("close"); }} />}
      </AnimatePresence>
    </div>
  );
}
