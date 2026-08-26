import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Search, UserPlus, Check, X, Trash2, Navigation, Radio } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const EMPTY = { friends: [], incoming: [], outgoing: [], tp_incoming: [], tp_outgoing: [], tp_live: [], tp_cooldown_left: 0 };

// Seconds left on your own teleport cooldown, said the way a person would say
// it. The wait is half an hour, so a raw second count is unreadable; minutes are
// rounded UP so the chip never promises sooner than the server will allow.
function teleportWaitLabel(secs) {
  const s = Math.max(0, Math.round(Number(secs) || 0));
  if (s >= 60) {
    const m = Math.ceil(s / 60);
    return m === 1 ? "1 minuto" : `${m} minutos`;
  }
  return s === 1 ? "1 segundo" : `${s} segundos`;
}

// Full-screen hold pop-up for an in-flight teleport countdown: both players see
// it (each side gets its own tp_live row) and either can abort. The seconds tick
// locally between polls; every poll re-syncs to the server's remaining time.
function TeleportCountdownOverlay({ row, onCancel }) {
  const [left, setLeft] = useState(row.countdown_seconds_left);
  useEffect(() => { setLeft(row.countdown_seconds_left); }, [row.id, row.countdown_seconds_left]);
  useEffect(() => {
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 0.25)), 250);
    return () => clearInterval(t);
  }, [row.id]);
  const secs = Math.max(0, Math.ceil(left));
  return (
    <motion.div className="fixed inset-0 z-[100001] flex items-center justify-center p-4"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="teleport-countdown-overlay">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <motion.div initial={{ scale: 0.92, y: 14 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.92, opacity: 0 }}
        className="relative glass-strong rounded-2xl w-full max-w-sm p-6 text-center border border-gold/30">
        <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5 justify-center">
          <Navigation size={11} /> Teletransporte en curso
        </p>
        <p className="text-sm text-muted-foreground mt-2">
          {row.role === "requester"
            ? <>Tu dino viajará junto a <span className="text-foreground font-semibold">{row.other_name}</span></>
            : <><span className="text-foreground font-semibold">{row.other_name}</span> llegará a tu posición</>}
        </p>
        <p className="font-display font-extrabold text-7xl tracking-tight text-gold tabular-nums my-4" data-testid="teleport-countdown-seconds">{secs}</p>
        <p className="text-xs font-bold text-crimson uppercase tracking-wide">No se muevan</p>
        <p className="text-[11px] text-muted-foreground mt-1">Si cualquiera de los dos se mueve, el teletransporte se cancela automáticamente.</p>
        <button onClick={onCancel} data-testid="teleport-countdown-cancel"
          className="mt-5 w-full inline-flex items-center justify-center gap-1.5 text-crimson border border-crimson/30 text-[12px] font-bold px-3 py-2.5 rounded-lg hover:bg-crimson/10 transition-all">
          <X size={13} /> Cancelar teletransporte
        </button>
      </motion.div>
    </motion.div>
  );
}

