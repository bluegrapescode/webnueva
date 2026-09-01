import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Unlock, Check, X, Gem, ArrowLeftRight, Loader2, User, AlertTriangle, Scale } from "lucide-react";
import { MEDIA } from "@/lib/media";

const AmberIcon = ({ size = 15, className = "" }) => (
  <img src={MEDIA.coinVip} alt="Amberium" className={`inline-block object-contain ${className}`} style={{ width: size, height: size }} />
);

const RC = {
  common: "#8e9297", Common: "#8e9297", uncommon: "#34D399", Uncommon: "#34D399",
  rare: "#38bdf8", Rare: "#38bdf8", epic: "#a855f7", Epic: "#a855f7",
  legendary: "#f59e0b", Legendary: "#f59e0b", mythic: "#ef4444", Mythic: "#ef4444",
};
const rc = (r) => RC[r] || "#6b7280";
const SPRING = { type: "spring", stiffness: 420, damping: 26 };

function Tile({ it, badge, onClick, onHover, dim, testid }) {
  const color = rc(it.rarity);
  const Comp = onClick ? motion.button : motion.div;
  return (
    <Comp onClick={onClick} onMouseEnter={onHover} data-testid={testid} title={`${it.name}${it.rarity ? " · " + it.rarity : ""}`}
      whileHover={onClick ? { scale: 1.1, zIndex: 5 } : undefined} whileTap={onClick ? { scale: 0.88 } : undefined} transition={SPRING}
      className={`relative aspect-square w-full rounded-[3px] overflow-hidden ${onClick ? "cursor-pointer" : "cursor-default"} ${dim ? "opacity-25 grayscale pointer-events-none" : ""}`}
      style={{ border: `1px solid ${color}88`, background: "#0f120b", boxShadow: `inset 0 0 10px ${color}22` }}>
      <div className="absolute inset-0" style={{ background: `radial-gradient(75% 75% at 50% 30%, ${color}2e, #0b0d09 88%)` }} />
      {it.image ? <img src={it.image} alt={it.name} className="absolute inset-0 w-full h-full object-cover" /> : <Gem className="absolute inset-0 m-auto opacity-40" size={16} />}
      {badge != null && <span className="absolute top-0.5 right-0.5 z-[3] rounded-[3px] px-1 py-[1px] text-[10px] font-black tabular-nums text-white leading-none" style={{ background: "rgba(0,0,0,.82)", border: `1px solid ${color}aa`, boxShadow: `0 0 6px ${color}55` }}>×{badge}</span>}
      {/* nombre del objeto (siempre visible) */}
      <span data-testid={testid ? `${testid}-name` : undefined}
        className="absolute inset-x-0 bottom-0 px-0.5 pt-2 pb-[1px] text-[8px] leading-[1.05] font-semibold text-white text-center truncate"
        style={{ background: "linear-gradient(to top, rgba(0,0,0,.9) 30%, rgba(0,0,0,0))" }}>
        {it.name}
      </span>
    </Comp>
  );
}

function SlotGrid({ items, cols = 4, rows = 6, renderItem, interactive, testid }) {
  const total = cols * rows;
  const seen = new Set();
  const uniq = items.filter((it) => (seen.has(it.inv_id) ? false : seen.add(it.inv_id)));
  const empties = Math.max(0, total - uniq.length);
  return (
    <div className={`grid gap-1 content-start`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }} data-testid={testid}>
      <AnimatePresence mode="popLayout" initial={false}>
        {uniq.map((it) => (
          <motion.div key={it.inv_id} layout initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }} transition={SPRING}>
            {renderItem(it)}
          </motion.div>
        ))}
      </AnimatePresence>
      {Array.from({ length: empties }).map((_, i) => (
        <div key={"e" + i} className="aspect-square rounded-[3px] border border-[#CAA968]/12 bg-black/30" />
      ))}
    </div>
  );
}

function Avatar({ src, name, side }) {
  return (
    <div className={`flex flex-col items-center ${side}`}>
      <div className="w-16 h-16 rounded-xl overflow-hidden border-2 border-[#CAA968]/60" style={{ boxShadow: "0 0 20px rgba(202,169,104,.35)" }}>
        {src ? <img src={src} alt={name} className="w-full h-full object-cover" /> : <User className="m-auto mt-4 opacity-50" size={26} />}
      </div>
      <span className="font-display font-bold text-sm mt-1.5">{name}</span>
    </div>
  );
}

const AmberTotal = ({ v }) => (
  <span className="inline-flex items-center gap-1 font-code font-black tabular-nums text-gold text-lg"><AmberIcon size={16} /> {v}</span>
);

