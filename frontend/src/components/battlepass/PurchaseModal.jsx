import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, Crown, Zap, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, externalRedirect } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { GOLD } from "@/components/battlepass/RewardCard";

const TIERS = [
  {
    key: "regular",
    title: "Pase Regular",
    price: "$5",
    accent: "#7CA842",
    features: [
      "Desbloquea la fila Regular: 1.000.000 PrimeMeat + 3.000 Amberium en total",
      "Dinos al 75% (no Prime) y Triceratops en el nivel 100",
      "12 mutaciones en total (3 al azar por dino)",
      "Diet Token 150% (dos se acumulan al 300%) · Growth Token 70% (Prime si completaste las misiones Prime)",
      "Skins del pase (no legendarias)",
    ],
  },
  {
    key: "premium_plus",
    title: "Pase Premium+",
    price: "$10",
    accent: GOLD,
    highlight: true,
    features: [
      "Desbloquea LAS DOS filas: 2.000.000 PrimeMeat + 6.000 Amberium en total",
      "Dinos PRIME al 75% y Tyrannosaurus con skin en el nivel 100",
      "28 mutaciones en total (4 al azar por dino Prime)",
      "Diet Token 300% · Growth Token 70% + Prime siempre",
      "Skins Legendarias exclusivas",
    ],
  },
];

const RANK = { free: 0, regular: 1, premium_plus: 2 };

export function PurchaseModal({ open, onClose, currentTier = "free" }) {
  const { play } = useSound();
  const [busy, setBusy] = useState(null);

  const purchase = async (tier) => {
    if (busy) return;
    play("click");
    setBusy(tier);
    try {
      const r = await api.bpCheckout(tier);
      const url = r.data?.checkout_url;
      if (!url) throw new Error("El servidor no devolvió una URL de pago");
      externalRedirect(url);
    } catch (e) {
      setBusy(null);
      play("error");
      toast.error(e?.response?.data?.detail || e?.response?.data?.error || e?.message || "No se pudo iniciar el pago");
    }
  };

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-4"
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
          data-testid="bp-purchase-modal"
        >
          <motion.div
            initial={{ scale: 0.92, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.92, y: 20, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="relative max-h-[92vh] w-full max-w-4xl overflow-y-auto overflow-x-hidden rounded-2xl border p-4 sm:p-6"
            style={{ borderColor: `${GOLD}44`, background: "#0b0b0e" }}
          >
            <button
              type="button"
              onClick={() => { play("close"); onClose(); }}
              aria-label="Cerrar"
              data-testid="bp-purchase-close"
              className="absolute right-3 top-3 z-10 rounded-full bg-white/5 p-2 text-foreground/70 backdrop-blur transition-all hover:bg-white/10 hover:text-foreground"
            >
              <X size={18} />
            </button>

            <div className="mb-5 text-center sm:mb-6">
              <div
                className="mx-auto flex h-12 w-12 items-center justify-center rounded-full sm:h-14 sm:w-14"
                style={{ background: `${GOLD}22` }}
              >
                <Crown size={28} style={{ color: GOLD }} />
              </div>
              <h2 className="mt-3 font-display text-xl font-extrabold tracking-tight sm:text-2xl">Desbloquear el pase</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Elige tu nivel de acceso. El pase dura hasta el final del mes.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {TIERS.map((t) => {
                const owned = RANK[currentTier] >= RANK[t.key];
                const upgrade = t.key === "premium_plus" && currentTier === "regular";
                const label = owned ? "Ya activo" : upgrade ? "Mejorar $5" : `Desbloquear ${t.price}`;
                return (
                  <div
                    key={t.key}
                    className="relative overflow-hidden rounded-xl border p-5"
                    style={{
                      borderColor: t.highlight ? `${t.accent}99` : "rgba(255,255,255,0.12)",
                      background: t.highlight
                        ? `linear-gradient(135deg, ${t.accent}1a, rgba(0,0,0,0.4))`
                        : "rgba(255,255,255,0.03)",
                      boxShadow: t.highlight ? `inset 0 0 40px ${t.accent}22` : "none",
                    }}
                    data-testid={`bp-tier-card-${t.key}`}
                  >
                    {t.highlight && (
                      <div
                        className="absolute right-3 top-3 rounded-full px-2 py-0.5 text-[10px] font-extrabold text-black"
                        style={{ background: t.accent }}
                      >
                        MÁS COMPLETO
                      </div>
                    )}
                    <div className="flex items-center gap-3">
                      {t.highlight ? <Crown size={22} style={{ color: t.accent }} /> : <Zap size={22} style={{ color: t.accent }} />}
                      <h3 className="font-display text-lg font-extrabold">{t.title}</h3>
                    </div>
                    <div className="mt-2 flex items-baseline gap-1.5">
                      <span className="font-display text-4xl font-extrabold" style={{ color: t.accent }}>{t.price}</span>
                      <span className="text-xs text-muted-foreground">/ mes</span>
                    </div>
                    <ul className="mt-4 space-y-2 text-sm">
                      {t.features.map((f, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Check size={14} className="mt-0.5 shrink-0" style={{ color: t.accent }} />
                          <span className="text-foreground/85">{f}</span>
                        </li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      disabled={owned || !!busy}
                      onClick={() => purchase(t.key)}
                      data-testid={`bp-buy-${t.key}`}
                      className={`mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg py-3 text-sm font-extrabold tracking-wide transition-all disabled:cursor-not-allowed ${
                        owned ? "bg-white/5 text-muted-foreground" : "hover:brightness-110"
                      }`}
                      style={owned ? undefined : { background: t.accent, color: "#0a0a0a" }}
                    >
                      {busy === t.key && <Loader2 size={15} className="animate-spin" />}
                      {label}
                    </button>
                  </div>
                );
              })}
            </div>

            <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground">
              El pago se procesa con Stripe. El progreso se reinicia el 1º de cada mes y las recompensas que no
              reclames se te otorgan automáticamente al cerrar el mes. Si tienes un Patreon activo, tu pase se
              desbloquea solo; el staff también puede regalar pases.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default PurchaseModal;
