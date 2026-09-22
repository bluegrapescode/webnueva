import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Check, Loader2, ShoppingCart, Sparkles, X, Zap, Gem, Tag, Clock, Layers, ShieldCheck } from "lucide-react";
import { rarityOf } from "./shopRarity";
import { Countdown } from "./Countdown";
import { api, externalRedirect } from "@/lib/api";
import { toast } from "sonner";

const RARITY_FLAVOR = {
  common: "Cosmético estándar del servidor.",
  uncommon: "Acabado poco común con detalles mejorados.",
  rare: "Diseño raro con tonalidades exclusivas.",
  epic: "Skin épica de edición especial, muy solicitada.",
  legendary: "Pieza legendaria con acabado premium y brillo único.",
  mythic: "Rareza mítica: de las más exclusivas del catálogo.",
};

export function SkinDetailModal({ skin, open, onClose, play, onEquipped }) {
  const [busy, setBusy] = useState(false);
  const [equipped, setEquipped] = useState(false);
  useEffect(() => { setEquipped(!!skin?.equipped); }, [skin]);
  if (!skin) return null;
  const r = rarityOf(skin.rarity);
  const holo = skin.rarity === "legendary" || skin.rarity === "mythic";

  const buy = async () => {
    setBusy(true); play?.("purchase");
    try {
      const { data } = await api.shopCheckout(skin.id);
      if (data?.checkout_url) externalRedirect(data.checkout_url);
      else { toast.error("No se pudo iniciar el pago"); setBusy(false); }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo iniciar el pago");
      setBusy(false);
    }
  };

  const equip = async () => {
    setBusy(true); play?.("click");
    try {
      await api.shopEquip(skin.id);
      play?.("success");
      toast.success(`${skin.name} equipada`);
      setEquipped(true);
      onEquipped?.(skin.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo equipar");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent
        className="glass-strong border-0 max-w-4xl p-0 overflow-hidden gap-0 clip-notch"
        data-testid="skin-detail-modal"
        style={{ boxShadow: `0 0 0 1.5px ${r.color}, 0 0 0 4px rgba(245,158,11,0.25), 0 0 70px ${r.color}55, 0 40px 120px -30px rgba(245,158,11,0.6)` }}
      >
        <DialogTitle className="sr-only">{skin.name}</DialogTitle>
        <DialogDescription className="sr-only">{skin.description || `Skin ${r.label} para ${skin.dino_species || "dino"}`}</DialogDescription>
        <button onClick={onClose} data-testid="skin-modal-close"
          className="absolute top-3 right-3 z-20 rounded-full bg-black/60 hover:bg-black/90 p-2 text-white/70 hover:text-white transition-colors">
          <X size={16} />
        </button>
        <div className="grid md:grid-cols-2">
          {/* render */}
          <div className="relative min-h-[300px] md:min-h-[460px] overflow-hidden">
            <div className="absolute inset-0" style={{ background: `radial-gradient(65% 60% at 50% 45%, ${r.color}55, #07080a 88%)` }} />
            <motion.img src={skin.image_url} alt={skin.name}
              className="absolute inset-0 w-full h-full object-contain p-3 drop-shadow-2xl"
              initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1, y: [0, -10, 0] }}
              transition={{ opacity: { duration: 0.4 }, scale: { duration: 0.4 }, y: { duration: 5, repeat: Infinity, ease: "easeInOut" } }} />
            {holo && <div className="skin-card__holo" aria-hidden />}
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
            <div className="absolute left-0 top-0 h-full w-1" style={{ background: `linear-gradient(to bottom, ${r.color}, transparent)` }} />
          </div>
          {/* info */}
          <div className="p-7 flex flex-col max-h-[85vh] overflow-y-auto">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 label-overline text-[10px] px-2.5 py-1 border self-start clip-notch-sm"
                style={{ color: r.color, borderColor: `${r.color}77`, background: `${r.color}22` }}>
                <Zap size={10} /> {r.label}
              </span>
              {skin.owned && <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded bg-emerald-500/20 text-emerald-200 border border-emerald-400/40"><Check size={11} /> En tu colección</span>}
            </div>
            <h2 className="font-display font-black uppercase tracking-tight text-3xl sm:text-4xl mt-3 leading-[0.9]">{skin.name}</h2>
            {skin.dino_species && <p className="text-sm text-white/50 mt-1.5">Para {skin.dino_species}</p>}

            {/* rarity flavour */}
            <p className="text-sm text-white/70 mt-4 leading-relaxed">{skin.description || RARITY_FLAVOR[skin.rarity] || RARITY_FLAVOR.common}</p>

            {/* attribute grid */}
            <div className="grid grid-cols-2 gap-2.5 mt-5">
              {[
                { icon: Gem, label: "Rareza", value: r.label, accent: true },
                { icon: Layers, label: "Especie", value: skin.dino_species || "Universal" },
                { icon: Tag, label: "Tipo", value: skin.skin_type || "Estándar" },
                { icon: Clock, label: "Disponibilidad", value: skin.end_at ? "Limitada" : "Permanente" },
              ].map((a) => (
                <div key={a.label} className="rounded-xl px-3 py-2.5 border" style={{ background: "rgba(255,255,255,.03)", borderColor: a.accent ? `${r.color}44` : "rgba(255,255,255,.08)" }}>
                  <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-white/45"><a.icon size={11} style={a.accent ? { color: r.color } : {}} /> {a.label}</span>
                  <span className="block text-sm font-bold mt-0.5 truncate" style={a.accent ? { color: r.color } : {}}>{a.value}</span>
                </div>
              ))}
            </div>

            {/* perks */}
            <div className="mt-4 space-y-2">
              <span className="flex items-center gap-2 text-xs text-white/70"><ShieldCheck size={14} style={{ color: r.color }} /> Se aplica a tu {skin.dino_species || "dinosaurio"} en el servidor</span>
              <span className="flex items-center gap-2 text-xs text-white/70"><Sparkles size={14} style={{ color: r.color }} /> Skin única coleccionable, ligada a tu cuenta</span>
              <span className="flex items-center gap-2 text-xs text-white/70 font-code">
                <Clock size={14} style={{ color: r.color }} />
                {skin.end_at ? <>Disponible por <Countdown endAt={skin.end_at} className="text-white/90" /></> : "Disponible por tiempo indefinido"}
              </span>
            </div>

            <div className="mt-auto pt-7">
              <div className="flex items-end justify-between mb-3">
                <span className="text-xs text-white/45 uppercase tracking-widest">Precio</span>
                <span className="font-code font-black text-3xl" style={{ color: r.color }}>${skin.price_usd.toFixed(2)}</span>
              </div>
              {skin.owned ? (
                equipped ? (
                  <button disabled data-testid="skin-equipped-btn"
                    className="w-full inline-flex items-center justify-center gap-2 clip-notch-sm py-4 font-black uppercase tracking-wide bg-emerald-500/20 text-emerald-200 border-2 border-emerald-400/50">
                    <Check size={18} /> Equipada
                  </button>
                ) : (
                  <button onClick={equip} disabled={busy} data-testid={`equip-btn-${skin.id}`}
                    className="w-full inline-flex items-center justify-center gap-2 clip-notch-sm py-4 font-black uppercase tracking-wide text-black transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-60"
                    style={{ background: "linear-gradient(135deg,#B8DA7E,#7CA842)" }}>
                    {busy ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />} Equipar al dino
                  </button>
                )
              ) : (
                <button onClick={buy} disabled={busy} data-testid={`buy-btn-${skin.id}`}
                  className="w-full inline-flex items-center justify-center gap-2 clip-notch-sm py-4 font-black uppercase tracking-wide text-black transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-60"
                  style={{ background: "linear-gradient(135deg,#FCD34D,#F59E0B)", boxShadow: "0 14px 38px -14px rgba(245,158,11,0.9)" }}>
                  {busy ? <Loader2 size={18} className="animate-spin" /> : <ShoppingCart size={18} />}
                  {busy ? "Redirigiendo…" : "Comprar con Stripe"}
                </button>
              )}
              <p className="text-center text-[10px] text-white/35 mt-2.5">Pago seguro por Stripe · Skin única coleccionable</p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
