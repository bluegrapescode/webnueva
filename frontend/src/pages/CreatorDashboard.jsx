import React, { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Trophy } from "lucide-react";
import { api, creatorWsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { CreatorHeader } from "@/components/creator/CreatorHeader";
import { StatsGrid } from "@/components/creator/StatsGrid";
import { SkinProgress } from "@/components/creator/SkinProgress";
import { RecentActivity } from "@/components/creator/RecentActivity";
import { MyReferrals } from "@/components/creator/MyReferrals";
import { CreatorLeaderboard } from "@/components/creator/CreatorLeaderboard";
import { MilestoneTimeline } from "@/components/creator/MilestoneTimeline";
import { ReferralsChart } from "@/components/creator/ReferralsChart";
import { ConversionCard } from "@/components/creator/ConversionCard";
import { HallOfFame } from "@/components/creator/HallOfFame";
import { toast } from "sonner";

export default function CreatorDashboard() {
  const { user } = useAuth();
  const { play } = useSound();
  const [dashboard, setDashboard] = useState(null);
  const [boards, setBoards]       = useState({ all: [], month: [] });
  const [prizeSkins, setPrizeSkins]     = useState(null);
  const [monthlyPrizes, setMonthlyPrizes] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef       = useRef(null);
  const pingRef     = useRef(null);
  const prevTotalRef = useRef(null);
  const prevRankRef  = useRef(null);

  const load = useCallback(async () => {
    // allSettled, not all: one failed leaderboard call must not throw away a
    // dashboard that DID answer — the old all-or-nothing left dashboard null,
    // which rendered as "Todavía no sos Creator" for a real creator.
    const [d, all, month] = await Promise.allSettled([
      api.cpDashboard(),
      api.cpLeaderboard("all"),
      api.cpLeaderboard("month"),
    ]);
    if (d.status === "fulfilled") setDashboard(d.value.data);
    const allD   = all.status === "fulfilled" ? all.value.data : null;
    const monthD = month.status === "fulfilled" ? month.value.data : null;
    if (allD || monthD) {
      setBoards({ all: allD?.board || [], month: monthD?.board || [] });
      // Both scopes carry the same global prize config — either response works.
      setPrizeSkins(allD?.prize_skins || monthD?.prize_skins || null);
      setMonthlyPrizes(allD?.monthly_prizes || monthD?.monthly_prizes || null);
    }
    setLoading(false);
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

  // WebSocket
  useEffect(() => {
    if (!user) return undefined;
    let closed = false;
    let reconnectT = null;
    const detectDelta = (data) => {
      const total = data?.creator?.total_referrals;
      const rank  = data?.creator?.rank;
      if (prevTotalRef.current != null && total > prevTotalRef.current) {
        play("newReferral");
        toast.success(`🎉 ¡Nuevo referido! (+${total - prevTotalRef.current})`);
      }
      if (prevRankRef.current != null && rank && rank < prevRankRef.current) {
        play("rankUp");
        toast.success(`🏆 ¡Subiste de rank! #${prevRankRef.current} → #${rank}`);
      }
      prevTotalRef.current = total;
      prevRankRef.current  = rank;
    };
    const connect = () => {
      try {
        const ws = new WebSocket(creatorWsUrl());
        wsRef.current = ws;
        ws.onopen  = () => !closed && setWsConnected(true);
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "creator_leaderboard") {
              setBoards({ all: msg.all_time || [], month: msg.monthly || [] });
              if (msg.prize_skins) setPrizeSkins(msg.prize_skins);
              if (msg.monthly_prizes) setMonthlyPrizes(msg.monthly_prizes);
            } else if (msg.type === "creator_dashboard") {
              // The socket only ever pushes this to an actual creator, but the
              // page gates on is_creator — inject it so a push can never stomp
              // the panel back to the "not registered" screen (old backends
              // sent the payload without the flag).
              setDashboard({ is_creator: true, ...msg.data });
              detectDelta(msg.data);
              setRefreshKey((k) => k + 1);
            } else if (msg.type === "creator_notification") {
              const n = msg.notification;
              if (n?.type === "SKIN_UNLOCKED") { play("skinUnlocked"); toast.success(`👑 ${n.title}`); }
              else if (n?.type === "REWARD_RECEIVED") { play("rewardReceived"); toast.success(`🥩 ${n.title}: ${n.message}`); }
              else if (n?.type === "MILESTONE") { play("milestone"); }
            }
          } catch (_) {}
        };
        ws.onclose = () => { setWsConnected(false); if (!closed) reconnectT = setTimeout(connect, 3000); };
        ws.onerror = () => {};
      } catch (_) { reconnectT = setTimeout(connect, 3000); }
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
  }, [user?.id, play]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user) return <SignInPrompt title="Iniciá sesión" sub="Necesitás una cuenta para ver el Panel de Creator." />;
  if (loading) return (
    <div className="mx-auto max-w-7xl px-4 py-24 text-center text-white/60">
      <motion.div animate={{ rotate: [0, 360] }} transition={{ duration: 3, repeat: Infinity, ease: "linear" }} className="mx-auto mb-3 inline-block">
        <Trophy className="text-gold" size={32} />
      </motion.div>
      <p>Cargando Programa de Creators…</p>
    </div>
  );

  // After loading, a null dashboard means the dashboard CALL failed (a real
  // answer — creator or not — always sets an object). Never claim "you're not
  // a creator" off a failed call; offer a retry instead.
  if (!dashboard) {
    return (
      <div className="mx-auto max-w-7xl px-3 sm:px-4 py-6 sm:py-10">
        <div className="rounded-2xl border border-white/10 bg-black/30 p-6 mb-6" data-testid="cp-load-failed">
          <div className="flex items-center gap-2">
            <Trophy size={14} className="text-gold" />
            <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">PROGRAMA DE CREATORS</span>
          </div>
          <h1 className="mt-1 text-3xl sm:text-4xl font-black tracking-tight">No se pudo cargar tu panel</h1>
          <p className="mt-2 text-sm text-white/60 max-w-xl">
            Esto no cambia tu registro como Creator — es solo un problema de conexión. Reintentá en unos segundos.
          </p>
          <button
            onClick={() => { setLoading(true); load(); }}
            className="mt-4 rounded-xl border border-gold/40 bg-gold/10 px-5 py-2 text-sm font-black tracking-wide text-gold hover:bg-gold/20 transition-colors"
          >
            Reintentar
          </button>
        </div>
        <CreatorLeaderboard boards={boards} currentUserId={user.id} prizeSkins={prizeSkins} monthlyPrizes={monthlyPrizes} />
      </div>
    );
  }

  const isCreator = dashboard.is_creator;
  const creator   = dashboard.creator;
  const next      = dashboard.next_position;

  // Non-creator view: only the leaderboard + hint
  if (!isCreator) {
    return (
      <div className="mx-auto max-w-7xl px-3 sm:px-4 py-6 sm:py-10">
        <div className="rounded-2xl border border-white/10 bg-black/30 p-6 mb-6" data-testid="cp-not-creator">
          <div className="flex items-center gap-2">
            <Trophy size={14} className="text-gold" />
            <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">PROGRAMA DE CREATORS</span>
          </div>
          <h1 className="mt-1 text-3xl sm:text-4xl font-black tracking-tight">Todavía no sos Creator</h1>
          <p className="mt-2 text-sm text-white/60 max-w-xl">
            Contactá con un admin para postularte y conseguir tu propio Código de Creator. Mientras tanto, revisá el leaderboard.
          </p>
        </div>
        <CreatorLeaderboard boards={boards} currentUserId={user.id} prizeSkins={prizeSkins} monthlyPrizes={monthlyPrizes} />
        <div className="mt-6">
          <HallOfFame limit={6} prizeSkins={prizeSkins} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-3 sm:px-4 py-6 sm:py-10 space-y-5 sm:space-y-6">
      <CreatorHeader creator={creator} code={creator?.code} />
      <StatsGrid creator={creator} dashboard={dashboard} />
      <MilestoneTimeline milestones={dashboard?.milestones} totalRefs={creator?.total_referrals || 0} />
      <SkinProgress progress={dashboard?.skin_progress} settings={dashboard?.settings} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <ReferralsChart days={30} />
        </div>
        <ConversionCard conversion={dashboard?.conversion} />
      </div>

      {/* Rank + next position ribbon */}
      {next && (
        <div className="relative overflow-hidden rounded-2xl border border-white/[0.05] p-5 flex items-center justify-between gap-4 flex-wrap" data-testid="next-position-ribbon"
          style={{ background: "#161225" }}>
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple-400/40 to-transparent" />
          <div className="relative flex items-center gap-4">
            <div className="text-purple-400 text-2xl font-black tabular-nums leading-none">#{next.creator?.rank}</div>
            <div>
              <div className="text-[9px] font-black tracking-[0.32em] text-white/40">PRÓXIMA POSICIÓN</div>
              <div className="mt-0.5 text-sm">
                <span className="font-black text-white">{next.creator?.display_name}</span>
                <span className="mx-2 text-white/25">·</span>
                <span className="tabular-nums text-white/60">{next.creator?.total_referrals?.toLocaleString?.() || 0} referidos</span>
              </div>
            </div>
          </div>
          <div className="relative text-sm text-purple-400 font-black tracking-tight">
            🔥 {next.gap} referido{next.gap === 1 ? "" : "s"} más para subir
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <RecentActivity recent={dashboard?.recent} creatorReward={dashboard?.settings?.creator_reward} />
        <MyReferrals refreshKey={refreshKey} />
      </div>

      <CreatorLeaderboard boards={boards} currentUserId={user.id} prizeSkins={prizeSkins} monthlyPrizes={monthlyPrizes} />

      <HallOfFame limit={6} prizeSkins={prizeSkins} />

      <div className="text-center text-[10px] text-white/40">
        {wsConnected ? "● EN VIVO — Actualizaciones en tiempo real activas" : "○ Reconectando…"}
      </div>
    </div>
  );
}
