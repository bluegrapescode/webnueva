import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Heart, CheckCircle2, Clock, Ticket, Trophy } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Renders in the Profile page (or wherever you want) a card telling the
 * referred player *who* they were referred by, plus the creator's live stats
 * and a link to the creator's public page — building community sense.
 *
 * 2026-08-18 (owner order): a player may support ANY number of creators, each
 * one once. The detailed card stays on the NEWEST creator — the API keeps that
 * one at the top level for exactly this reason — and the rest are named
 * underneath, so a player who supports five people is not silently shown one.
 */
export function MyReferralCard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    api.cpMyReferral().then((r) => alive && setData(r.data)).catch(() => alive && setData({ used: false }));
    return () => { alive = false; };
  }, []);

  if (!data || !data.used) return null;

  const c = data.creator || {};
  const rewarded = data.status === "REWARDED";
  const all = data.referrals || [];
  const others = all.slice(1);
  // The welcome bonus is once per PLAYER (server: player_reward_once), so on a
  // second code this is legitimately zero. Print a dash rather than "+0K",
  // which reads as a bug instead of as "already collected".
  const bonus = Number(data.reward_amount || data.player_reward_next || 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border border-white/[0.06] p-5"
      data-testid="my-referral-card"
      style={{ background: "linear-gradient(180deg, #1B1630 0%, #161225 100%)" }}
    >
      <div className="pointer-events-none absolute -top-16 -right-14 h-40 w-40 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(236,72,153,0.55), transparent 65%)" }} />

      <div className="relative flex items-center gap-2 mb-4">
        <Heart size={13} className="text-pink-400" fill="#EC4899" />
        <span className="text-[10px] font-black tracking-[0.35em] text-pink-400/80">
          {all.length > 1 ? `TUS CREATORS (${all.length})` : "TU CREATOR"}
        </span>
      </div>

      <div className="relative flex items-center gap-4">
        <div className="h-14 w-14 shrink-0 rounded-full border-2 border-purple-400/50 overflow-hidden bg-black/40 flex items-center justify-center text-lg font-black uppercase text-purple-300">
          {c.avatar
            ? <img src={c.avatar} alt="" className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
            : (c.display_name || "?")[0]}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-black text-lg truncate text-white">{c.display_name || c.code}</span>
            {c.exclusive_skin_unlocked && <Trophy size={13} className="text-gold" />}
          </div>
          <div className="text-[11px] text-white/45 font-mono">Código: <span className="text-gold">{c.code}</span></div>
          {c.rank && (
            <div className="text-[10px] text-white/50 mt-0.5">
              🏆 Rank #{c.rank} en el leaderboard global
            </div>
          )}
        </div>
      </div>

      <div className="relative mt-5 grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-black/30 border border-white/[0.05] p-2.5 text-center">
          <div className="text-[9px] font-black tracking-widest text-white/40">SU RANK</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">
            {c.rank ? `#${c.rank}` : "—"}
          </div>
        </div>
        <div className="rounded-lg bg-black/30 border border-white/[0.05] p-2.5 text-center">
          <div className="text-[9px] font-black tracking-widest text-white/40">SUS REFS</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">
            {(c.total_referrals || 0).toLocaleString()}
          </div>
        </div>
        <div className="rounded-lg bg-black/30 border border-white/[0.05] p-2.5 text-center">
          <div className="text-[9px] font-black tracking-widest text-white/40">TU BONO</div>
          <div className="mt-0.5 text-base font-black text-emerald-400 tabular-nums">
            {bonus > 0 ? `+${Math.round(bonus / 1000)}K` : "—"}
          </div>
        </div>
      </div>

      <div className="relative mt-4 flex items-center gap-2 text-[11px]">
        {rewarded ? (
          <span className="inline-flex items-center gap-1 text-emerald-400 font-black tracking-widest">
            <CheckCircle2 size={11} /> RECOMPENSA APLICADA
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-amber-400 font-black tracking-widest">
            <Clock size={11} /> PENDIENTE · {data.pending_reason || "Entrá al servidor y jugá para cobrar"}
          </span>
        )}
      </div>

      <div className="relative mt-4">
        <Link
          to={`/creator/${c.code}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] font-black tracking-widest text-white/80 hover:bg-white/[0.08] transition"
        >
          <Ticket size={11} /> VER PERFIL DEL CREATOR
        </Link>
      </div>

      {others.length > 0 && (
        <div className="relative mt-3" data-testid="my-referral-others">
          <div className="text-[9px] font-black tracking-widest text-white/40">
            TAMBIÉN APOYÁS
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {others.map((o) => (
              <Link key={o.id || o.code} to={`/creator/${o.creator?.code || o.code}`}
                className="inline-flex max-w-full items-center gap-1 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] font-black tracking-wider text-white/70 hover:bg-white/[0.08] transition">
                <span className="truncate">{o.creator?.display_name || o.creator?.code || o.code}</span>
                {o.status === "PENDING" && <Clock size={9} className="shrink-0 text-amber-400" />}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="relative mt-3 text-[10px] text-white/40 italic">
        Cada vez que uses tu cuenta, {c.display_name || "tu creator"} gana PrimeMeat. ¡Sos parte de la manada! 🦖
      </div>
    </motion.div>
  );
}
