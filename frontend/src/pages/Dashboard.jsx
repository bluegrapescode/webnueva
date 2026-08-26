import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Calendar, Megaphone } from "lucide-react";
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

      {/* Events */}
      <Reveal className="mt-12 mb-6">
        <h2 className="font-display font-extrabold text-2xl tracking-tight inline-flex items-center gap-2"><Calendar size={20} className="text-gold" /> Próximos Eventos</h2>
      </Reveal>
      <div className="grid md:grid-cols-3 gap-6">
        {events.map((e, i) => (
          <Reveal key={i} delay={i * 0.08}>
            <div className="glass rounded-2xl p-6 hover:border-gold/30 hover:-translate-y-1 transition-all duration-300 h-full" data-testid={`event-card-${i}`}>
              <div className="flex items-center justify-between mb-3">
                <span className="label-overline text-[10px] text-gold">{e.type}</span>
                <span className="text-xs text-muted-foreground">{e.date_label}</span>
              </div>
              <h3 className="font-display font-bold text-lg mb-2">{e.title}</h3>
              <p className="text-sm text-muted-foreground">{e.description}</p>
            </div>
          </Reveal>
        ))}
      </div>

      {/* News */}
      <Reveal className="mt-12 mb-6">
        <h2 className="font-display font-extrabold text-2xl tracking-tight inline-flex items-center gap-2"><Megaphone size={20} className="text-gold" /> Últimas Noticias</h2>
      </Reveal>
      <div className="grid md:grid-cols-2 gap-6">
        {news.map((n, i) => (
          <Reveal key={n.id || i} delay={i * 0.06}>
            <div className="group glass rounded-2xl overflow-hidden flex hover:border-gold/30 transition-all duration-300" data-testid={`news-card-${i}`}>
              <div className="w-32 shrink-0 overflow-hidden">
                <img src={n.image} alt="" className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-700" />
              </div>
              <div className="p-5">
                <span className="label-overline text-[10px] text-gold">{n.category}</span>
                <h3 className="font-display font-bold text-lg mt-1 mb-1">{n.title}</h3>
                <p className="text-sm text-muted-foreground line-clamp-2">{n.body}</p>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
