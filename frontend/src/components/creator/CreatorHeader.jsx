import React, { useState } from "react";
import { motion } from "framer-motion";
import { Copy, Check, Link as LinkIcon, Radio } from "lucide-react";
import { LevelBadge } from "./LevelBadge";
import { useSound } from "@/context/SoundContext";
import { toast } from "sonner";

/**
 * Header polished with navy-purple palette to match new leaderboard style.
 */
export function CreatorHeader({ creator, code }) {
  const { play } = useSound();
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);

  const copy = async (text, setter) => {
    try {
      await navigator.clipboard.writeText(text);
      setter(true);
      play("copyCode");
      toast.success("✓ Código copiado");
      setTimeout(() => setter(false), 1500);
    } catch (_) { toast.error("No se pudo copiar."); }
  };
  const link = `${window.location.origin}/ref/${code}`;

  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.06]" data-testid="creator-header"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400/40 to-transparent" />
      <div className="pointer-events-none absolute -top-40 -right-24 h-96 w-96 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(139,92,246,0.85), transparent 60%)" }} />
      <div className="pointer-events-none absolute -bottom-16 -left-16 h-56 w-56 rounded-full opacity-15"
        style={{ background: "radial-gradient(circle, rgba(236,72,153,0.8), transparent 65%)" }} />

      <div className="relative p-6 sm:p-10 grid gap-8 md:grid-cols-[1fr_auto] items-start">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] font-black tracking-[0.35em] text-emerald-400/80">
            <Radio size={11} className="animate-pulse" />
            PROGRAMA DE CREATORS
            <span className="text-white/20">·</span>
            <span className="text-white/60">ACTIVO</span>
          </div>
          <h1 className="mt-3 text-4xl sm:text-5xl md:text-6xl font-black tracking-[-0.03em] leading-[0.95] text-white">
            Bienvenido de vuelta,
            <br />
            <span style={{ background: "linear-gradient(90deg, #A78BFA, #EC4899)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
              {creator?.display_name || "Creator"}
            </span>
          </h1>
          <div className="mt-5 flex items-center gap-3 flex-wrap">
            <LevelBadge level={creator?.level} size="md" />
            <span className="text-sm text-white/50 tabular-nums">
              {(creator?.total_referrals ?? 0).toLocaleString()} referidos validados · histórico
            </span>
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}
          className="relative w-full md:w-[340px] rounded-2xl p-5 overflow-hidden"
          style={{ background: "rgba(0,0,0,0.35)", border: "1.5px solid #8B5CF6", boxShadow: "0 0 40px rgba(139,92,246,0.25)" }}
        >
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400 to-transparent" />
          <div className="relative">
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-black tracking-[0.35em] text-purple-400">TU CÓDIGO</span>
              <span className="text-[9px] font-mono text-white/30">/ref/{code}</span>
            </div>
            <div className="mt-2 font-mono text-3xl sm:text-4xl font-black tracking-[0.14em] leading-none text-white"
              data-testid="creator-code-value">
              {code || "—"}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button type="button" onClick={() => copy(code || "", setCopiedCode)} disabled={!code}
                data-testid="creator-copy-code"
                className="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-black tracking-widest text-white transition hover:brightness-110 disabled:opacity-40"
                style={{ background: "#8B5CF6" }}
              >
                {copiedCode ? <><Check size={12} /> COPIADO</> : <><Copy size={12} /> COPIAR CÓDIGO</>}
              </button>
              <button type="button" onClick={() => copy(link, setCopiedLink)} disabled={!code}
                data-testid="creator-copy-link"
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[10px] font-black tracking-widest text-white/80 transition hover:bg-white/10 disabled:opacity-40"
              >
                {copiedLink ? <><Check size={12} /> COPIADO</> : <><LinkIcon size={12} /> COPIAR LINK</>}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
