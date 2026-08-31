import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Unlock, Check, X, Gem, ArrowLeftRight, Loader2, User, AlertTriangle, Scale } from "lucide-react";

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
    <Comp onClick={onClick} onMouseEnter={onHover} data-testid={testid}
      whileHover={onClick ? { scale: 1.1, zIndex: 5 } : undefined} whileTap={onClick ? { scale: 0.88 } : undefined} transition={SPRING}
      className={`relative aspect-square w-full rounded-[3px] overflow-hidden ${onClick ? "cursor-pointer" : "cursor-default"} ${dim ? "opacity-25 grayscale pointer-events-none" : ""}`}
      style={{ border: `1px solid ${color}88`, background: "#0f120b", boxShadow: `inset 0 0 10px ${color}22` }}>
      <div className="absolute inset-0" style={{ background: `radial-gradient(75% 75% at 50% 30%, ${color}2e, #0b0d09 88%)` }} />
      {it.image ? <img src={it.image} alt={it.name} className="absolute inset-0 w-full h-full object-cover" /> : <Gem className="absolute inset-0 m-auto opacity-40" size={16} />}
      {badge != null && <span className="absolute bottom-0 right-0.5 text-[10px] font-black tabular-nums text-white" style={{ textShadow: "0 1px 2px #000" }}>{badge}</span>}
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
  <span className="inline-flex items-center gap-1 font-code font-black tabular-nums text-gold text-lg"><Gem size={15} /> {v}</span>
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

  const [amber, setAmber] = useState(me.offer.amber || 0);
  const amberTimer = useRef(null); const focused = useRef(false);
  useEffect(() => { if (!focused.current) setAmber(me.offer.amber || 0); }, [me.offer.amber]);
  useEffect(() => { if (!alert) return; const t = setTimeout(() => onClearAlert?.(), 6000); return () => clearTimeout(t); }, [alert, onClearAlert]);

  const click = () => play?.("click");
  const send = (items, a) => onOffer(items.map((i) => ({ inv_id: i.inv_id, qty: i.qty })), a);
  const addItem = (it) => { if (me.locked) return; const cur = offeredMap[it.inv_id] || 0; if (cur >= it.quantity) return; click();
    const next = myItems.some((x) => x.inv_id === it.inv_id) ? myItems.map((x) => x.inv_id === it.inv_id ? { ...x, qty: x.qty + 1 } : x) : [...myItems, { inv_id: it.inv_id, qty: 1 }];
    send(next, amber); };
  const removeItem = (invId) => { if (me.locked) return; click(); send(myItems.map((x) => x.inv_id === invId ? { ...x, qty: x.qty - 1 } : x).filter((x) => x.qty > 0), amber); };
  const onAmber = (v) => { focused.current = true; const val = Math.max(0, Math.min(amberMax, parseInt(v || "0", 10) || 0)); setAmber(val);
    clearTimeout(amberTimer.current); amberTimer.current = setTimeout(() => { focused.current = false; send(myItems, val); }, 450); };

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
                <SlotGrid items={invItems.map((it) => ({ ...it }))} cols={4} rows={8} interactive testid="my-inventory-grid"
                  renderItem={(it) => { const left = it.quantity - (offeredMap[it.inv_id] || 0);
                    return <Tile it={it} badge={left} dim={left <= 0} onHover={() => play?.("hover")} onClick={() => addItem(it)} testid={`inv-item-${it.inv_id}`} />; }} />
              </div>}
        </div>

        {/* 2 · MY OFFER */}
        <motion.div layout className="rounded-lg border p-2.5" style={{ borderColor: me.confirmed ? "rgba(52,211,153,.5)" : me.locked ? "rgba(202,169,104,.5)" : "rgba(255,255,255,.1)", background: "rgba(202,169,104,.05)" }}>
          {colHead(<span className="flex items-center gap-1">Tu oferta {me.locked && <Lock size={10} className="text-gold" />}{me.confirmed && <Check size={11} className="text-emerald" />}</span>,
            <input type="number" min="0" max={amberMax} value={amber} disabled={me.locked} onChange={(e) => onAmber(e.target.value)} data-testid="my-amber-input"
              className="w-20 px-2 py-1 rounded glass border border-gold/20 text-xs text-gold font-bold outline-none focus:border-gold/60 disabled:opacity-50" />)}
          <SlotGrid items={myItems} cols={4} rows={6} testid="my-offer-slots"
            renderItem={(i) => { const meta = invLookup[i.inv_id] || i; return <Tile it={meta} badge={i.qty} onClick={me.locked ? undefined : () => removeItem(i.inv_id)} testid={`my-offered-${i.inv_id}`} />; }} />
          <p className="text-[10px] text-muted-foreground mt-1.5 text-center">Amberium: {amber} / {amberMax} hoy</p>
        </motion.div>

        {/* 3 · THEIR OFFER */}
        <motion.div layout className="rounded-lg border p-2.5" style={{ borderColor: them.confirmed ? "rgba(52,211,153,.5)" : them.locked ? "rgba(202,169,104,.5)" : "rgba(255,255,255,.1)", background: "rgba(255,255,255,.02)" }}>
          {colHead(<span className="flex items-center gap-1">Su oferta {them.locked && <Lock size={10} className="text-gold" />}{them.confirmed && <Check size={11} className="text-emerald" />}</span>,
            <motion.span key={them.offer.amber || 0} initial={{ scale: 1.3, color: "#CAA968" }} animate={{ scale: 1, color: "#e5c07b" }} transition={SPRING} className="text-xs font-bold text-gold flex items-center gap-1"><Gem size={11} />{them.offer.amber || 0}</motion.span>)}
          <SlotGrid items={theirItems} cols={4} rows={6} testid="their-offer-slots"
            renderItem={(i) => <Tile it={i} badge={i.qty} testid={`their-offered-${i.inv_id}`} />} />
        </motion.div>

        {/* 4 · THEIR INVENTORY */}
        <div className="rounded-lg border border-white/10 bg-black/25 p-2.5">
          {colHead(`Inventario de ${them.name}`, <AmberTotal v={peerInv?.amber_balance ?? 0} />)}
          {peerItems.length === 0
            ? <p className="text-xs text-muted-foreground text-center py-8">Sin objetos</p>
            : <div className="max-h-[420px] overflow-y-auto pr-0.5">
                <SlotGrid items={peerItems.map((it) => ({ ...it }))} cols={4} rows={8} testid="their-inventory-grid"
                  renderItem={(it) => <Tile it={it} badge={it.quantity} testid={`peer-item-${it.inv_id}`} />} />
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
            <Scale size={17} /> {me.confirmed ? <>Esperando…</> : "Barter"}
          </motion.button>
        </div>
        {!bothLocked && <p className="text-center text-[11px] text-muted-foreground">Ambos deben <b>bloquear</b> su oferta para confirmar. Editar reinicia los bloqueos.</p>}
        {me.confirmed && !them.confirmed && <p className="text-center text-[11px] text-gold flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Esperando la confirmación de {them.name}…</p>}
      </div>
    </div>
  );
}
