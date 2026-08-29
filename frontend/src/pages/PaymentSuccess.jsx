import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2, CheckCircle2, XCircle, Store as StoreIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { PurchaseCelebration } from "@/components/shop/PurchaseCelebration";

// Stripe redirects here after checkout. Poll the (unauthenticated) status
// endpoint until the skin is granted, then celebrate.
export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { play } = useSound();
  const { refresh } = useAuth();
  const sessionId = params.get("session_id");
  const [state, setState] = useState("checking"); // checking | success | failed
  const [skin, setSkin] = useState(null);
  const [celebrate, setCelebrate] = useState(null);
  const tries = useRef(0);

  useEffect(() => {
    if (!sessionId) { setState("failed"); return; }
    let stop = false;
    const poll = async () => {
      tries.current += 1;
      try {
        const { data } = await api.shopPaymentStatus(sessionId);
        if (data.payment_status === "paid" && data.granted) {
          if (stop) return;
          setSkin({ id: data.skin_id, name: data.skin_name });
          setState("success");
          refresh?.();
          // fetch full skin visuals for the celebration
          try {
            const mine = await api.shopMine();
            const full = (mine.data.skins || []).find((s) => s.skin_id === data.skin_id);
            if (full) { setSkin(full); setCelebrate({ id: full.skin_id, name: full.name, image_url: full.image_url, rarity: full.rarity }); }
          } catch {}
          return;
        }
        if (["failed", "expired"].includes(data.payment_status)) { setState("failed"); return; }
      } catch {}
      if (!stop && tries.current < 30) setTimeout(poll, 2000);
      else if (!stop) setState("failed");
    };
    poll();
    return () => { stop = true; };
  }, [sessionId, refresh]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6" data-testid="payment-success-page">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-2xl border border-white/10 p-10 max-w-md w-full text-center">
        {state === "checking" && (
          <>
            <Loader2 size={44} className="mx-auto animate-spin text-[#7CA842]" />
            <h1 className="font-display font-extrabold text-2xl mt-5">Confirmando tu pago…</h1>
            <p className="text-white/50 text-sm mt-2">Estamos verificando la transacción con Stripe. No cierres esta ventana.</p>
          </>
        )}
        {state === "success" && (
          <>
            <CheckCircle2 size={48} className="mx-auto text-emerald-400" />
            <h1 className="font-display font-extrabold text-3xl mt-4">¡Compra completada!</h1>
            <p className="text-white/60 mt-2">{skin?.name ? <><b>{skin.name}</b> ya está en tu inventario.</> : "Tu skin ya está en tu inventario."}</p>
            <div className="mt-6 flex gap-3">
              <button onClick={() => navigate("/tienda-skins")} data-testid="back-to-shop-btn"
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl py-3 font-bold text-black" style={{ background: "linear-gradient(135deg,#B8DA7E,#7CA842)" }}>
                <StoreIcon size={16} /> Volver a la tienda
              </button>
            </div>
          </>
        )}
        {state === "failed" && (
          <>
            <XCircle size={48} className="mx-auto text-red-400" />
            <h1 className="font-display font-extrabold text-2xl mt-4">No pudimos confirmar el pago</h1>
            <p className="text-white/50 text-sm mt-2">Si el cobro se realizó, la skin aparecerá en tu inventario en unos minutos. Si no, no se te ha cobrado.</p>
            <button onClick={() => navigate("/tienda-skins")} className="mt-6 w-full rounded-xl py-3 font-bold bg-white/10 hover:bg-white/15 border border-white/10">
              Volver a la tienda
            </button>
          </>
        )}
      </motion.div>
      <PurchaseCelebration skin={celebrate} onDone={() => setCelebrate(null)} play={play} />
    </div>
  );
}
