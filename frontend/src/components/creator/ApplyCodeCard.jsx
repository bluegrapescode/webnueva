import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Ticket, CheckCircle2, AlertTriangle, Sparkles, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useSound } from "@/context/SoundContext";

// 2026-08-18 (owner order): a player may support ANY number of creators, each
// one exactly once. The backend keeps the SAME error id and only narrows what
// it means, so this copy is what changed, not the contract.
const ERROR_COPY = {
  REFERRAL_ALREADY_USED:
    "Ya apoyaste a este creator. Cada código se puede usar una sola vez, pero podés apoyar a otros creators.",
  CODE_NOT_FOUND: "Ese Código de Creator no existe.",
  SELF_REFERRAL:  "No podés usar tu propio Código de Creator.",
  CREATORS_CANT_BE_REFERRED: "Las cuentas de creator no pueden usar códigos de referido.",
};

// referrals.status enum, translated for display (server.py / creator_program.py).
const STATUS_ES = {
  PENDING:   "Pendiente",
  VALIDATED: "Validado",
  REWARDED:  "Recompensado",
  CANCELLED: "Cancelado",
};

const CACHE_KEY = "cp_ref_code_pending";

export function ApplyCodeCard({ onApplied }) {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState(null); // null | "checking" | "success" | "pending" | "error"
  const [message, setMessage] = useState("");
  const [mine, setMine] = useState(null); // null = not loaded, else the my-referral payload
  const { play } = useSound();

  const refresh = useCallback(async () => {
    try {
      const r = await api.cpMyReferral();
      setMine(r.data && r.data.used ? r.data : null);
    } catch (_) {}
  }, []);

  useEffect(() => {
    refresh();
    // Auto-apply if we captured a pending code from /ref/:code redirect
    const pending = localStorage.getItem(CACHE_KEY);
    if (pending) {
      setCode(pending);
      localStorage.removeItem(CACHE_KEY);
      setTimeout(() => handleApply(pending, true), 200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApply = async (raw, silent = false) => {
    const clean = (raw || code).trim().toUpperCase();
    if (!clean) return;
    setStatus("checking");
    setMessage("");
    try {
      const r = await api.cpApplyCode(clean);
      const data = r.data;
      if (data.status === "PENDING") {
        // Applied, but the referred account has not met min_playtime_minutes
        // yet — the backend already wrote the exact sentence to tell the
        // player what to do next; show it verbatim instead of a bare "success".
        setStatus("pending");
        const msg = `Código aplicado — te refirió ${data.creator_name}. ${data.pending_reason || ""}`.trim();
        setMessage(msg);
        if (!silent) play("notification");
        if (!silent) toast.info(msg);
      } else {
        setStatus("success");
        const msg = `✓ Código aplicado. Te refirió ${data.creator_name}.`;
        setMessage(msg);
        if (!silent) play("rewardReceived");
        if (!silent) toast.success(msg);
      }
      await refresh();
      onApplied && onApplied(data);
    } catch (e) {
      setStatus("error");
      const detail = e?.response?.data?.detail;
      const copy = ERROR_COPY[detail] || (detail || "No se pudo aplicar el código.");
      setMessage(copy);
      if (!silent) toast.error(copy);
      if (detail === "REFERRAL_ALREADY_USED") await refresh();
    }
  };

  // 2026-08-18: supporting one creator no longer ENDS this card. The codes
  // already used are listed above the box and the box stays open, because the
  // whole point of the order is that a player can support the next creator too.
  // The list falls back to the legacy single-referral fields so a page served
  // from cache against the new API still shows the newest code rather than
  // nothing.
  const supported = (mine && (mine.referrals || (mine.used ? [mine] : []))) || [];

  return (
    <div className="rounded-2xl border border-white/10 bg-black/30 p-4 sm:p-5" data-testid="cp-apply-code">
      {supported.length > 0 && (
        <div className="mb-4" data-testid="cp-already-referred">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-emerald-400" />
            <span className="text-[10px] font-black tracking-[0.3em] text-emerald-400/80">
              CREATORS QUE APOYÁS ({supported.length})
            </span>
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {supported.map((s) => {
              const isPending = s.status === "PENDING";
              return (
                <div key={s.id || s.code}
                  className={`rounded-xl border px-3 py-2 ${isPending ? "border-amber-500/25 bg-amber-500/[0.06]" : "border-emerald-500/25 bg-emerald-500/[0.06]"}`}
                  data-testid={`cp-supported-${s.code}`}>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm min-w-0">
                    {isPending
                      ? <Clock size={13} className="shrink-0 text-amber-400" />
                      : <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />}
                    <span className={`font-black break-words ${isPending ? "text-amber-400" : "text-emerald-400"}`}>
                      {s.creator?.display_name || s.creator?.code || s.code}
                    </span>
                    <span className="text-[11px] text-white/50">{STATUS_ES[s.status] || s.status}</span>
                  </div>
                  {isPending && s.pending_reason && (
                    <div className="mt-1 text-[11px] text-amber-400/90">{s.pending_reason}</div>
                  )}
                </div>
              );
            })}
          </div>
          {mine?.welcome_bonus_used && mine?.player_reward_once && (
            <div className="mt-2 text-[11px] text-white/45">
              Tu bono de bienvenida ya fue cobrado — los códigos que uses ahora suman al creator, no a vos.
            </div>
          )}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Ticket size={14} className="text-gold" />
        <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">
          {supported.length > 0 ? "APOYÁ A OTRO CREATOR" : "¿TE INVITÓ UN CREATOR?"}
        </span>
      </div>
      <div className="mt-3 flex flex-col sm:flex-row gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="INGRESÁ EL CÓDIGO DE CREATOR"
          data-testid="cp-code-input"
          maxLength={20}
          className="flex-1 rounded-md border border-white/15 bg-black/40 px-3 py-2 font-mono text-sm font-black tracking-widest text-white placeholder:text-white/30 focus:border-gold/50 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => handleApply()}
          disabled={!code || status === "checking"}
          data-testid="cp-apply-btn"
          className="inline-flex items-center justify-center gap-1.5 rounded-md bg-gold px-4 py-2 text-[11px] font-black tracking-widest text-black transition hover:brightness-110 disabled:opacity-40"
        >
          <Sparkles size={12} /> APLICAR CÓDIGO
        </button>
      </div>
      <AnimatePresence>
        {status === "success" && message && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-300">
            <CheckCircle2 size={12} /> {message}
          </motion.div>
        )}
        {status === "pending" && message && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
            <Clock size={12} /> {message}
          </motion.div>
        )}
        {status === "error" && message && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-crimson/30 bg-crimson/10 px-2 py-1 text-[11px] text-crimson">
            <AlertTriangle size={12} /> {message}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
