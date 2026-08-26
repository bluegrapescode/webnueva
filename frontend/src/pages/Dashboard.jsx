import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Calendar, Megaphone, Newspaper, Clock, Swords, Users, Skull, Tag, Bell, Sparkles, ArrowUpRight, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { AnimatedCounter } from "@/components/common/AnimatedCounter";
import { StatusDot } from "@/components/common/Hud";
import { Reveal } from "@/components/common/Reveal";
import { useSound } from "@/context/SoundContext";

// Width of the ASCII load bar, in cells. Fixed so the row never reflows on a poll.
const BAR_CELLS = 36;

function Countdown({ iso }) {
  const [left, setLeft] = useState("");
  useEffect(() => {
    const tick = () => {
      const diff = new Date(iso) - new Date();
      if (!Number.isFinite(diff)) { setLeft("—"); return; }
      if (diff <= 0) { setLeft("Ahora"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setLeft(`${h}h ${m}m ${s}s`);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [iso]);
  return <span className="tabular-nums">{left}</span>;
}

// Per-type visual identity for events and news so each card reads at a glance.
const EVENT_STYLE = {
  PvP:       { icon: Swords, color: "#E2574A", label: "PvP" },
  PvE:       { icon: Skull,  color: "#E9C83D", label: "PvE" },
  Community: { icon: Users,  color: "#3FB960", label: "Comunidad" },
  default:   { icon: Calendar, color: "#7CA842", label: "Evento" },
};
const NEWS_STYLE = {
  "Aviso":         { icon: Bell,      color: "#4D9FE8" },
  "Tienda":        { icon: Tag,       color: "#E9C83D" },
  "Evento":        { icon: Calendar,  color: "#3FB960" },
  "Actualización": { icon: Sparkles,  color: "#A855F7" },
  default:         { icon: Newspaper, color: "#7CA842" },
};

function timeAgo(iso) {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const diff = Math.max(0, Date.now() - then);
  const d = Math.floor(diff / 86400000);
  if (d >= 1) return d === 1 ? "hace 1 día" : `hace ${d} días`;
  const h = Math.floor(diff / 3600000);
  if (h >= 1) return `hace ${h} h`;
  const m = Math.floor(diff / 60000);
  return m >= 1 ? `hace ${m} min` : "recién";
}

export default function Dashboard() {
  const { play } = useSound();
  const [status, setStatus] = useState(null);
  const [news, setNews] = useState([]);
  const [events, setEvents] = useState([]);

  useEffect(() => {
    api.serverStatus().then((r) => setStatus(r.data)).catch(() => {});
    api.news().then((r) => setNews(r.data)).catch(() => {});
    api.events().then((r) => setEvents(r.data)).catch(() => {});
    const t = setInterval(() => api.serverStatus().then((r) => setStatus(r.data)).catch(() => {}), 30000);
    return () => clearInterval(t);
  }, []);

  // ---- terminal readout: everything below is derived defensively so a partial or
  // failed /server/status payload renders an honest "sin datos" card, never a crash.
  const online = status?.online !== false;
  const players = Number.isFinite(status?.players) ? status.players : 0;
  const maxPlayers = Number.isFinite(status?.max_players) && status.max_players > 0 ? status.max_players : 0;
  const ratio = maxPlayers > 0 ? Math.max(0, Math.min(players / maxPlayers, 1)) : 0;
  const pct = Math.round(ratio * 100);
  const filled = Math.min(BAR_CELLS, players > 0 ? Math.max(1, Math.round(ratio * BAR_CELLS)) : 0);

  const staff = Array.isArray(status?.staff_online) ? status.staff_online.filter((s) => s && s.name) : [];

  // feminine for "mutaciones", masculine for "humanos"
  const onOff = (v, fem) => (v === true ? (fem ? "activadas" : "activados") : v === false ? (fem ? "desactivadas" : "desactivados") : "—");
  const rows = [
    { k: "estado", v: !status ? "conectando…" : online ? "EN LÍNEA" : "DESCONECTADO" },
    { k: "cola", v: Number.isFinite(status?.queue) ? status.queue : "—" },
    { k: "mutaciones", v: onOff(status?.mutations, true) },
    { k: "humanos", v: onOff(status?.humans, false) },
    { k: "próximo reinicio", v: status?.next_restart ? <Countdown iso={status.next_restart} /> : "—" },
  ];

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="mb-10">
        <p className="label-overline text-xs text-gold mb-2">Centro de Mando</p>
        <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Panel</h1>
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Server status — RCON terminal readout */}
        {/* min-w-0: a grid item defaults to min-width:auto, so the monospace readout
            (which never wraps mid-token) would otherwise push the card past the viewport
            on a phone and give the whole page a horizontal scroll. */}
        <Reveal className={`min-w-0 ${staff.length ? "lg:col-span-2" : "lg:col-span-3"}`}>
          <div className="term-card relative rounded-2xl overflow-hidden h-full px-6 py-6 sm:px-9 sm:py-8" data-testid="server-status-card">
            {/* header line */}
            <div className="term-head flex items-center gap-2.5 pb-3.5 mb-6 flex-wrap">
              <span data-testid="server-status-indicator" className="inline-flex">
                <StatusDot online={online} size={9} />
              </span>
              <span className="font-code text-[11px] sm:text-xs tracking-[0.1em] term-dim flex-1 min-w-0 break-words leading-relaxed">
                RCON://NA1 · {online ? "SESIÓN ACTIVA" : "SIN RESPUESTA"} · TICK {status?.tickrate ?? "—"} · {(status?.version || "EVRIMA").toUpperCase()}
              </span>
            </div>

            {/* server identity */}
            <h2 className="font-code font-bold text-xl sm:text-[28px] leading-tight tracking-tight term-bright break-words">
              {status?.name || "[NA1] LA ISLA NUBLAR"}
            </h2>
            <p className="font-code text-[13px] term-dim mt-1">mapa {status?.map || "—"}</p>

            {/* population readout */}
            <p className="font-code term-bright mt-7 mb-1.5 leading-none" style={{ fontSize: "clamp(40px, 6vw, 64px)", letterSpacing: "-0.03em" }}>
              <AnimatedCounter value={status?.players ?? 0} />
              <span className="term-dim" style={{ fontSize: "clamp(16px, 2vw, 24px)", letterSpacing: "0" }}>
                {" "}/ {status?.max_players ?? 0} supervivientes
              </span>
            </p>
            <p className="font-code term-track whitespace-nowrap overflow-hidden" style={{ fontSize: "clamp(11px, 1.5vw, 17px)", letterSpacing: "-0.05em" }}>
              [<span className="term-fill">{"#".repeat(filled)}</span>{".".repeat(BAR_CELLS - filled)}] {pct}%
            </p>

            {/* key/value rows */}
            <dl className="mt-7 font-code text-[13px] sm:text-[15px]">
              {rows.map((r) => (
                <div key={r.k} className="flex items-baseline gap-4 py-[3px]">
                  <dt className="term-key w-[128px] sm:w-[190px] shrink-0">{r.k}</dt>
                  <dd className="term-bright font-bold m-0">{r.v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Reveal>

        {/* Staff online — hidden entirely when the status payload carries no staff list,
            which is the case on the live RCON path. An empty card beside the readout
            reads as a broken panel. */}
        {staff.length > 0 && (
        <Reveal delay={0.1}>
          <div className="glass rounded-2xl p-7 h-full" data-testid="staff-online-card">
            <p className="label-overline text-xs text-muted-foreground mb-5">Staff en Línea</p>
            <div className="space-y-3">
              {staff.map((s) => (
                <div key={s.name} className="flex items-center gap-3 glass rounded-xl p-3">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold-deep to-gold flex items-center justify-center font-display font-bold text-background text-sm">
                    {s.name[0]}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.role}</p>
                  </div>
                  <span className={`h-2 w-2 rounded-full ${s.status === "online" ? "bg-emerald" : "bg-gold"}`} />
                </div>
              ))}
            </div>
          </div>
        </Reveal>
        )}
      </div>

      {/* ---------------------------- EVENTS ---------------------------- */}
      <Reveal className="mt-14 mb-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="grid place-items-center w-11 h-11 rounded-lg bg-gold/15 border border-gold/30 text-gold shrink-0"><Calendar size={20} /></span>
            <div>
              <p className="label-overline text-[11px] text-gold">Agenda del servidor</p>
              <h2 className="font-display font-extrabold text-2xl sm:text-3xl tracking-tight">Próximos Eventos</h2>
            </div>
          </div>
          {events.length > 0 && <span className="text-xs font-bold uppercase tracking-wider px-3 py-1.5 rounded-md glass border border-white/10 text-muted-foreground">{events.length} programados</span>}
        </div>
      </Reveal>
      {events.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-muted-foreground">No hay eventos programados por ahora.</div>
      ) : (
      <div className="grid md:grid-cols-3 gap-5">
        {events.map((e, i) => {
          const st = EVENT_STYLE[e.type] || EVENT_STYLE.default;
          const Icon = st.icon;
          return (
          <Reveal key={e.id || i} delay={i * 0.08}>
            <div className="group relative glass rounded-2xl p-6 h-full overflow-hidden hover:-translate-y-1 transition-all duration-300"
              style={{ borderColor: "rgba(255,255,255,0.08)" }} data-testid={`event-card-${i}`}>
              {/* top accent + ambient glow in the type colour */}
              <span className="absolute inset-x-0 top-0 h-1" style={{ background: st.color }} />
              <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" style={{ background: `radial-gradient(circle, ${st.color}33, transparent 70%)` }} />
              <div className="flex items-center justify-between mb-4">
                <span className="inline-flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-md" style={{ color: st.color, background: `${st.color}1f`, border: `1px solid ${st.color}44` }}>
                  <Icon size={13} /> {st.label}
                </span>
                <span className="grid place-items-center w-10 h-10 rounded-lg shrink-0" style={{ background: `${st.color}1a`, color: st.color }}><Icon size={20} /></span>
              </div>
              <h3 className="font-display font-bold text-xl mb-2 leading-tight">{e.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-5">{e.description}</p>
              <div className="flex items-center gap-2 pt-4 border-t border-white/10 text-sm font-semibold" style={{ color: st.color }}>
                <Clock size={15} /> <span className="tabular-nums">{e.date_label}</span>
              </div>
            </div>
          </Reveal>
          );
        })}
      </div>
      )}

      {/* ---------------------------- NEWS ---------------------------- */}
      <Reveal className="mt-16 mb-6">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-11 h-11 rounded-lg bg-gold/15 border border-gold/30 text-gold shrink-0"><Megaphone size={20} /></span>
          <div>
            <p className="label-overline text-[11px] text-gold">Lo último de la isla</p>
            <h2 className="font-display font-extrabold text-2xl sm:text-3xl tracking-tight">Últimas Noticias</h2>
          </div>
        </div>
      </Reveal>
      {news.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-muted-foreground">No hay noticias todavía.</div>
      ) : (
      <div className="grid lg:grid-cols-3 gap-5">
        {news.map((n, i) => {
          const st = NEWS_STYLE[n.category] || NEWS_STYLE.default;
          const Icon = st.icon;
          const featured = i === 0;
          return (
          <Reveal key={n.id || i} delay={i * 0.06} className={featured ? "lg:col-span-3" : ""}>
            <article className={`group glass rounded-2xl overflow-hidden hover:border-gold/40 transition-all duration-300 h-full flex ${featured ? "flex-col md:flex-row" : "flex-col"}`} data-testid={`news-card-${i}`}>
              {/* image — full, never cut: fixed aspect + contain over a themed backdrop */}
              <div className={`relative shrink-0 overflow-hidden ${featured ? "md:w-[46%] aspect-video md:aspect-auto md:min-h-[260px]" : "aspect-video"}`}
                style={{ background: "radial-gradient(120% 120% at 50% 0%, #16210f 0%, #0b0d08 70%)" }}>
                <img src={n.image} alt="" loading="lazy"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                  className="absolute inset-0 w-full h-full object-contain p-5 group-hover:scale-105 transition-transform duration-700" />
                <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(180deg, transparent 40%, rgba(9,11,7,0.55) 100%)" }} />
                <span className="absolute top-3 left-3 inline-flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-md backdrop-blur-sm" style={{ color: st.color, background: `${st.color}22`, border: `1px solid ${st.color}55` }}>
                  <Icon size={12} /> {n.category}
                </span>
              </div>
              {/* body */}
              <div className={`p-6 flex flex-col ${featured ? "md:justify-center flex-1" : ""}`}>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground mb-2">
                  <Clock size={12} /> <span>{timeAgo(n.created_at)}</span>
                </div>
                <h3 className={`font-display font-bold leading-tight mb-2 ${featured ? "text-2xl" : "text-lg"}`}>{n.title}</h3>
                <p className={`text-sm text-muted-foreground leading-relaxed ${featured ? "line-clamp-4 md:max-w-2xl" : "line-clamp-3"}`}>{n.body}</p>
                <button className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-gold hover:gap-2.5 transition-all w-fit" data-testid={`news-readmore-${i}`}>
                  Leer más <ArrowUpRight size={14} />
                </button>
              </div>
            </article>
          </Reveal>
          );
        })}
      </div>
      )}
    </div>
  );
}
