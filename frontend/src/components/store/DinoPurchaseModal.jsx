import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { X, Check, Dna, Crown, ChevronDown, Bookmark } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";

const PRIME_SURCHARGE = 1000;
// max = mutation slots the tier buys, counted across BOTH pickers (own +
// parental) — the same total the backend charges against.
const TIERS = {
  basic: { label: "Normal", max: 3 },
  prime: { label: "Prime", max: 6 },
};
const tierPrice = (base, key) => base + (key === "prime" ? PRIME_SURCHARGE : 0);
const PRESET_KEY = "dino_mut_preset";

const Shard = ({ c = "" }) => <img src={MEDIA.coinVip} alt="Amberium" className={`inline-block w-4 h-4 object-contain drop-shadow ${c}`} />;

function MutSelect({ label, value, onChange, options, testid }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const sel = options.find((o) => o.key === value);
  return (
    <div ref={ref} className="relative">
      <span className="label-overline text-[9px] text-muted-foreground">{label}</span>
      <button type="button" onClick={() => setOpen((o) => !o)} data-testid={testid}
        className={`mt-1 w-full rounded-[2px] border px-3 py-2.5 text-sm text-left flex items-center justify-between transition-colors ${open ? "border-emerald-500/60 bg-emerald-500/[0.06]" : "border-white/10 bg-black/40 hover:border-white/20"}`}>
        <span className={sel ? "text-foreground" : "text-muted-foreground"}>{sel ? sel.name : "None"}</span>
        <ChevronDown size={15} className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-[70] mt-1 w-full max-h-60 overflow-y-auto rounded-[2px] border border-emerald-500/25 bg-[#0b1210] shadow-2xl" data-testid={`${testid}-list`}>
          <button type="button" onClick={() => { onChange(""); setOpen(false); }} className="w-full text-left px-3 py-2.5 hover:bg-emerald-500/[0.08] border-b border-white/5">
            <p className="text-sm font-semibold">Ninguna</p>
            <p className="text-[11px] text-muted-foreground">Deja este slot vacío.</p>
          </button>
          {options.map((o) => (
            <button key={o.key} type="button" onClick={() => { onChange(o.key); setOpen(false); }}
              className={`w-full text-left px-3 py-2.5 hover:bg-emerald-500/[0.08] border-b border-white/5 last:border-0 ${value === o.key ? "bg-emerald-500/10" : ""}`} data-testid={`${testid}-opt-${o.key}`}>
              <p className="text-sm font-semibold text-foreground">{o.name}</p>
              <p className="text-[11px] text-muted-foreground leading-snug">{o.desc}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const DinoPurchaseModal = ({ item, balance, onClose, onPurchased, play, initialTier = "basic" }) => {
  const [tier, setTier] = useState(initialTier);
  const [muts, setMuts] = useState(["", "", ""]);
  const [parents, setParents] = useState(["", "", ""]);
  const [allMuts, setAllMuts] = useState(null);
  const [buying, setBuying] = useState(false);

  // Ask for this species' catalog: the game's diet rule means a Triceratops
  // cannot carry Hematophagy, and the purchase now rejects what it can't.
  useEffect(() => {
    api.mutations(item.dino_slug).then((r) => setAllMuts(r.data.mutations)).catch(() => setAllMuts([]));
  }, [item.dino_slug]);

  const cfg = TIERS[tier];
  const price = tierPrice(item.price, tier);
  const affordable = balance(item.currency) >= price;
  const cleanName = useMemo(() => item.name.replace(/ Slot$/, ""), [item.name]);
  const taken = [...muts, ...parents].filter(Boolean);
  const chosen = [...new Set(taken)];
  const atBudget = chosen.length >= cfg.max;

  const optsFor = (current) => (allMuts || []).filter((m) => m.key === current || !taken.includes(m.key));
  // An empty slot stops offering options once the tier's slots are spent, so
  // the picker can't build a loadout the purchase would reject.
  const optsForSlot = (current) => (atBudget && !current ? [] : optsFor(current));

  const savePreset = () => {
    play?.("click");
    localStorage.setItem(PRESET_KEY, JSON.stringify({ muts, parents }));
    toast.success("Loadout saved", { description: "It'll auto-fill next time you buy a dino." });
  };
  useEffect(() => {
    try {
      const p = JSON.parse(localStorage.getItem(PRESET_KEY) || "null");
      if (p?.muts) { setMuts(p.muts.slice(0, 3)); setParents((p.parents || ["", "", ""]).slice(0, 3)); }
    } catch {}
  }, []);
  // The saved loadout is ONE global key, not per species, and it restores before the
  // species catalog arrives. A key this species cannot carry would render as "None"
  // (the label is resolved out of the options) while still being submitted - the
  // purchase then 400s naming a mutation that is nowhere on screen. Drop those the
  // moment the catalog lands, so the slot really is empty.
  useEffect(() => {
    if (!allMuts) return;
    const legal = new Set(allMuts.map((m) => m.key));
    const keep = (xs) => xs.map((k) => (k && legal.has(k) ? k : ""));
    setMuts((xs) => (xs.some((k) => k && !legal.has(k)) ? keep(xs) : xs));
    setParents((xs) => (xs.some((k) => k && !legal.has(k)) ? keep(xs) : xs));
  }, [allMuts]);

  const confirm = async () => {
    if (!affordable) { play?.("error"); toast.error("Insufficient balance."); return; }
    setBuying(true);
    try {
      await api.purchaseDino({ item_id: item.id, tier, mutations: muts.filter(Boolean), parents: parents.filter(Boolean) });
      play?.("purchase");
      toast.success(`¡${cleanName} (${cfg.label}) comprado!`, {
        description: "Está en tu Bóveda. Entra al juego como esa especie y pulsa Recuperar para tenerlo.",
      });
      onPurchased?.();
    } catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "Purchase failed."); }
    finally { setBuying(false); }
  };

  return (
    <motion.div className="fixed inset-0 z-[60] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => { onClose(); play?.("close"); }} />
      <motion.div initial={{ opacity: 0, scale: 0.94, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.94, y: 20 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative rounded-[2px] w-full max-w-3xl overflow-hidden max-h-[92vh] flex flex-col border border-emerald-500/25"
        style={{ background: "linear-gradient(160deg, #0e1512, #080b0a)" }} data-testid="dino-purchase-modal">
        <button onClick={() => { onClose(); play?.("close"); }} data-testid="dino-modal-close" className="absolute top-4 right-4 z-10 p-2 rounded-[2px] hover:bg-white/10 transition-colors"><X size={18} /></button>

        <div className="p-6 sm:p-7 overflow-y-auto">
          {/* Header */}
          <p className="label-overline text-[10px] text-emerald-400 mb-1">Comprar</p>
          <h3 className="font-display font-extrabold text-3xl leading-none">{cleanName}</h3>
          <p className="text-sm text-muted-foreground mt-1.5">{item.type || "Dinosaur"} · <span style={{ color: "#7CA842" }}>{item.rarity}</span></p>

          {/* Version selector */}
          <div className="grid grid-cols-2 gap-3 mt-5">
            {Object.entries(TIERS).map(([key, t]) => {
              const sel = tier === key; const prime = key === "prime";
              return (
                <button key={key} onClick={() => { play?.("click"); setTier(key); }} data-testid={`dino-tier-${key}`}
                  className="text-center rounded-[2px] p-4 border transition-all"
                  style={sel ? { borderColor: prime ? "#7CA842" : "#10B981", background: `${prime ? "#7CA842" : "#10B981"}12` } : { borderColor: "rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.02)" }}>
                  <div className="flex items-center justify-center gap-1.5 mb-2">
                    <span className="font-display font-bold uppercase tracking-widest text-sm inline-flex items-center gap-1.5">{prime && <Crown size={13} className="text-gold" />}{t.label}</span>
                    {sel && <Check size={14} style={{ color: prime ? "#7CA842" : "#10B981" }} />}
                  </div>
                  <p className="inline-flex items-center gap-1.5 font-display font-bold text-lg tabular-nums" style={{ color: prime ? "#7CA842" : "#e8e8e8" }}><Shard /> {tierPrice(item.price, key).toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                </button>
              );
            })}
          </div>

          {/* Mutations */}
          <div className="flex items-center justify-between mt-6 mb-3">
            <p className="label-overline text-[10px] text-muted-foreground">Mutaciones <span className="text-muted-foreground/50">({chosen.length}/{cfg.max} slots)</span></p>
            <button onClick={savePreset} data-testid="dino-save-preset" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border border-dashed border-white/15 rounded-[2px] px-2.5 py-1.5 transition-colors"><Bookmark size={12} /> Save</button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="dino-mutation-slots">
            {[0, 1, 2].map((i) => (
              <MutSelect key={i} label={`Mutation ${i + 1}`} value={muts[i]} options={optsForSlot(muts[i])}
                onChange={(v) => { play?.("click"); setMuts((p) => { const a = [...p]; a[i] = v; return a; }); }} testid={`dino-mut-slot-${i}`} />
            ))}
          </div>

          {/* Parents */}
          <p className="label-overline text-[10px] text-muted-foreground mt-5 mb-3">Linaje Parental <span className="text-muted-foreground/50">(inherited mutations)</span></p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="dino-parent-slots">
            {[0, 1, 2].map((i) => (
              <MutSelect key={i} label={`Parent ${i + 1}`} value={parents[i]} options={optsForSlot(parents[i])}
                onChange={(v) => { play?.("click"); setParents((p) => { const a = [...p]; a[i] = v; return a; }); }} testid={`dino-parent-slot-${i}`} />
            ))}
          </div>

          {/* Total */}
          <div className="flex items-center justify-between border-t border-white/10 pt-4 mt-6">
            <div>
              <p className="label-overline text-[10px] text-muted-foreground">Total</p>
              <p className="inline-flex items-center gap-1.5 font-display font-extrabold text-2xl mt-0.5" style={{ color: tier === "prime" ? "#7CA842" : "#10B981" }}><Shard /> {price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
              <p className="text-[11px] text-muted-foreground">{cfg.label} · {chosen.length} mutation{chosen.length === 1 ? "" : "s"}</p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => { onClose(); play?.("close"); }} className="rounded-[2px] px-6 py-3 font-semibold border border-white/10 hover:bg-white/5 transition-colors">Cancelar</button>
              <button onClick={confirm} disabled={buying || !affordable} data-testid="confirm-dino-purchase"
                className="inline-flex items-center justify-center gap-2 font-display font-bold px-7 py-3 rounded-[2px] transition-all disabled:opacity-50"
                style={{ background: tier === "prime" ? "linear-gradient(180deg,#7CA842,#b8860b)" : "linear-gradient(180deg,#10B981,#0b7a54)", color: "#04120c" }}>
                {buying ? "Processing…" : !affordable ? "Not enough" : <><Check size={16} /> Buy {cfg.label}</>}
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};
