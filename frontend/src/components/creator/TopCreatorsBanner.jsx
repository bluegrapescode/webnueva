import React, { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Copy, Check, Crown, Ticket, Flame } from "lucide-react";
import { api, creatorWsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CACHE_KEY = "cp_ref_code_pending";
const CARD_BG = "#161225";
const CARD_BG_ALT = "#1B1630";
const BORDER_SOFT = "rgba(255,255,255,0.05)";
const ACCENT_PURPLE = "#8B5CF6";

function CopyPill({ value }) {
  const [copied, setCopied] = useState(false);
  const copy = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success("✓ Código copiado");
      setTimeout(() => setCopied(false), 1400);
    } catch (_) {}
  };
  return (
    <button onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.03] px-2 py-1 font-mono text-[11px] font-black tracking-widest text-white/80 hover:bg-white/[0.08] transition"
    >
      {value}
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} className="text-white/40" />}
    </button>
  );
}

function TopCard({ entry, rank, highlight, onUse }) {
  const color = rank === 1 ? "#D4AF37" : rank === 2 ? "#C0C6D0" : "#CD7F32";
  const label = rank === 1 ? "1ST" : rank === 2 ? "2ND" : "3RD";

  return (
    <motion.div
      layout
      layoutId={`creator-card-${entry.user_id}`}
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
      transition={{ layout: { type: "spring", stiffness: 260, damping: 28 }, opacity: { duration: 0.4 }, y: { duration: 0.45 } }}
      className="relative overflow-hidden rounded-2xl p-5"
      style={{
        background: `linear-gradient(180deg, ${CARD_BG_ALT} 0%, ${CARD_BG} 100%)`,
        border: highlight ? `1.5px solid ${ACCENT_PURPLE}` : `1px solid ${BORDER_SOFT}`,
        boxShadow: highlight ? `0 0 40px rgba(139,92,246,0.28)` : "none",
      }}
    >
      {highlight && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{ background: `linear-gradient(90deg, transparent, ${ACCENT_PURPLE}, transparent)` }} />
      )}
      <div className="pointer-events-none absolute -top-16 -right-12 h-40 w-40 rounded-full opacity-20"
        style={{ background: `radial-gradient(circle, ${color}, transparent 65%)` }} />

      <div className="relative flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 overflow-hidden font-black uppercase"
            style={{ borderColor: color, background: `linear-gradient(135deg, ${color}33, rgba(0,0,0,0.7))`, color }}>
            {entry.avatar
              ? <img src={entry.avatar} alt="" className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
              : (entry.display_name || "?")[0]}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-black text-base truncate text-white">{entry.display_name}</span>
              {rank === 1 && <Crown size={12} className="text-gold shrink-0" fill="#D4AF37" />}
            </div>
            <div className="text-[11px] text-white/40 font-mono">@{(entry.display_name || "creator").toLowerCase()}</div>
          </div>
        </div>
        <span
          className="shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[9px] font-black tracking-[0.3em]"
          style={{ borderColor: color + "55", background: color + "18", color }}>
          {label}
        </span>
      </div>

      {/* Stats: REFS / MONTH / RATE / EARNED (mirrors PNL/Followers/WinRate/Profit) */}
      <div className="relative mt-5 grid grid-cols-4 gap-3">
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">REFS</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Number(entry.total_referrals || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">MES</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Number(entry.monthly_referrals || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">TASA</div>
          <div className="mt-0.5 text-base font-black text-emerald-400 tabular-nums">
            {(entry.monthly_referrals && entry.total_referrals) ? ((entry.monthly_referrals / entry.total_referrals) * 100).toFixed(1) : "0.0"}%
          </div>
        </div>
        <div>
          <div className="text-[9px] font-black tracking-widest text-white/40">GANADO</div>
          <div className="mt-0.5 text-base font-black text-white tabular-nums">{Math.round((entry.total_prime_meat_earned || 0) / 1000)}K</div>
        </div>
      </div>

      {/* Code + CTA row */}
      <div className="relative mt-4 flex items-center justify-between gap-2">
        <CopyPill value={entry.code} />
        <button
          onClick={() => onUse(entry)}
          data-testid={`use-code-${entry.code}`}
          className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[10px] font-black tracking-widest transition hover:brightness-110"
          style={{ background: highlight ? ACCENT_PURPLE : "rgba(255,255,255,0.08)", color: highlight ? "#fff" : "rgba(255,255,255,0.9)" }}
        >
          <Ticket size={11} /> USAR CÓDIGO
        </button>
      </div>
    </motion.div>
  );
}

