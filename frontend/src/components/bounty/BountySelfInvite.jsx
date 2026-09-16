import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Droplet, X, Clock } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { api } from "@/lib/api";
import { useBounty } from "@/context/BountyContext";
import { fmtNum } from "@/lib/bountyMeta";

// Invitación aleatoria global: "¿pones precio a tu cabeza?". Aparece cuando el
// servidor envía bounty:self_invite al usuario logueado.
export function BountySelfInvite() {
  const { lastEvent } = useBounty();
  const [invite, setInvite] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (lastEvent && lastEvent.event === "bounty:self_invite") {
      setInvite(lastEvent.data);
    }
    if (lastEvent && lastEvent.event === "bounty:self_started") {
      setInvite(null);
    }
  }, [lastEvent]);

  useEffect(() => {
    if (!invite) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [invite]);

  if (!invite) return null;
  const left = Math.max(0, Math.ceil(((invite.expiresAt || 0) - now) / 1000));
  if (left <= 0) { setTimeout(() => setInvite(null), 0); }

  const accept = async () => {
    setBusy(true);
    try {
      await api.bountySelfAcceptInvite();
      toast.success("¡Precio puesto sobre tu cabeza! Sobrevive para ganar PrimeMeat.");
      setInvite(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo activar");
    } finally { setBusy(false); }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed bottom-5 right-5 z-[85] w-[320px]"
        initial={{ opacity: 0, x: 40, scale: 0.9 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}
        transition={{ type: "spring", stiffness: 260, damping: 22 }}
        data-testid="bounty-self-invite"
      >
        <div className="relative rounded-2xl border overflow-hidden" style={{ background: "linear-gradient(150deg, #1a0a06, #0b0b0d 70%)", borderColor: "rgba(240,180,41,0.5)", boxShadow: "0 0 44px -14px rgba(240,180,41,0.6)" }}>
          <div className="absolute inset-0 pointer-events-none bounty-scan opacity-20" />
          <button data-testid="bounty-self-invite-close" onClick={() => setInvite(null)} className="absolute top-2 right-2 z-10 p-1 rounded text-white/40 hover:text-white/80"><X className="w-4 h-4" /></button>
          <div className="relative p-4">
            <div className="flex items-center gap-2 mb-2">
              <Droplet className="w-4 h-4 text-[#F0B429]" />
              <span className="text-[10px] font-bold uppercase tracking-[0.22em] text-[#F0B429]">Oportunidad de sangre</span>
            </div>
            <p className="text-sm font-bold text-white leading-snug">¿Pones precio a tu cabeza?</p>
            <p className="text-xs text-white/55 mt-1">
              Gana 🥩 <span className="text-white font-semibold">{fmtNum(invite.primePerMin)}</span>/min mientras sobrevivas ({invite.durationMin} min máx). Quien te elimine se lleva <span className="inline-flex items-center gap-0.5 text-[#F0B429] font-semibold"><img src={MEDIA.coinVip} alt="" className="w-3 h-3" />{fmtNum(invite.killerAmber)}</span>.
            </p>
            <div className="flex items-center gap-1 mt-2 text-white/40 text-[11px]"><Clock className="w-3 h-3" /> Expira en {left}s</div>
            <div className="flex gap-2 mt-3">
              <button data-testid="bounty-self-invite-accept" disabled={busy} onClick={accept}
                className="flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-50"
                style={{ background: "linear-gradient(180deg, #F0B429, #b9860f)", color: "#1a1206" }}>
                {busy ? "Activando…" : "Acepto"}
              </button>
              <button data-testid="bounty-self-invite-decline" onClick={() => setInvite(null)}
                className="px-3 py-2 rounded-lg text-xs font-semibold text-white/60 border border-white/15 hover:bg-white/5">
                Ahora no
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

export default BountySelfInvite;
