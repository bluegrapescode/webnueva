import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Swords, Award, Map as MapIcon, Sun, CalendarDays, Trophy, Lock, Check, Zap, Clock, Gift, Radio, Hourglass } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { HudCorners } from "@/components/common/Hud";

const fmt = (n) => Number(n || 0).toLocaleString();

const RARITY = {
  Common: { c: "#9ca3af", bg: "rgba(156,163,175,0.12)" },
  Uncommon: { c: "#34d399", bg: "rgba(52,211,153,0.12)" },
  Rare: { c: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  Epic: { c: "#a855f7", bg: "rgba(168,85,247,0.14)" },
  Legendary: { c: "#7CA842", bg: "rgba(124, 168, 66,0.14)" },
};
const OBJ_ICON = { kill_dino: Swords, play_time: Award, visit_location: MapIcon };
const TABS = [
  { k: "daily", label: "Diarias", icon: Sun },
  { k: "weekly", label: "Semanales", icon: CalendarDays },
  { k: "achievement", label: "Logros", icon: Trophy },
  { k: "event", label: "Eventos", icon: Radio },
];

function fmtDur(s) {
  s = Math.max(0, Math.floor(s));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${String(sec).padStart(2, "0")}s`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

function TimerChip({ icon: Icon, label, seconds }) {
  return (
    <div className="inline-flex items-center gap-2 border border-gold/40 bg-gold/[0.06] px-3 py-2" style={{ borderRadius: 3 }}>
      <Icon size={14} className="text-gold" />
      <span className="text-[10px] font-bold tracking-widest text-gold/70">{label}</span>
      <span className="text-xs font-bold text-gold tabular-nums">{fmtDur(seconds)}</span>
    </div>
  );
}

function QuestCard({ q, eggNames, busy, onClaim, index }) {
  const rar = RARITY[q.rarity] || RARITY.Common;
  const Icon = q.locked ? Lock : (OBJ_ICON[q.objective?.type] || Swords);
  const objDone = q.completed ? 1 : 0;
  const pct = Math.min(100, Math.round((q.progress / Math.max(1, q.target)) * 100));
  const canClaim = q.completed && !q.claimed && !q.locked;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * 0.04, 0.3) }}
      data-testid={`quest-card-${q.id}`}
      className={`relative overflow-hidden border p-5 flex flex-col ${q.locked ? "border-white/[0.06] bg-white/[0.01] opacity-70" : q.claimed ? "border-emerald-500/30 bg-emerald-500/[0.03]" : "border-emerald-500/25 bg-white/[0.02]"}`}
      style={{ borderRadius: 3 }}
    >
      {!q.locked && <HudCorners color={q.claimed ? "rgba(52,211,153,0.4)" : `${rar.c}88`} />}

      {/* header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-11 h-11 flex items-center justify-center shrink-0 border"
            style={{ borderRadius: 2, background: q.locked ? "rgba(255,255,255,0.04)" : rar.bg, borderColor: q.locked ? "rgba(255,255,255,0.1)" : `${rar.c}55`, color: q.locked ? "#9ca3af" : rar.c }}>
            <Icon size={20} />
          </div>
          <div className="min-w-0">
            <h3 className="font-display font-bold text-lg leading-tight truncate">{q.title}</h3>
            {q.locked
              ? <p className="text-xs text-gold/80 mt-0.5">Complete <b>{q.requires_title}</b> first</p>
              : <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{q.description}</p>}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-[9px] font-bold tracking-widest px-2 py-0.5 border" style={{ color: rar.c, borderColor: `${rar.c}66`, borderRadius: 2 }}>{q.rarity.toUpperCase()}</span>
          <span className="text-[9px] font-bold tracking-widest text-muted-foreground/60">{q.category.toUpperCase()}</span>
        </div>
      </div>

      {/* objectives summary */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] tracking-widest text-muted-foreground/50">OBJECTIVES</span>
        <span className="text-xs font-bold tabular-nums" style={{ color: objDone ? rar.c : "#9ca3af" }}>{objDone}/1</span>
      </div>
      <div className="h-[3px] w-full bg-white/5 mb-4"><div className="h-full transition-all" style={{ width: `${objDone * 100}%`, background: rar.c }} /></div>

      {/* single objective row */}
      <div className="flex items-center gap-2 mb-1">
        <div className={`w-4 h-4 border flex items-center justify-center shrink-0 ${q.completed ? "" : "border-white/20"}`}
          style={{ borderRadius: 1, background: q.completed ? `${rar.c}22` : "transparent", borderColor: q.completed ? rar.c : undefined }}>
          {q.completed && <Check size={11} style={{ color: rar.c }} />}
        </div>
        <span className={`text-sm ml-auto text-right ${q.completed ? "line-through text-muted-foreground/50" : "text-foreground/90"}`}>{q.objective?.label}</span>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs font-bold tabular-nums" style={{ color: q.completed ? rar.c : "#e5e7eb" }}>{fmt(q.progress)}/{fmt(q.target)}</span>
        <div className="h-[3px] flex-1 bg-white/5"><motion.div className="h-full" initial={{ width: 0 }} animate={{ width: `${pct}%` }} style={{ background: rar.c }} /></div>
      </div>

      {/* footer */}
      <div className="flex items-center justify-between gap-2 mt-auto pt-3 border-t border-white/5">
        <div className="flex items-center gap-3">
          {q.coins > 0 && <span className="inline-flex items-center gap-1 text-sm font-bold"><img src={MEDIA.coinNormal} alt="" className="w-4 h-4 object-contain" />{fmt(q.coins)}<span className="text-[10px] text-muted-foreground/50 ml-0.5">CC</span></span>}
          {q.vip > 0 && <span className="inline-flex items-center gap-1 text-sm font-bold text-gold"><img src={MEDIA.coinVip} alt="" className="w-4 h-4 object-contain" />{fmt(q.vip)}</span>}
          {q.xp > 0 && <span className="inline-flex items-center gap-1 text-sm font-bold text-fuchsia-400"><Zap size={13} className="fill-fuchsia-400/40" />{q.xp}<span className="text-[10px] text-muted-foreground/50 ml-0.5">XP</span></span>}
          {q.egg && <span className="inline-flex items-center gap-1 text-xs font-bold text-fuchsia-300"><Gift size={12} />{eggNames[q.egg] || "Egg"}</span>}
        </div>
        {q.claimed ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-400" data-testid={`quest-claimed-${q.id}`}><Check size={14} /> CLAIMED</span>
        ) : q.locked ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-muted-foreground/50"><Lock size={13} /> LOCKED</span>
        ) : (
          <button onClick={() => onClaim(q)} disabled={!canClaim || busy === q.id} data-testid={`quest-claim-${q.id}`}
            className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 transition-all disabled:cursor-not-allowed"
            style={{ borderRadius: 2, background: canClaim ? rar.c : "rgba(255,255,255,0.05)", color: canClaim ? "#0a0a0a" : "#6b7280" }}>
            {busy === q.id ? "…" : canClaim ? <><Gift size={13} /> RECLAMAR</> : "EN PROGRESO"}
          </button>
        )}
      </div>
    </motion.div>
  );
}

const EVENT_THEME = {
  upcoming: { c: "#38bdf8", label: "COMIENZA EN" },
  active: { c: "#34d399", label: "TERMINA EN" },
  over: { c: "#9ca3af", label: "TERMINADO" },
};

function MultiplierEventCard({ ev, index, elapsed }) {
  const t = ev.event || {};
  const left = (field) => Math.max(0, (t[field] ?? 0) - elapsed);
  const status = t.status === "upcoming" && left("starts_in") <= 0 ? "active"
    : t.status === "active" && left("ends_in") <= 0 ? "over" : (t.status || "over");
  const theme = EVENT_THEME[status] || EVENT_THEME.over;
  const timeLeft = status === "upcoming" ? left("starts_in") : left("ends_in");

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * 0.04, 0.3) }}
      data-testid={`mult-event-card-${ev.id}`}
      className={`relative overflow-hidden border p-5 flex flex-col bg-white/[0.02] ${status === "over" ? "opacity-60" : ""}`}
      style={{ borderRadius: 3, borderColor: `${theme.c}44` }}
    >
      <HudCorners color={`${theme.c}88`} />
      <div className="absolute inset-x-0 top-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${theme.c}AA, transparent)` }} />

      {/* header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-11 h-11 flex items-center justify-center shrink-0 border"
            style={{ borderRadius: 2, background: `${theme.c}14`, borderColor: `${theme.c}55`, color: theme.c }}>
            <Zap size={20} />
          </div>
          <div className="min-w-0">
            <p className="text-[9px] font-bold tracking-widest text-muted-foreground/60">EVENTO MULTIPLICADOR</p>
            <h3 className="font-display font-bold text-lg leading-tight truncate">{ev.title || `Día de ${ev.species}`}</h3>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 text-sm font-bold px-2.5 py-1 border shrink-0"
          style={{ color: theme.c, borderColor: `${theme.c}66`, background: `${theme.c}14`, borderRadius: 2 }} data-testid={`mult-event-value-${ev.id}`}>
          <img src={MEDIA.coinNormal} alt="" className="w-4 h-4 object-contain" /> x{ev.multiplier}
        </span>
      </div>

      {/* countdown strip */}
      <div className="flex items-center justify-between gap-2 mb-3 border px-3 py-2" style={{ borderRadius: 2, borderColor: `${theme.c}33`, background: `${theme.c}0D` }}>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold tracking-widest" style={{ color: theme.c }}>
          <Hourglass size={12} /> {theme.label}
        </span>
        {status !== "over" && <span className="text-xs font-bold tabular-nums" style={{ color: theme.c }}>{fmtDur(timeLeft)}</span>}
      </div>

      <p className="text-sm text-foreground/85 leading-relaxed mt-auto">
        Todo el PrimeMeat que ganes jugando como <b style={{ color: theme.c }}>{ev.species}</b> se
        multiplica <b style={{ color: theme.c }}>x{ev.multiplier}</b> mientras dure el evento.
        {status === "upcoming" ? " Prepárate — aún no comienza." : ""}
      </p>
    </motion.div>
  );
}

