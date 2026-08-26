import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Trophy, Sparkles, Ticket } from "lucide-react";
import { api } from "@/lib/api";
import { LevelBadge } from "@/components/creator/LevelBadge";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const CACHE_KEY = "cp_ref_code_pending";

export default function CreatorPublic() {
  const { code } = useParams();
  const [data, setData] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    api.cpPublic(code).then((r) => alive && setData(r.data))
      .catch(() => alive && setNotFound(true))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [code]);

  const useCode = async () => {
    if (!user) {
      localStorage.setItem(CACHE_KEY, (code || "").toUpperCase());
      toast.info("Iniciá sesión primero — tu código fue guardado.");
      navigate("/");
      return;
    }
    try {
      const r = await api.cpApplyCode(code);
      if (r.data.status === "PENDING") {
        toast.info(`✨ ¡Te refirió ${r.data.creator_name || code}! ${r.data.pending_reason || ""}`.trim());
      } else {
        toast.success(`✓ ¡Te refirió ${r.data.creator_name || code}!`);
      }
      navigate("/profile");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail === "REFERRAL_ALREADY_USED") {
        // 2026-08-18: one code PER CREATOR, not one code ever.
        toast.error("Ya apoyaste a este creator. Podés apoyar a otros con sus códigos.");
      } else if (detail === "SELF_REFERRAL") {
        toast.error("No podés usar tu propio código.");
      } else {
        toast.error("No se pudo aplicar el código.");
      }
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-4 py-24 text-center text-white/60">Cargando…</div>;
  if (notFound) return (
    <div className="mx-auto max-w-2xl px-4 py-24 text-center">
      <div className="text-6xl">🔍</div>
      <h1 className="mt-3 text-2xl font-black">Creator no encontrado</h1>
      <p className="mt-1 text-sm text-white/50">El código <span className="font-mono text-gold">{code}</span> no existe.</p>
      <Link to="/creator/dashboard" className="mt-4 inline-block text-gold text-xs font-black tracking-widest hover:underline">← Volver al Programa de Creators</Link>
    </div>
  );

  const c = data?.creator;
  const target = data?.skin_target || 100;
  const pct = Math.min(100, ((c?.total_referrals || 0) / target) * 100);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:py-14" data-testid="creator-public">
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        className="relative overflow-hidden rounded-2xl border border-gold/25 bg-gradient-to-br from-gold/[0.10] to-black/60 p-6 sm:p-8"
      >
        <div className="pointer-events-none absolute -top-24 -right-24 h-56 w-56 rounded-full opacity-30"
          style={{ background: "radial-gradient(circle, rgba(212,175,55,0.75), transparent 60%)" }} />

        <div className="relative flex items-center gap-4">
          <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-full border-2 border-gold/50 bg-black/50 overflow-hidden flex items-center justify-center text-3xl font-black">
            {c?.avatar
              ? <img src={c.avatar} alt="" className="h-full w-full object-cover" />
              : (c?.display_name || "?")[0]}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-black tracking-[0.3em] text-gold/70">CREATOR</div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight leading-tight truncate">{c?.display_name}</h1>
            <div className="mt-1.5 flex items-center gap-2 flex-wrap">
              <LevelBadge level={c?.level} />
              <span className="font-mono text-xs text-gold">{c?.code}</span>
              {c?.rank && (
                <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-black tracking-widest text-white/60">
                  <Trophy size={10} /> #{c.rank}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="relative mt-6 grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="text-[9px] font-black tracking-widest text-white/40">REFERIDOS TOTALES</div>
            <div className="text-2xl sm:text-3xl font-black tabular-nums text-gold">{(c?.total_referrals || 0).toLocaleString()}</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="text-[9px] font-black tracking-widest text-white/40">PROGRESO DE SKIN</div>
            <div className="text-2xl sm:text-3xl font-black tabular-nums">{c?.total_referrals || 0}<span className="text-white/40 text-lg"> / {target}</span></div>
          </div>
        </div>

        <div className="relative mt-3 h-2 rounded-full overflow-hidden bg-black/60">
          <motion.div className="absolute inset-y-0 left-0 rounded-full"
            initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ delay: 0.3, duration: 0.8 }}
            style={{ background: "linear-gradient(90deg, #F59E0B, #D4AF37)", boxShadow: "0 0 12px rgba(212,175,55,0.6)" }}
          />
        </div>

        <button
          onClick={useCode}
          data-testid="cp-public-use-code"
          className="relative mt-6 w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-gold py-3 text-xs font-black tracking-widest text-black transition hover:brightness-110"
        >
          <Ticket size={13} /> USAR CÓDIGO DE CREATOR
        </button>
        <p className="mt-2 text-center text-[10px] text-white/40">
          Usá este código y ambos reciben PrimeMeat. <Sparkles size={9} className="inline text-gold" />
        </p>
      </motion.div>
    </div>
  );
}