export function TradeRoom({ session, inv, peerInv, play, onOffer, onLock, onConfirm, onCancel, alert, onClearAlert }) {
  const me = session.me, them = session.them;
  const myItems = me.offer.items || [];
  const theirItems = them.offer.items || [];
  const offeredMap = useMemo(() => Object.fromEntries(myItems.map((i) => [i.inv_id, i.qty])), [myItems]);
  const invItems = inv?.items || [];
  const peerItems = peerInv?.items || [];
  const amberMax = Math.min(inv?.amber?.balance ?? 0, inv?.amber?.remaining_today ?? 0);
  const invLookup = useMemo(() => Object.fromEntries(invItems.map((i) => [i.inv_id, i])), [invItems]);

  // ── stacking: identical items collapse into one slot with ×N ──
  const stackKey = (it) => `${it.item_id ?? it.name}|${it.category ?? ""}|${it.rarity ?? ""}|${it.tier ?? ""}`;
  const stackId = (it) => "stk_" + stackKey(it).replace(/[^a-z0-9]+/gi, "_");
  const groupInv = (items) => {
    const m = new Map();
    for (const it of items) {
      const k = stackKey(it);
      if (!m.has(k)) m.set(k, { ...it, inv_id: stackId(it), total: 0, rows: [] });
      const g = m.get(k); const q = it.quantity ?? 1;
      g.total += q; g.rows.push({ inv_id: it.inv_id, quantity: q });
    }
    return [...m.values()];
  };
  const groupOffer = (items, lookup) => {
    const m = new Map();
    for (const i of items) {
      const meta = (lookup && lookup[i.inv_id]) || i;
      const k = stackKey(meta);
      if (!m.has(k)) m.set(k, { ...meta, inv_id: stackId(meta), qty: 0, rows: [] });
      const g = m.get(k); g.qty += i.qty; g.rows.push({ inv_id: i.inv_id, qty: i.qty });
    }
    return [...m.values()];
  };
  const myInvStacks = useMemo(() => groupInv(invItems), [invItems, offeredMap]);
  const myOfferStacks = useMemo(() => groupOffer(myItems, invLookup), [myItems, invLookup]);
  const theirOfferStacks = useMemo(() => groupOffer(theirItems, null), [theirItems]);
  const peerStacks = useMemo(() => groupInv(peerItems), [peerItems]);
  const offeredForRows = (rows) => rows.reduce((s, r) => s + (offeredMap[r.inv_id] || 0), 0);

  const [amber, setAmber] = useState(me.offer.amber || 0);
  const amberTimer = useRef(null); const focused = useRef(false);
  useEffect(() => { if (!focused.current) setAmber(me.offer.amber || 0); }, [me.offer.amber]);
  useEffect(() => { if (!alert) return; const t = setTimeout(() => onClearAlert?.(), 6000); return () => clearTimeout(t); }, [alert, onClearAlert]);

  const click = () => play?.("click");
  const coin = () => play?.("coinClick");
  const send = (items, a) => onOffer(items.map((i) => ({ inv_id: i.inv_id, qty: i.qty })), a);
  // add one unit of a whole stack: allocate to the first underlying row with capacity
  const addStack = (g) => {
    if (me.locked) return;
    if (offeredForRows(g.rows) >= g.total) return;
    coin();
    let next = [...myItems];
    for (const row of g.rows) {
      if ((offeredMap[row.inv_id] || 0) < row.quantity) {
        next = next.some((x) => x.inv_id === row.inv_id)
          ? next.map((x) => x.inv_id === row.inv_id ? { ...x, qty: x.qty + 1 } : x)
          : [...next, { inv_id: row.inv_id, qty: 1 }];
        break;
      }
    }
    send(next, amber);
  };
  // remove one unit of a stack: take it from the last offered underlying row
  const removeStack = (g) => {
    if (me.locked) return;
    const offeredRows = g.rows.filter((r) => (offeredMap[r.inv_id] || 0) > 0);
    const row = offeredRows[offeredRows.length - 1];
    if (!row) return;
    coin();
    send(myItems.map((x) => x.inv_id === row.inv_id ? { ...x, qty: x.qty - 1 } : x).filter((x) => x.qty > 0), amber);
  };
  const onAmber = (v) => { focused.current = true; const val = Math.max(0, Math.min(amberMax, parseInt(v || "0", 10) || 0)); setAmber(val);
    clearTimeout(amberTimer.current); amberTimer.current = setTimeout(() => { focused.current = false; send(myItems, val); }, 450); };
  const stepAmber = (d) => { if (me.locked) return; coin(); onAmber(String(Math.max(0, Math.min(amberMax, (amber || 0) + d)))); };

  const bothLocked = me.locked && them.locked;

  const colHead = (label, right) => (
    <div className="flex items-center justify-between mb-1.5 px-0.5">
      <span className="label-overline text-[10px] text-muted-foreground">{label}</span>
      {right}
    </div>
  );

  return (
    <div data-testid="trade-room" className="relative rounded-2xl p-4 sm:p-6"
      style={{ border: "1px solid rgba(202,169,104,.35)", background: "linear-gradient(180deg,#0e120a,#0a0c07)", boxShadow: "inset 0 0 60px rgba(0,0,0,.6)" }}>
      {/* corner flourishes */}
      {["top-2 left-2", "top-2 right-2", "bottom-2 left-2", "bottom-2 right-2"].map((c, i) => (
        <div key={i} className={`absolute ${c} w-5 h-5 border-gold/50`} style={{ borderTopWidth: c.includes("top") ? 2 : 0, borderBottomWidth: c.includes("bottom") ? 2 : 0, borderLeftWidth: c.includes("left") ? 2 : 0, borderRightWidth: c.includes("right") ? 2 : 0 }} />
      ))}

      {/* header: avatars + title */}
      <div className="flex items-center justify-between">
        <Avatar src={them && me.user_id ? undefined : undefined} name="Tú" />
        <div className="text-center">
          <p className="font-display font-black text-lg tracking-tight flex items-center gap-2 justify-center"><ArrowLeftRight className="text-gold" size={18} /> Intercambio</p>
          <button onClick={() => { click(); onCancel(); }} data-testid="trade-cancel" className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-crimson transition-colors"><X size={12} /> Cancelar</button>
        </div>
        <Avatar src={them.avatar} name={them.name} />
      </div>

      {/* anti-scam alert */}
      <AnimatePresence>
        {alert && (
          <motion.div initial={{ opacity: 0, y: -8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
            data-testid="trade-scam-alert"
            className="mt-3 flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold border border-crimson/50 bg-crimson/15 text-crimson"
            style={{ boxShadow: "0 0 24px rgba(214,60,60,.35)" }}>
            <AlertTriangle size={16} className="animate-pulse" />
            {alert.by || "El otro jugador"} cambió su oferta después de que bloqueaste. Revísala antes de confirmar.
          </motion.div>
        )}
      </AnimatePresence>

      {/* 4-column trade grid */}
      <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* 1 · MY INVENTORY */}
        <div className="rounded-lg border border-white/10 bg-black/25 p-2.5">
          {colHead("Tu inventario", <AmberTotal v={inv?.amber?.balance ?? 0} />)}
          {invItems.length === 0
            ? <p className="text-xs text-muted-foreground text-center py-8">Sin objetos</p>
            : <div className="max-h-[420px] overflow-y-auto pr-0.5">
                <SlotGrid items={myInvStacks} cols={4} rows={8} interactive testid="my-inventory-grid"
                  renderItem={(g) => { const left = g.total - offeredForRows(g.rows);
                    return <Tile it={g} badge={left} dim={left <= 0} onHover={() => play?.("hover")} onClick={() => addStack(g)} testid={`inv-item-${g.item_id || g.inv_id}`} />; }} />
              </div>}
        </div>

        {/* 2 · MY OFFER */}
        <motion.div layout className="rounded-lg border p-2.5" style={{ borderColor: me.confirmed ? "rgba(52,211,153,.5)" : me.locked ? "rgba(202,169,104,.5)" : "rgba(255,255,255,.1)", background: "rgba(202,169,104,.05)" }}>
          {colHead(<span className="flex items-center gap-1">Tu oferta {me.locked && <Lock size={10} className="text-gold" />}{me.confirmed && <Check size={11} className="text-emerald" />}</span>,
            <span className="flex items-center gap-1 text-xs font-bold text-gold"><AmberIcon size={13} /> {amber}</span>)}
          <SlotGrid items={myOfferStacks} cols={4} rows={6} testid="my-offer-slots"
            renderItem={(g) => <Tile it={g} badge={g.qty} onClick={me.locked ? undefined : () => removeStack(g)} testid={`my-offered-${g.item_id || g.inv_id}`} />} />
          {/* Amberium control — clear +/- stepper */}
          <div className="mt-2.5 rounded-lg border border-gold/25 bg-gold/[0.06] p-2" data-testid="amber-control">
            <div className="flex items-center justify-between mb-1.5">
              <span className="flex items-center gap-1.5 text-[11px] font-bold text-gold"><AmberIcon size={14} /> Amberium a enviar</span>
              <span className="text-[10px] text-muted-foreground">máx {amberMax} hoy</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button type="button" onClick={() => stepAmber(-10)} disabled={me.locked || amber <= 0} data-testid="amber-minus"
                className="w-9 h-9 shrink-0 rounded-md bg-white/10 border border-white/10 text-lg font-black text-gold leading-none disabled:opacity-40 hover:bg-white/15 transition-colors">−</button>
              <input type="number" min="0" max={amberMax} value={amber} disabled={me.locked} onChange={(e) => onAmber(e.target.value)} data-testid="my-amber-input"
                className="flex-1 min-w-0 px-2 py-2 rounded-md glass border border-gold/25 text-center text-sm text-gold font-bold outline-none focus:border-gold/60 disabled:opacity-50" />
              <button type="button" onClick={() => stepAmber(10)} disabled={me.locked || amber >= amberMax} data-testid="amber-plus"
                className="w-9 h-9 shrink-0 rounded-md bg-white/10 border border-white/10 text-lg font-black text-gold leading-none disabled:opacity-40 hover:bg-white/15 transition-colors">+</button>
            </div>
          </div>
        </motion.div>

        {/* 3 · THEIR OFFER */}
        <motion.div layout className="rounded-lg border p-2.5" style={{ borderColor: them.confirmed ? "rgba(52,211,153,.5)" : them.locked ? "rgba(202,169,104,.5)" : "rgba(255,255,255,.1)", background: "rgba(255,255,255,.02)" }}>
          {colHead(<span className="flex items-center gap-1">Su oferta {them.locked && <Lock size={10} className="text-gold" />}{them.confirmed && <Check size={11} className="text-emerald" />}</span>,
            <motion.span key={them.offer.amber || 0} initial={{ scale: 1.3, color: "#CAA968" }} animate={{ scale: 1, color: "#e5c07b" }} transition={SPRING} className="text-xs font-bold text-gold flex items-center gap-1"><AmberIcon size={13} />{them.offer.amber || 0}</motion.span>)}
          <SlotGrid items={theirOfferStacks} cols={4} rows={6} testid="their-offer-slots"
            renderItem={(g) => <Tile it={g} badge={g.qty} testid={`their-offered-${g.item_id || g.inv_id}`} />} />
        </motion.div>

        {/* 4 · THEIR INVENTORY */}
        <div className="rounded-lg border border-white/10 bg-black/25 p-2.5">
          {colHead(`Inventario de ${them.name}`, <AmberTotal v={peerInv?.amber_balance ?? 0} />)}
          {peerItems.length === 0
            ? <p className="text-xs text-muted-foreground text-center py-8">Sin objetos</p>
            : <div className="max-h-[420px] overflow-y-auto pr-0.5">
                <SlotGrid items={peerStacks} cols={4} rows={8} testid="their-inventory-grid"
                  renderItem={(g) => <Tile it={g} badge={g.total} testid={`peer-item-${g.item_id || g.inv_id}`} />} />
              </div>}
        </div>
      </div>

      {/* central BARTER control */}
      <div className="mt-6 flex flex-col items-center gap-2">
        <div className="flex items-center gap-3">
          <motion.button whileTap={{ scale: 0.94 }} onClick={() => { click(); onLock(!me.locked); }} data-testid="trade-lock-btn"
            className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-bold border transition-colors ${me.locked ? "bg-gold/15 text-gold border-gold/40" : "bg-white/10 border-white/10 hover:bg-white/15"}`}>
            {me.locked ? <><Unlock size={15} /> Desbloquear</> : <><Lock size={15} /> Bloquear</>}
          </motion.button>
          <motion.button whileTap={{ scale: 0.94 }} whileHover={bothLocked && !me.confirmed ? { scale: 1.03 } : undefined}
            onClick={() => { click(); onConfirm(); }} disabled={!bothLocked || me.confirmed} data-testid="trade-confirm-btn"
            animate={bothLocked && !me.confirmed ? { boxShadow: ["0 0 0 0 rgba(202,169,104,0)", "0 0 26px 3px rgba(202,169,104,.6)", "0 0 0 0 rgba(202,169,104,0)"] } : {}}
            transition={bothLocked && !me.confirmed ? { duration: 1.6, repeat: Infinity } : { duration: 0.2 }}
            className="inline-flex items-center gap-2 rounded-lg px-10 py-3 font-black uppercase tracking-widest text-background disabled:opacity-40"
            style={{ background: "linear-gradient(135deg,#E9D8A6,#CAA968)" }}>
            <Scale size={17} /> {me.confirmed ? <>Esperando…</> : "Confirmar"}
          </motion.button>
        </div>
        {!bothLocked && <p className="text-center text-[11px] text-muted-foreground">Ambos deben <b>bloquear</b> su oferta para confirmar. Editar reinicia los bloqueos.</p>}
        {me.confirmed && !them.confirmed && <p className="text-center text-[11px] text-gold flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Esperando la confirmación de {them.name}…</p>}
      </div>
    </div>
  );
}
