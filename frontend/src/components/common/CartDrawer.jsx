import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ShoppingCart, Plus, Minus, Trash2, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CoinChip } from "@/components/common/CoinChip";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

export function CartDrawer() {
  const { items, setQty, remove, clear, totals, open, setOpen } = useCart();
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [busy, setBusy] = useState(false);

  const close = () => { play("close"); setOpen(false); };

  const afford = user && user.coins >= totals.normal && user.vip_coins >= totals.vip;

  const checkout = async () => {
    if (!user) { play("error"); toast.error("Inicia sesión con Steam para pagar."); return; }
    if (!items.length) return;
    setBusy(true);
    try {
      const payload = items.map((i) => ({ item_id: i.id, quantity: i.qty || 1 }));
      const { data } = await api.checkout(payload);
      play("purchase");
      toast.success(`¡Pedido completado! ${data.purchased.length} artículo(s)`, { description: "Añadido a tu inventario." });
      clear();
      await refresh();
      setOpen(false);
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "Falló el pago.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[100000]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="cart-drawer">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={close} />
          <motion.aside
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="absolute right-0 top-0 h-full w-full max-w-md glass-strong flex flex-col"
          >
            <div className="flex items-center justify-between p-5 border-b border-white/5">
              <h3 className="font-display font-bold text-xl inline-flex items-center gap-2"><ShoppingCart size={20} className="text-gold" /> Tu Carrito</h3>
              <button onClick={close} data-testid="cart-close" className="p-2 rounded-lg hover:bg-white/10 transition-colors"><X size={18} /></button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {items.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground py-20">
                  <ShoppingCart size={40} className="mb-4 opacity-40" />
                  <p>Tu carrito está vacío.</p>
                </div>
              ) : items.map((i) => (
                <motion.div key={i.id} layout initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}
                  className="flex gap-3 glass rounded-xl p-3" data-testid={`cart-item-${i.id}`}>
                  <img src={i.image} alt="" className="w-16 h-16 rounded-lg object-contain p-1" />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate">{i.name}</p>
                    <CoinChip type={i.currency} amount={i.price} size="sm" />
                    <div className="flex items-center gap-2 mt-2">
                      <button onClick={() => { setQty(i.id, (i.qty || 1) - 1); play("click"); }} data-testid={`cart-dec-${i.id}`} className="p-1 rounded glass hover:border-gold/40"><Minus size={13} /></button>
                      <span className="text-sm font-bold w-6 text-center tabular-nums">{i.qty || 1}</span>
                      <button onClick={() => { setQty(i.id, (i.qty || 1) + 1); play("click"); }} data-testid={`cart-inc-${i.id}`} className="p-1 rounded glass hover:border-gold/40"><Plus size={13} /></button>
                      <button onClick={() => { remove(i.id); play("close"); }} data-testid={`cart-remove-${i.id}`} className="ml-auto p-1.5 rounded text-crimson hover:bg-crimson/10"><Trash2 size={14} /></button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="p-5 border-t border-white/5 space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Total</span>
                <div className="flex gap-3">
                  {totals.normal > 0 && <CoinChip type="normal" amount={totals.normal} size="md" />}
                  {totals.vip > 0 && <CoinChip type="vip" amount={totals.vip} size="md" />}
                  {totals.normal === 0 && totals.vip === 0 && <span className="text-muted-foreground">—</span>}
                </div>
              </div>
              {user && items.length > 0 && !afford && (
                <p className="text-xs text-crimson text-center">Saldo insuficiente para este pedido.</p>
              )}
              <button
                onClick={checkout}
                disabled={busy || items.length === 0}
                data-testid="cart-checkout"
                className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all disabled:opacity-50"
              >
                {busy ? "Procesando…" : <><Check size={18} /> {user ? "Pagar" : "Inicia sesión para pagar"}</>}
              </button>
            </div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
