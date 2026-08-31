import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Unlock, Check, X, Gem, Plus, Minus, ArrowLeftRight, Loader2 } from "lucide-react";

const RARITY_COLOR = {
  common: "#8e9297", Common: "#8e9297", uncommon: "#34D399", Uncommon: "#34D399",
  rare: "#38bdf8", Rare: "#38bdf8", epic: "#a855f7", Epic: "#a855f7",
  legendary: "#f59e0b", Legendary: "#f59e0b", mythic: "#ef4444", Mythic: "#ef4444",
};
const rc = (r) => RARITY_COLOR[r] || "#CAA968";
const SPRING = { type: "spring", stiffness: 420, damping: 26 };

function ItemTile({ it, badge, onClick, onHover, dim, testid }) {
  const color = rc(it.rarity);
  const Comp = onClick ? motion.button : motion.div;
  return (
    <Comp
      onClick={onClick} onMouseEnter={onHover} data-testid={testid}
      whileHover={onClick ? { scale: 1.09 } : undefined}
      whileTap={onClick ? { scale: 0.88 } : undefined}
      transition={SPRING}
      className={`relative aspect-square rounded-md overflow-hidden border ${onClick ? "cursor-pointer" : "cursor-default"} ${dim ? "opacity-30 grayscale pointer-events-none" : ""}`}
      style={{ borderColor: `${color}66`, boxShadow: `inset 0 0 0 1px ${color}22, 0 4px 14px -6px ${color}88` }}
    >
      <div className="absolute inset-0" style={{ background: `radial-gradient(70% 70% at 50% 30%, ${color}33, #0b0d09 85%)` }} />
      {it.image ? <img src={it.image} alt={it.name} className="absolute inset-0 w-full h-full object-cover" /> : <Gem className="absolute inset-0 m-auto opacity-40" size={20} />}
      {badge != null && (
        <span className="absolute bottom-0.5 right-0.5 text-[10px] font-black tabular-nums px-1 rounded bg-black/70 text-white">{badge}</span>
      )}
    </Comp>
  );
}