export default function Quests() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [data, setData] = useState({ quests: [], counts: {}, resets: {}, egg_names: {}, multiplier_events: [] });
  const [tab, setTab] = useState("daily");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [now, setNow] = useState(Date.now());
  const loadedAt = useRef(Date.now());

  const load = async () => {
    try { const r = await api.listQuests(); setData(r.data); loadedAt.current = Date.now(); }
    catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { if (user) load(); }, [user?.id]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  const elapsed = (now - loadedAt.current) / 1000;
  const dailyLeft = (data.resets?.daily ?? 0) - elapsed;
  const weeklyLeft = (data.resets?.weekly ?? 0) - elapsed;

  const claim = async (q) => {
    if (busy) return;
    setBusy(q.id);
    try {
      await api.claimQuest(q.id);
      play("reward");
      toast.success(`¡Recompensa reclamada: ${q.title}!`);
      await Promise.all([load(), refresh?.()]);
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo reclamar"); }
    finally { setBusy(null); }
  };

  const EVENT_ORDER = { active: 0, upcoming: 1 };
  const multEvents = useMemo(() => {
    const rows = [...(data.multiplier_events || [])];
    rows.sort((a, b) => (EVENT_ORDER[a.event?.status] ?? 3) - (EVENT_ORDER[b.event?.status] ?? 3));
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.multiplier_events]);
  const inTab = useMemo(() => data.quests.filter((q) => q.category === tab), [data.quests, tab]);
  const activeCount = tab === "event"
    ? multEvents.filter((e) => e.event?.status === "active").length
    : inTab.filter((q) => !q.claimed).length;
  const liveEvents = useMemo(() => multEvents.some((e) => e.event?.status === "active"), [multEvents]);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Misiones" sub="Inicia sesión para ver y completar quests con recompensas." /></div>;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-14" data-testid="quests-page">
      {/* header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5 mb-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">QUESTS &amp; ACHIEVEMENTS</h1>
          <p className="text-sm text-muted-foreground mt-2">Completa objetivos y gana recompensas.</p>
        </motion.div>
        <div className="flex flex-wrap gap-2" data-testid="quest-timers">
          <TimerChip icon={Clock} label="DAILY" seconds={dailyLeft} />
          <TimerChip icon={Clock} label="WEEKLY" seconds={weeklyLeft} />
        </div>
      </div>

      {/* tabs */}
      <div className="flex flex-wrap gap-2 mb-8" data-testid="quest-tabs">
        {TABS.map(({ k, label, icon: Icon }) => (
          <button key={k} onClick={() => { setTab(k); play("click"); }} data-testid={`quest-tab-${k}`}
            className={`relative inline-flex items-center gap-2 px-4 py-2.5 text-sm font-bold border transition-all ${tab === k ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300" : "border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20"}`}
            style={{ borderRadius: 3 }}>
            <Icon size={15} /> {label}
            <span className={`text-[11px] px-1.5 py-0.5 ${tab === k ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-muted-foreground"}`} style={{ borderRadius: 2 }}>{data.counts?.[k] ?? 0}</span>
            {k === "event" && liveEvents && (
              <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400" />
              </span>
            )}
          </button>
        ))}
      </div>

      {/* active divider */}
      <div className="flex items-center gap-4 mb-8">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent to-emerald-500/30" />
        <div className="relative inline-flex items-center gap-3 border border-emerald-500/40 bg-emerald-500/[0.06] px-6 py-3" style={{ borderRadius: 3 }}>
          <HudCorners color="rgba(52,211,153,0.6)" />
          {tab === "event" ? <Zap size={18} className="text-emerald-400" /> : <Swords size={18} className="text-emerald-400" />}
          <div className="text-center">
            <p className="font-display font-bold text-emerald-300 tracking-widest text-sm">{tab === "event" ? "EVENTOS ACTIVOS" : "MISIONES ACTIVAS"}</p>
            <p className="text-[10px] text-muted-foreground">{tab === "event" ? "Juega como la especie del evento y tu PrimeMeat se multiplica" : "Completa todos los objetivos para reclamar tu recompensa"}</p>
          </div>
          <span className="text-sm font-bold text-emerald-300 border border-emerald-500/40 px-2 py-0.5" style={{ borderRadius: 2 }} data-testid="quest-active-count">{activeCount}</span>
        </div>
        <div className="h-px flex-1 bg-gradient-to-l from-transparent to-emerald-500/30" />
      </div>

      {/* grid */}
      {loading ? (
        <div className="glass p-10 text-center text-muted-foreground text-sm" style={{ borderRadius: 3 }}>Cargando quests…</div>
      ) : (tab === "event" ? multEvents.length === 0 : inTab.length === 0) ? (
        <div className="glass p-12 text-center" style={{ borderRadius: 3 }}>
          {tab === "event" ? <Radio size={40} className="mx-auto text-muted-foreground/40 mb-3" /> : <Trophy size={40} className="mx-auto text-muted-foreground/40 mb-3" />}
          <p className="font-display font-bold text-lg">{tab === "event" ? "No hay eventos por ahora" : "No hay quests en esta categoría"}</p>
          <p className="text-sm text-muted-foreground mt-1">{tab === "event" ? "El staff publica eventos multiplicadores de PrimeMeat — vuelve pronto." : "Vuelve pronto — el staff añadirá nuevas misiones."}</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="quests-grid">
          {tab === "event"
            ? multEvents.map((ev, i) => <MultiplierEventCard key={ev.id} ev={ev} index={i} elapsed={elapsed} />)
            : inTab.map((q, i) => <QuestCard key={q.id} q={q} eggNames={data.egg_names} busy={busy} onClaim={claim} index={i} />)}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground/60 mt-8 flex items-center gap-2">
        <Award size={13} /> El progreso avanza con acciones dentro del juego (kills, tiempo jugado, ubicaciones). La sincronización en tiempo real se activará al conectar RCON.
      </p>
    </div>
  );
}