export function TopCreatorsBanner() {
  const [creators, setCreators] = useState(null);
  const { user } = useAuth();
  const navigate = useNavigate();
  const wsRef = useRef(null);
  const pingRef = useRef(null);
  const prevTopIdsRef = useRef([]);

  // Initial fetch
  useEffect(() => {
    let alive = true;
    api.cpLeaderboard("month")
      .then((r) => alive && setCreators((r.data.board || []).slice(0, 3)))
      .catch(() => alive && setCreators([]));
    return () => { alive = false; };
  }, []);

  // Live WebSocket updates
  useEffect(() => {
    let closed = false;
    let reconnectT = null;
    const connect = () => {
      try {
        const ws = new WebSocket(creatorWsUrl());
        wsRef.current = ws;
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "creator_leaderboard") {
              const monthly = (msg.monthly || []).slice(0, 3);
              // Detect reorder / new champion — small subtle toast for landing viewers
              const newIds = monthly.map((c) => c.user_id).join("|");
              const oldIds = prevTopIdsRef.current.join("|");
              if (oldIds && oldIds !== newIds && monthly[0]) {
                // Only toast if the champion actually changed
                const oldChamp = prevTopIdsRef.current[0];
                const newChamp = monthly[0].user_id;
                if (oldChamp && oldChamp !== newChamp) {
                  toast(`👑 ${monthly[0].display_name} está ahora en #1`, { duration: 3500 });
                }
              }
              prevTopIdsRef.current = monthly.map((c) => c.user_id);
              setCreators(monthly);
            }
          } catch (_) {}
        };
        ws.onclose = () => { if (!closed) reconnectT = setTimeout(connect, 5000); };
        ws.onerror = () => {};
      } catch (_) { reconnectT = setTimeout(connect, 5000); }
    };
    connect();
    pingRef.current = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);
    return () => {
      closed = true;
      if (reconnectT) clearTimeout(reconnectT);
      if (pingRef.current) clearInterval(pingRef.current);
      const ws = wsRef.current;
      if (ws) { try { ws.close(); } catch (_) {} }
    };
  }, []);

  const handleUse = useCallback(async (entry) => {
    if (!user) {
      localStorage.setItem(CACHE_KEY, (entry.code || "").toUpperCase());
      toast.info(`✨ Código de creator ${entry.code} guardado. Iniciá sesión para reclamar tu bono.`);
      return;
    }
    try {
      const r = await api.cpApplyCode(entry.code);
      if (r.data.status === "PENDING") {
        toast.info(`✨ ¡Te refirió ${r.data.creator_name || entry.code}! ${r.data.pending_reason || ""}`.trim());
      } else {
        toast.success(`✓ ¡Te refirió ${r.data.creator_name || entry.code}!`);
      }
      navigate("/creator/dashboard");
    } catch (err) {
      const d = err?.response?.data?.detail;
      // 2026-08-18: one code PER CREATOR, not one code ever.
      if (d === "REFERRAL_ALREADY_USED")      toast.error("Ya apoyaste a este creator.");
      else if (d === "SELF_REFERRAL")         toast.error("No podés usar tu propio código.");
      else                                    toast.error("No se pudo aplicar el código.");
    }
  }, [user, navigate]);

  if (!creators || creators.length === 0) return null;

  return (
    <section className="relative max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-20" data-testid="top-creators-banner">
      {/* Ambient cotton-candy blob backdrop */}
      <div className="pointer-events-none absolute inset-x-0 -top-32 h-96 opacity-30 blur-[80px]"
        style={{ background: "radial-gradient(circle at 30% 50%, #ec4899, transparent 45%), radial-gradient(circle at 70% 40%, #8b5cf6, transparent 50%), radial-gradient(circle at 50% 60%, #06b6d4, transparent 45%)" }} />

      <div className="relative text-center max-w-2xl mx-auto mb-10">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 mb-4">
          <Flame size={11} className="text-purple-400" />
          <span className="text-[10px] font-black tracking-[0.35em] text-white/70">TOP CREATORS · ESTE MES</span>
        </div>
        <h2 className="font-display font-black text-4xl sm:text-5xl md:text-6xl tracking-[-0.02em] leading-[0.95]">
          Leaderboard de Creators
        </h2>
        <p className="mt-4 text-sm sm:text-base text-white/50">
          Usá el código de tu creator favorito y ambos reciben <b className="text-white">PrimeMeat</b>.
        </p>
      </div>

      {/* Top-3 cards, equal height, center highlighted purple.
          AnimatePresence + layout enables smooth reordering when a live update
          bumps the champion or swaps ranks. */}
      <div className="relative grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5">
        <AnimatePresence mode="popLayout">
          {creators[1] && <TopCard key={creators[1].user_id} entry={creators[1]} rank={2} highlight={false} onUse={handleUse} />}
          {creators[0] && <TopCard key={creators[0].user_id} entry={creators[0]} rank={1} highlight={true}  onUse={handleUse} />}
          {creators[2] && <TopCard key={creators[2].user_id} entry={creators[2]} rank={3} highlight={false} onUse={handleUse} />}
        </AnimatePresence>
      </div>

      <div className="relative mt-8 flex justify-center">
        <Link to="/creator/dashboard"
          className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-5 py-2 text-[10px] font-black tracking-widest text-white/70 hover:bg-white/[0.08] transition">
          VER LEADERBOARD COMPLETO →
        </Link>
      </div>
    </section>
  );
}
