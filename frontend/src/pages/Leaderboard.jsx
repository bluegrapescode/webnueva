import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Swords, Award, Clock, Users } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { LB_TABS, splitBoard, myPinnedRow } from "@/lib/leaderboardTabs";
import { Podium } from "@/components/leaderboard/Podium";
import { RankRow } from "@/components/leaderboard/RankRow";
import { CountdownRibbon } from "@/components/leaderboard/CountdownRibbon";
import { PrizeShowcase } from "@/components/leaderboard/PrizeShowcase";

const TAB_ICON = { overall: Trophy, kills: Swords, quests: Award, playtime: Clock };
const REFRESH_MS = 60_000;

export default function Leaderboard() {
  const { user } = useAuth();
  const { play } = useSound();
  const [hub, setHub] = useState(null);
  const [me, setMe] = useState(null);
  const [tabKey, setTabKey] = useState("overall");
  const [loading, setLoading] = useState(true);
  const loadedAt = useRef(Date.now());

  const load = async () => {
    try {
      const r = await api.leaderboards();
      setHub(r.data);
      loadedAt.current = Date.now();
    } catch { /* keep the last good payload on a transient failure */ }
    finally { setLoading(false); }
  };
  const loadMe = async () => {
    try { const r = await api.leaderboardsMe(); setMe(r.data?.me || null); }
    catch { setMe(null); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (user) loadMe(); else setMe(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const tab = LB_TABS.find((t) => t.k === tabKey) || LB_TABS[0];
  const board = hub?.boards?.[tab.k];
  const { podium, list } = useMemo(() => splitBoard(board), [board]);
  const meRow = me?.[tab.k] || null;
  const pinned = myPinnedRow(meRow, (podium?.length || 0) + (list?.length || 0));

  const elapsed = Math.floor((Date.now() - loadedAt.current) / 1000);
  const secondsRemaining = Math.max(0, (hub?.seconds_remaining ?? 0) - elapsed);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-14" data-testid="leaderboard-page">
      {/* header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5 mb-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">CLASIFICACIÓN</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {hub?.season_name ? `Temporada ${hub.season_name} · ` : ""}
            Los mejores cazadores del mes. El top 3 general gana PrimeMeat al cerrar la temporada.
          </p>
          {hub != null && (
            <p className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-bold tracking-widest text-white/50">
              <Users size={12} />
              <span className="tabular-nums" data-testid="lb-players-total">{Number(hub.players_total || 0).toLocaleString()}</span>
              CAZADORES CLASIFICADOS
            </p>
          )}
        </motion.div>
        {hub != null && <CountdownRibbon secondsRemaining={secondsRemaining} />}
      </div>

      {hub != null && <PrizeShowcase prizes={hub.prizes} prizeSkins={hub.prize_skins} />}

      {/* tabs */}
      <div className="mt-6 mb-5 flex flex-wrap gap-2" data-testid="lb-tabs">
        {LB_TABS.map((t) => {
          const Icon = TAB_ICON[t.k] || Trophy;
          const active = t.k === tab.k;
          return (
            <button key={t.k} onClick={() => { setTabKey(t.k); play("click"); }} data-testid={`lb-tab-${t.k}`}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-bold border transition-all ${active ? "" : "border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20"}`}
              style={active ? { borderRadius: 3, borderColor: `${t.accent}99`, background: `${t.accent}1A`, color: t.accent } : { borderRadius: 3 }}>
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>

      {loading && hub == null ? (
        <div className="rounded-md border border-white/10 bg-black/30 p-10 text-center text-sm text-white/50">
          Cargando clasificación…
        </div>
      ) : hub == null ? (
        <div className="rounded-md border border-white/10 bg-black/30 p-10 text-center text-sm text-white/50">
          No se pudo cargar la clasificación. Intenta de nuevo en un momento.
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={tab.k} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
            <Podium podium={podium} tab={tab} currentUserId={user?.id} />

            {list.length > 0 && (
              <div className="mt-4 divide-y divide-white/[0.05] rounded-md border border-white/10 bg-black/30 overflow-hidden" data-testid="lb-list">
                {list.map((entry) => (
                  <RankRow key={entry.user_id} entry={entry} tab={tab} isMe={!!user && entry.user_id === user.id} />
                ))}
              </div>
            )}

            {pinned && (
              <div className="mt-3 rounded-md border border-gold/30 bg-black/40 overflow-hidden" data-testid="lb-me-pin">
                <div className="px-4 pt-2 text-[9px] font-black tracking-[0.3em] text-gold/70">TU POSICIÓN</div>
                <RankRow entry={pinned} tab={tab} isMe standalone />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