export function FriendsDock() {
  const { user } = useAuth();
  const { play } = useSound();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [data, setData] = useState(EMPTY);
  const [addMode, setAddMode] = useState(false);
  const searchTimer = useRef(null);
  const prevRef = useRef(null);
  const qRef = useRef("");
  const addModeRef = useRef(false);
  useEffect(() => { qRef.current = q; }, [q]);
  useEffect(() => { addModeRef.current = addMode; }, [addMode]);

  const applyData = (d) => {
    const next = {
      friends: d.friends,
      incoming: d.incoming || [],
      outgoing: d.outgoing || [],
      tp_incoming: d.tp_incoming || [],
      tp_outgoing: d.tp_outgoing || [],
      tp_live: d.tp_live || [],
      tp_cooldown_left: Math.max(0, Number(d.tp_cooldown_left) || 0),
    };
    const p = prevRef.current;
    if (p) {
      // A friend we were waiting on accepted us
      const pOut = new Set(p.outgoing.map((o) => o.user_id));
      const pFriends = new Set(p.friends.map((f) => f.id));
      next.friends.forEach((f) => {
        if (pOut.has(f.id) && !pFriends.has(f.id)) {
          toast.success(`${f.persona_name} aceptó tu solicitud de amistad`);
          try { play("success"); } catch { /* sound optional */ }
        }
      });
      // New incoming friend request
      const pIn = new Set(p.incoming.map((i) => i.user_id));
      next.incoming.forEach((i) => {
        if (!pIn.has(i.user_id)) {
          toast(`Nueva solicitud de amistad de ${i.persona_name}`);
          try { play("open"); } catch { /* sound optional */ }
        }
      });
      // New incoming teleport request
      const pTpIn = new Set(p.tp_incoming.map((t) => t.id));
      next.tp_incoming.forEach((t) => {
        if (!pTpIn.has(t.id)) {
          toast(`${t.from_name} quiere teletransportarse a tu posición`);
          try { play("open"); } catch { /* sound optional */ }
        }
      });
      // Our outgoing teleport request got resolved
      const pTpOut = new Map(p.tp_outgoing.map((t) => [t.id, t.status]));
      next.tp_outgoing.forEach((t) => {
        const was = pTpOut.get(t.id);
        if (was === "pending" && t.status === "countdown") {
          toast.success(`${t.to_name} aceptó — no te muevas durante la cuenta regresiva`);
          try { play("success"); } catch { /* sound optional */ }
        } else if (was === "pending" && t.status === "accepted") {
          toast.success(`${t.to_name} aceptó — teletransportando tu dino`);
          try { play("success"); } catch { /* sound optional */ }
        } else if (was === "pending" && t.status === "declined") {
          toast.error(`${t.to_name} rechazó el teletransporte`);
          try { play("error"); } catch { /* sound optional */ }
        }
      });
      // Countdown outcome (both roles): completed = the mod fired the real
      // teleport; cancelled carries the server's named reason (who moved, señal
      // perdida, aborted by hand, ...).
      const pLive = new Map((p.tp_live || []).map((t) => [t.id, t.status]));
      next.tp_live.forEach((t) => {
        const was = pLive.get(t.id);
        if (was === "countdown" && t.status === "completed") {
          toast.success(t.role === "requester"
            ? `Teletransporte completado — tu dino está junto a ${t.other_name}`
            : `Teletransporte completado — ${t.other_name} llegó a tu posición`);
          try { play("success"); } catch { /* sound optional */ }
        } else if (was === "countdown" && t.status === "cancelled") {
          toast.error(t.reason || "Teletransporte cancelado");
          try { play("error"); } catch { /* sound optional */ }
        }
      });
      // Pending request that vanished without a terminal status = it expired.
      // Only when it was already near its deadline — a transient empty read
      // from the server must not fake an expiry (the row comes back next poll).
      p.tp_outgoing.forEach((t) => {
        if (t.status === "pending" && t.seconds_left <= 12 && !next.tp_outgoing.some((x) => x.id === t.id)) {
          toast.error(`La solicitud de teletransporte a ${t.to_name} expiró`);
        }
      });
    }
    prevRef.current = next;
    setData(next);
  };

  const load = () =>
    api.friends().then((r) => {
      const d = r?.data;
      if (!d || !Array.isArray(d.friends)) return; // non-JSON / unexpected shape: keep last good state
      applyData(d);
    }).catch(() => {});

  useEffect(() => {
    if (!user) return;
    load();
    const t = setInterval(() => {
      load();
      const qq = (qRef.current || "").trim();
      if (addModeRef.current && qq.length >= 2) {
        api.friendsSearch(qq).then((r) => setResults(r.data)).catch(() => {});
      }
    }, 6000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // While a teleport is pending or holding its countdown, the 6s poll is too
  // coarse for a 10s window — tighten to 1.5s until the flow resolves. The
  // effect keys on the boolean only, so the interval isn't churned per poll.
  const tpActive = data.tp_incoming.length > 0
    || data.tp_outgoing.some((t) => t.status === "pending")
    || (data.tp_live || []).some((t) => t.status === "countdown");
  useEffect(() => {
    if (!user || !tpActive) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, tpActive]);

  useEffect(() => {
    clearTimeout(searchTimer.current);
    if (q.trim().length < 2) { setResults([]); return; }
    searchTimer.current = setTimeout(() => {
      api.friendsSearch(q.trim()).then((r) => setResults(r.data)).catch(() => setResults([]));
    }, 350);
    return () => clearTimeout(searchTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  if (!user) return null;

  const onlineCount = data.friends.filter((f) => f.online).length;
  const pending = data.incoming.length + data.tp_incoming.length;
  const countdownRow = (data.tp_live || []).find((t) => t.status === "countdown") || null;

  const sorted = [...data.friends].sort((a, b) => (b.online ? 1 : 0) - (a.online ? 1 : 0));
  const tpPendingFor = (fid) => data.tp_outgoing.find((t) => t.to_id === fid && t.status === "pending");
  // Your own teleport cooldown, refreshed by the same 6s poll as everything else.
  const tpCooldownLeft = Math.max(0, Number(data.tp_cooldown_left) || 0);

  const addFriend = async (id) => {
    try { await api.friendsRequest(id); play("success"); toast.success("Solicitud de amistad enviada"); setResults((r) => r.map((x) => x.id === id ? { ...x, status: "pending" } : x)); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo enviar"); }
  };
  const respond = async (id, accept) => {
    try { await api.friendsRespond(id, accept); play(accept ? "success" : "close"); toast.success(accept ? "Amigo agregado" : "Solicitud rechazada"); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
  };
  const remove = async (id) => {
    try { await api.friendsRemove(id); play("close"); toast.success("Amigo eliminado"); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
  };
  const cancelOutgoing = async (id) => {
    try { await api.friendsRemove(id); play("close"); toast.success("Solicitud cancelada"); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
  };
  const requestTeleport = async (f) => {
    if (!f.online) { toast.error("Tu amigo no está en el servidor en este momento."); return; }
    // No dino-gate here: the server answers with the exact reason (you or your
    // friend missing an in-game dino, cooldown, etc.) and the toast shows it.
    try { await api.friendsTeleportRequest(f.id); play("open"); toast.success(`Solicitud de teletransporte enviada a ${f.persona_name} — esperando que acepte`); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo enviar la solicitud"); }
  };
  const respondTeleport = async (id, accept) => {
    try {
      const { data: r } = await api.friendsTeleportRespond(id, accept);
      if (accept) {
        play("success");
        toast.success(r?.status === "countdown"
          ? (r?.message || "Cuenta regresiva iniciada — no se muevan")
          : `Teletransportando a ${r?.teleported || "tu amigo"} a tu posición`);
      } else { play("close"); }
      load();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); load(); }
  };
  const openAdd = () => { setAddMode(true); play("open"); };

  return (
    <>
      {/* Teleport hold pop-up — shows for BOTH players whenever a countdown is
          in flight, whether or not the dock panel is open. */}
      <AnimatePresence>
        {countdownRow && (
          <TeleportCountdownOverlay key={countdownRow.id} row={countdownRow}
            onCancel={() => respondTeleport(countdownRow.id, false)} />
        )}
      </AnimatePresence>

      {/* Floating action button */}
      <button
        onClick={() => { setOpen((o) => !o); play(open ? "close" : "open"); }}
        data-testid="friends-dock-toggle"
        className="fixed bottom-6 right-6 z-[90] w-14 h-14 rounded-2xl bg-gold text-background shadow-2xl gold-glow flex items-center justify-center hover:brightness-110 active:scale-95 transition-all"
        aria-label="Friends"
      >
        <Users size={22} />
        {onlineCount > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[22px] h-[22px] px-1 rounded-full bg-emerald text-background text-[11px] font-bold flex items-center justify-center border-2 border-background" data-testid="friends-dock-online-count">
            {onlineCount}
          </span>
        )}
        {pending > 0 && (
          <span className="absolute -bottom-1.5 -left-1.5 min-w-[20px] h-[20px] px-1 rounded-full bg-crimson text-white text-[10px] font-bold flex items-center justify-center border-2 border-background" data-testid="friends-dock-pending-count">
            {pending}
          </span>
        )}
      </button>

      {/* Slide-in panel */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div className="fixed inset-0 z-[89] bg-black/40 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.aside
              initial={{ x: 400, opacity: 0.6 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 400, opacity: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 30 }}
              className="fixed top-0 right-0 bottom-0 z-[90] w-[92vw] max-w-[380px] glass-strong border-l border-white/10 flex flex-col"
              data-testid="friends-dock-panel"
            >
              {/* header */}
              <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
                <div className="flex items-center gap-2.5">
                  <Users size={20} className="text-gold" />
                  <div>
                    <p className="label-overline text-[9px] text-gold leading-none">Escuadrón</p>
                    <h3 className="font-display font-bold text-lg leading-tight">Amigos</h3>
                  </div>
                  <span className="ml-1 text-[11px] text-emerald">{onlineCount} online</span>
                </div>
                <button onClick={() => setOpen(false)} data-testid="friends-dock-close" className="p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>
              </div>

              {/* body */}
              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {!addMode ? (
                  <>
                    {/* incoming teleport requests */}
                    {data.tp_incoming.length > 0 && (
                      <div data-testid="friends-dock-tp-incoming">
                        <p className="label-overline text-[10px] text-gold mb-2">Teletransporte ({data.tp_incoming.length})</p>
                        <div className="space-y-1.5">
                          {data.tp_incoming.map((t) => (
                            <div key={t.id} className="glass rounded-xl p-3 border border-gold/40" data-testid={`dock-tp-incoming-${t.id}`}>
                              <p className="text-xs"><span className="font-semibold">{t.from_name}</span> quiere teletransportarse a tu posición</p>
                              <p className="text-[10px] text-muted-foreground mt-0.5">Expira en {t.seconds_left}s</p>
                              <div className="flex items-center gap-2 mt-2">
                                <button onClick={() => respondTeleport(t.id, true)} data-testid={`dock-tp-accept-${t.id}`}
                                  className="flex-1 inline-flex items-center justify-center gap-1 bg-emerald/15 text-emerald border border-emerald/30 text-[11px] font-bold px-2.5 py-1.5 rounded-lg hover:bg-emerald/25">
                                  <Check size={12} /> Aceptar
                                </button>
                                <button onClick={() => respondTeleport(t.id, false)} data-testid={`dock-tp-decline-${t.id}`}
                                  className="flex-1 inline-flex items-center justify-center gap-1 text-crimson border border-crimson/30 text-[11px] font-bold px-2.5 py-1.5 rounded-lg hover:bg-crimson/10">
                                  <X size={12} /> Rechazar
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* incoming friend requests */}
                    {data.incoming.length > 0 && (
                      <div data-testid="friends-dock-incoming">
                        <p className="label-overline text-[10px] text-muted-foreground mb-2">Solicitudes ({data.incoming.length})</p>
                        <div className="space-y-1.5">
                          {data.incoming.map((r) => (
                            <div key={r.user_id} className="flex items-center gap-2 glass rounded-lg p-2" data-testid={`dock-incoming-${r.user_id}`}>
                              <span className="flex-1 text-xs font-semibold truncate">{r.persona_name}</span>
                              <button onClick={() => respond(r.user_id, true)} data-testid={`dock-accept-${r.user_id}`} className="inline-flex items-center gap-1 bg-emerald/15 text-emerald border border-emerald/30 text-[11px] font-bold px-2.5 py-1.5 rounded-lg hover:bg-emerald/25"><Check size={12} /></button>
                              <button onClick={() => respond(r.user_id, false)} data-testid={`dock-decline-${r.user_id}`} className="inline-flex items-center gap-1 text-crimson text-[11px] font-bold px-2 py-1.5 rounded-lg hover:bg-crimson/10"><X size={12} /></button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* outgoing friend requests */}
                    {data.outgoing.length > 0 && (
                      <div data-testid="friends-dock-outgoing">
                        <p className="label-overline text-[10px] text-muted-foreground mb-2">Enviadas ({data.outgoing.length})</p>
                        <div className="space-y-1.5">
                          {data.outgoing.map((o) => (
                            <div key={o.user_id} className="flex items-center gap-2 glass rounded-lg p-2" data-testid={`dock-outgoing-${o.user_id}`}>
                              <span className="flex-1 text-xs font-semibold truncate">{o.persona_name}</span>
                              <span className="text-[10px] text-gold px-1.5">Pendiente</span>
                              <button onClick={() => cancelOutgoing(o.user_id)} data-testid={`dock-outgoing-cancel-${o.user_id}`} title="Cancelar solicitud" className="inline-flex items-center gap-1 text-crimson text-[11px] font-bold px-2 py-1.5 rounded-lg hover:bg-crimson/10"><X size={12} /></button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* friends */}
                    <div data-testid="friends-dock-list">
                      <p className="label-overline text-[10px] text-muted-foreground mb-2">Tus amigos ({data.friends.length})</p>
                      {data.friends.length === 0 ? (
                        <p className="text-muted-foreground py-8 text-center text-sm">Aún no tienes amigos. Toca <span className="text-gold font-semibold">Agregar amigo</span> abajo para importar tus amigos de Steam.</p>
                      ) : (
                        <div className="space-y-1.5">
                          {sorted.map((f) => {
                            const tp = tpPendingFor(f.id);
                            return (
                              <div key={f.id} className="glass rounded-xl p-2.5" data-testid={`dock-friend-${f.id}`}>
                                <div className="flex items-center gap-2.5">
                                  <div className="relative shrink-0">
                                    <img src={f.avatar || MEDIA.logo} alt="" className="w-10 h-10 rounded-lg object-cover" />
                                    <span className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-background ${f.online ? "bg-emerald" : "bg-muted-foreground"}`} data-testid={`dock-friend-status-${f.id}`} />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold truncate">{f.persona_name}</p>
                                    {f.online && f.dino
                                      ? <p className="text-[10px] text-emerald inline-flex items-center gap-1 truncate" data-testid={`dock-friend-presence-${f.id}`}><Radio size={9} /> {f.dino.name} · HP {Math.round(f.dino.health)}%</p>
                                      : f.online
                                        ? <p className="text-[10px] text-emerald inline-flex items-center gap-1" data-testid={`dock-friend-presence-${f.id}`}><Radio size={9} /> En el servidor</p>
                                        : <p className="text-[10px] text-muted-foreground" data-testid={`dock-friend-presence-${f.id}`}>Desconectado</p>}
                                  </div>
                                  <button onClick={() => remove(f.id)} data-testid={`dock-remove-${f.id}`} className="p-1.5 rounded-lg text-crimson hover:bg-crimson/10"><Trash2 size={14} /></button>
                                </div>
                                {(f.online || tp) && (
                                  tp ? (
                                    <button onClick={() => respondTeleport(tp.id, false)} data-testid={`dock-tp-cancel-${f.id}`}
                                      className="mt-2 w-full inline-flex items-center justify-center gap-1.5 bg-gold/15 text-gold border border-gold/30 text-[11px] font-bold px-3 py-2 rounded-lg hover:bg-gold/25 tabular-nums">
                                      <Navigation size={12} /> Esperando respuesta · {tp.seconds_left}s — Cancelar
                                    </button>
                                  ) : tpCooldownLeft > 0 ? (
                                    /* Teleport cooldown (30 min): say how long is left instead of
                                       letting the click go out and come back refused. */
                                    <button type="button" disabled data-testid={`dock-tp-cooldown-${f.id}`}
                                      title="Solo puedes teletransportarte una vez cada 30 minutos"
                                      className="mt-2 w-full inline-flex items-center justify-center gap-1.5 bg-gold/10 text-muted-foreground border border-gold/20 text-[11px] font-bold px-3 py-2 rounded-lg cursor-not-allowed tabular-nums">
                                      <Navigation size={12} /> Teletransporte en {teleportWaitLabel(tpCooldownLeft)}
                                    </button>
                                  ) : (
                                    <button onClick={() => requestTeleport(f)} data-testid={`dock-teleport-${f.id}`}
                                      className="mt-2 w-full inline-flex items-center justify-center gap-1.5 bg-gold text-background text-[11px] font-bold px-3 py-2 rounded-lg hover:brightness-110 active:scale-[0.99] transition-all">
                                      <Navigation size={12} /> Pedir teletransporte
                                    </button>
                                  )
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div data-testid="friends-dock-add">
                    {/* search by name only */}
                    <div className="flex items-center gap-2 glass rounded-lg px-3">
                      <Search size={15} className="text-muted-foreground" />
                      <input className="flex-1 bg-transparent py-2.5 text-sm focus:outline-none" placeholder="Escribe el nombre del jugador…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="friends-dock-search" autoFocus />
                    </div>
                    <p className="text-[10px] text-muted-foreground/70 mt-1.5">Mínimo 2 letras. Solo aparecen jugadores que ya entraron a la web.</p>
                    {q.trim().length >= 2 && results.length === 0 && (
                      <p className="text-muted-foreground py-6 text-center text-sm" data-testid="friends-search-empty">Sin resultados para "{q.trim()}".</p>
                    )}
                    {results.length > 0 && (
                      <div className="mt-2 space-y-1.5" data-testid="friends-dock-search-results">
                        {results.map((r) => (
                          <div key={r.id} className="flex items-center gap-2.5 glass rounded-lg p-2" data-testid={`dock-search-${r.id}`}>
                            <img src={r.avatar || MEDIA.logo} alt="" className="w-9 h-9 rounded-lg object-cover" />
                            <span className="flex-1 min-w-0"><span className="block text-xs font-semibold truncate">{r.persona_name}</span><span className={`text-[10px] ${r.online ? "text-emerald" : "text-muted-foreground"}`}>{r.online ? "En Juego" : "Desconectado"}</span></span>
                            {r.status === "accepted" ? <span className="text-[10px] text-muted-foreground px-1.5">Amigos</span>
                              : r.status === "pending" ? <span className="text-[10px] text-gold px-1.5">Pendiente</span>
                              : <button onClick={() => addFriend(r.id)} data-testid={`dock-add-${r.id}`} className="inline-flex items-center gap-1 bg-gold text-background text-[11px] font-bold px-2.5 py-1.5 rounded-lg hover:brightness-110"><UserPlus size={12} /> Añadir</button>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* footer add-friend button */}
              <div className="border-t border-white/10 p-3">
                <button onClick={() => (addMode ? (setAddMode(false), play("close")) : openAdd())} data-testid="friends-dock-add-toggle"
                  className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold uppercase tracking-wider text-sm py-3 rounded-xl hover:brightness-110 active:scale-[0.99] transition-all">
                  <UserPlus size={16} /> {addMode ? "Volver a mis amigos" : "Agregar amigo"}
                </button>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