// Offer columns with synchronized spring-in / spring-out on every add/remove.
function AnimatedSlots({ items, renderItem, count = 8, testid }) {
  // defensive dedupe by inv_id to avoid transient duplicate React keys
  const seen = new Set();
  const uniq = items.filter((it) => (seen.has(it.inv_id) ? false : seen.add(it.inv_id)));
  const empties = Math.max(0, count - uniq.length);
  return (
    <div className="grid grid-cols-4 gap-1.5" data-testid={testid}>
      <AnimatePresence mode="popLayout" initial={false}>
        {uniq.map((it) => (
          <motion.div key={it.inv_id} layout
            initial={{ scale: 0, opacity: 0, y: -8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={SPRING}>
            {renderItem(it)}
          </motion.div>
        ))}
      </AnimatePresence>
      {Array.from({ length: empties }).map((_, i) => (
        <div key={"e" + i} className="aspect-square rounded-md border border-white/[0.06] bg-white/[0.02]" />
      ))}
    </div>
  );
}

export function TradeRoom({ session, inv, play, onOffer, onLock, onConfirm, onCancel }) {
  const me = session.me, them = session.them;
  const myItems = me.offer.items || [];
  const theirItems = them.offer.items || [];
  const offeredMap = useMemo(() => Object.fromEntries(myItems.map((i) => [i.inv_id, i.qty])), [myItems]);
  const invItems = inv?.items || [];
  const amberMax = Math.min(inv?.amber?.balance ?? 0, inv?.amber?.remaining_today ?? 0);
  const invLookup = useMemo(() => Object.fromEntries(invItems.map((i) => [i.inv_id, i])), [invItems]);

  const [amber, setAmber] = useState(me.offer.amber || 0);
  const amberTimer = useRef(null);
  const focused = useRef(false);
  useEffect(() => { if (!focused.current) setAmber(me.offer.amber || 0); }, [me.offer.amber]);

  const click = () => play?.("click");
  const sendOffer = (items, amberVal) => onOffer(items.map((i) => ({ inv_id: i.inv_id, qty: i.qty })), amberVal);

  const addItem = (invIt) => {
    if (me.locked) return;
    const cur = offeredMap[invIt.inv_id] || 0;
    if (cur >= invIt.quantity) return;
    click();
    const next = myItems.some((i) => i.inv_id === invIt.inv_id)
      ? myItems.map((i) => i.inv_id === invIt.inv_id ? { ...i, qty: i.qty + 1 } : i)
      : [...myItems, { inv_id: invIt.inv_id, qty: 1 }];
    sendOffer(next, amber);
  };
  const stepItem = (invId, delta) => {
    if (me.locked) return;
    click();
    const next = myItems.map((i) => i.inv_id === invId ? { ...i, qty: i.qty + delta } : i).filter((i) => i.qty > 0);
    sendOffer(next, amber);
  };
  const onAmber = (v) => {
    focused.current = true;
    const val = Math.max(0, Math.min(amberMax, parseInt(v || "0", 10) || 0));
    setAmber(val);
    clearTimeout(amberTimer.current);
    amberTimer.current = setTimeout(() => { focused.current = false; sendOffer(myItems, val); }, 450);
  };

  const bothLocked = me.locked && them.locked;

  return (
    <div data-testid="trade-room">
      <div className="flex items-center justify-between mb-5">
        <h2 className="font-display font-black text-2xl tracking-tight flex items-center gap-2"><ArrowLeftRight className="text-gold" size={24} /> Intercambio en curso</h2>
        <button onClick={() => { click(); onCancel(); }} data-testid="trade-cancel" className="inline-flex items-center gap-1.5 text-sm rounded-lg px-3 py-2 bg-white/10 hover:bg-crimson/20 hover:text-crimson border border-white/10 transition-colors"><X size={15} /> Cancelar</button>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* ── MY SIDE ── */}
        <motion.div layout className="glass rounded-2xl border border-gold/20 p-4"
          animate={{ boxShadow: me.confirmed ? "0 0 0 1.5px rgba(52,211,153,.6)" : me.locked ? "0 0 0 1.5px rgba(202,169,104,.5)" : "0 0 0 0px rgba(0,0,0,0)" }}
          transition={{ duration: 0.3 }}>
          <div className="flex items-center justify-between mb-3">
            <span className="font-display font-bold text-lg">Tu oferta</span>
            <div className="flex items-center gap-1.5 text-xs">
              <AnimatePresence>
                {me.locked && <motion.span initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1 text-gold"><Lock size={12} /> Bloqueada</motion.span>}
                {me.confirmed && <motion.span initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1 text-emerald"><Check size={12} /> Confirmado</motion.span>}
              </AnimatePresence>
            </div>
          </div>

          <AnimatedSlots testid="my-offer-slots" items={myItems} renderItem={(i) => {
            const meta = invLookup[i.inv_id] || i;
            return (
              <div className="relative group">
                <ItemTile it={meta} badge={i.qty} onClick={me.locked ? undefined : () => stepItem(i.inv_id, -1)} testid={`my-offered-${i.inv_id}`} />
                {!me.locked && (
                  <div className="absolute -top-1.5 -right-1.5 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => stepItem(i.inv_id, -1)} className="w-4 h-4 rounded-full bg-crimson text-white grid place-items-center"><Minus size={9} /></button>
                    <button onClick={() => stepItem(i.inv_id, 1)} className="w-4 h-4 rounded-full bg-emerald text-background grid place-items-center"><Plus size={9} /></button>
                  </div>
                )}
              </div>
            );
          }} />

          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold"><Gem size={15} /> Amberium</span>
            <input type="number" min="0" max={amberMax} value={amber} disabled={me.locked} onChange={(e) => onAmber(e.target.value)} data-testid="my-amber-input"
              className="w-28 px-2.5 py-1.5 rounded-lg glass border border-white/10 text-sm outline-none focus:border-gold/50 disabled:opacity-50" />
            <span className="text-[11px] text-muted-foreground">/ {amberMax} disp. hoy</span>
          </div>

          <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-5 mb-2">Tu inventario {me.locked && <span className="text-gold normal-case">· desbloquea para editar</span>}</p>
          {invItems.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">No tienes objetos intercambiables.</p>
          ) : (
            <div className="grid grid-cols-6 sm:grid-cols-8 gap-1.5 max-h-56 overflow-y-auto pr-1" data-testid="my-inventory-grid">
              {invItems.map((it) => {
                const left = it.quantity - (offeredMap[it.inv_id] || 0);
                return <ItemTile key={it.inv_id} it={it} badge={left} dim={left <= 0} testid={`inv-item-${it.inv_id}`} onHover={() => play?.("hover")} onClick={() => addItem(it)} />;
              })}
            </div>
          )}
        </motion.div>

        {/* ── THEIR SIDE ── */}
        <motion.div layout className="glass rounded-2xl border border-white/10 p-4"
          animate={{ boxShadow: them.confirmed ? "0 0 0 1.5px rgba(52,211,153,.6)" : them.locked ? "0 0 0 1.5px rgba(202,169,104,.5)" : "0 0 0 0px rgba(0,0,0,0)" }}
          transition={{ duration: 0.3 }}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg overflow-hidden bg-white/5">{them.avatar ? <img src={them.avatar} alt="" className="w-full h-full object-cover" /> : null}</div>
              <span className="font-display font-bold text-lg">{them.name}</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <AnimatePresence>
                {them.locked && <motion.span initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1 text-gold"><Lock size={12} /> Bloqueada</motion.span>}
                {them.confirmed && <motion.span initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1 text-emerald"><Check size={12} /> Confirmado</motion.span>}
              </AnimatePresence>
            </div>
          </div>

          <AnimatedSlots testid="their-offer-slots" items={theirItems} renderItem={(i) => (
            <ItemTile it={i} badge={i.qty} testid={`their-offered-${i.inv_id}`} />
          )} />

          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold"><Gem size={15} /> Amberium</span>
            <motion.span key={them.offer.amber || 0} initial={{ scale: 1.25, color: "#CAA968" }} animate={{ scale: 1, color: "#ffffff" }} transition={SPRING}
              className="px-2.5 py-1.5 rounded-lg glass border border-white/10 text-sm tabular-nums font-bold">{them.offer.amber || 0}</motion.span>
          </div>
          {theirItems.length === 0 && (them.offer.amber || 0) === 0 && (
            <p className="text-sm text-muted-foreground py-10 text-center">{them.name} aún no ha ofrecido nada.</p>
          )}
        </motion.div>
      </div>

      {/* ── controls ── */}
      <div className="mt-5 flex flex-col sm:flex-row items-center justify-center gap-3">
        <motion.button whileTap={{ scale: 0.94 }} onClick={() => { click(); onLock(!me.locked); }} data-testid="trade-lock-btn"
          className={`inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-bold border transition-colors w-full sm:w-auto ${me.locked ? "bg-gold/15 text-gold border-gold/40" : "bg-white/10 border-white/10 hover:bg-white/15"}`}>
          {me.locked ? <><Unlock size={17} /> Desbloquear</> : <><Lock size={17} /> Bloquear oferta</>}
        </motion.button>
        <motion.button whileTap={{ scale: 0.94 }} whileHover={bothLocked && !me.confirmed ? { scale: 1.03 } : undefined}
          onClick={() => { click(); onConfirm(); }} disabled={!bothLocked || me.confirmed} data-testid="trade-confirm-btn"
          animate={bothLocked && !me.confirmed ? { boxShadow: ["0 0 0 0 rgba(202,169,104,0)", "0 0 22px 2px rgba(202,169,104,.55)", "0 0 0 0 rgba(202,169,104,0)"] } : { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }}
          transition={bothLocked && !me.confirmed ? { duration: 1.6, repeat: Infinity } : { duration: 0.2 }}
          className="inline-flex items-center justify-center gap-2 rounded-xl px-8 py-3.5 font-black uppercase tracking-wide text-background disabled:opacity-40 w-full sm:w-auto"
          style={{ background: "linear-gradient(135deg,#E9D8A6,#CAA968)" }}>
          {me.confirmed ? <><Loader2 size={17} className="animate-spin" /> Esperando a {them.name}…</> : <><Check size={18} /> Confirmar intercambio</>}
        </motion.button>
      </div>
      {!bothLocked && (
        <p className="text-center text-xs text-muted-foreground mt-2">Ambos jugadores deben <b>bloquear</b> su oferta para poder confirmar. Editar la oferta reinicia los bloqueos.</p>
      )}
    </div>
  );
}
