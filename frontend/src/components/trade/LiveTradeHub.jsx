import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Search, Radio, ArrowLeftRight, Loader2, X, Check, ShieldAlert, History } from "lucide-react";
import { api, tradeWsUrl } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TradeRoom } from "@/components/trade/TradeRoom";
import TradeHistory from "@/components/trade/TradeHistory";

export default function LiveTradeHub() {
  const { play } = useSound();
  const { refresh } = useAuth();
  const [online, setOnline] = useState([]);
  const [query, setQuery] = useState("");
  const [session, setSession] = useState(null);
  const [invite, setInvite] = useState(null);       // incoming
  const [outgoing, setOutgoing] = useState(null);    // waiting for acceptance
  const [inv, setInv] = useState(null);              // my tradeable inventory
  const [peerInv, setPeerInv] = useState(null);      // other player's inventory (read-only)
  const [alert, setAlert] = useState(null);          // anti-scam: they edited after I locked
  const [view, setView] = useState("live");          // live | history
  const wsRef = useRef(null);

  const loadInventory = useCallback(async () => {
    try { const { data } = await api.tradeInventory(); setInv(data); } catch {}
  }, []);

  useEffect(() => { loadInventory(); }, [loadInventory]);

  // presence + session sync WebSocket
  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(tradeWsUrl());
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        let m; try { m = JSON.parse(ev.data); } catch { return; }
        switch (m.type) {
          case "presence": setOnline(m.online || []); break;
          case "trade_invite": setInvite(m); play?.("open"); break;
          case "trade_start": setSession(m.state); setOutgoing(null); setInvite(null); setAlert(null); loadInventory(); break;
          case "trade_state": setSession(m.state); break;
          case "trade_offer_changed": setAlert({ by: m.by, ts: Date.now() }); play?.("open"); break;
          case "trade_declined": toast.info(`${m.by} rechazó tu invitación`); setOutgoing(null); break;
          case "trade_cancelled": toast.info(`${m.by || "El otro jugador"} canceló el intercambio`); setSession(null); loadInventory(); break;
          case "trade_error": toast.error(m.detail || "El intercambio falló"); setSession(null); loadInventory(); break;
          case "trade_completed":
            play?.("success"); toast.success("¡Intercambio completado!");
            setSession(null); loadInventory(); refresh?.();
            break;
          default: break;
        }
      };
      const ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch {} }, 25000);
      ws._ping = ping;
    } catch {}
    return () => { try { clearInterval(ws?._ping); ws?.close(); } catch {} };
  }, [play, loadInventory, refresh]);

  // resume any active session on mount
  useEffect(() => {
    (async () => {
      try { const { data } = await api.tradeActive(); if (data.session) setSession(data.session); } catch {}
    })();
  }, []);

  // load the other player's (read-only) inventory when a session is active
  useEffect(() => {
    const sid = session?.session_id;
    if (!sid) { setPeerInv(null); return; }
    let stop = false;
    api.tradePeerInventory(sid).then((r) => { if (!stop) setPeerInv(r.data); }).catch(() => {});
    return () => { stop = true; };
  }, [session?.session_id]);

  const doInvite = async (p) => {
    play?.("click");
    try {
      await api.tradeInvite(p.user_id);
      setOutgoing(p);
    } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo invitar"); }
  };

  const acceptInvite = async () => {
    try { await api.tradeRespond(invite.session_id, true); setInvite(null); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo aceptar"); setInvite(null); }
  };
  const declineInvite = async () => {
    try { await api.tradeRespond(invite.session_id, false); } catch {}
    setInvite(null);
  };
  const cancelOutgoing = async () => {
    try { const s = await api.tradeActive(); if (s.data.session) await api.tradeCancel(s.data.session.session_id); } catch {}
    setOutgoing(null);
  };

  const filtered = online.filter((p) => p.name?.toLowerCase().includes(query.toLowerCase()));

  // ── active trade room ──
  if (session) {
    return (
      <TradeRoom
        session={session} inv={inv} peerInv={peerInv} play={play} alert={alert} onClearAlert={() => setAlert(null)}
        onOffer={(items, amber) => api.tradeSetOffer(session.session_id, items, amber).catch((e) => toast.error(e?.response?.data?.detail || "Error en la oferta"))}
        onLock={(locked) => api.tradeLock(session.session_id, locked).catch((e) => toast.error(e?.response?.data?.detail || "Error"))}
        onConfirm={() => api.tradeConfirm(session.session_id).catch((e) => toast.error(e?.response?.data?.detail || "No se pudo confirmar"))}
        onCancel={() => { api.tradeCancel(session.session_id).catch(() => {}); setSession(null); loadInventory(); }}
        reloadInv={loadInventory}
      />
    );
  }

  // ── lobby ──
  return (
    <div data-testid="live-trade-hub">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
        <div>
          <p className="label-overline text-[11px] text-crimson flex items-center gap-2"><Radio size={13} className="animate-pulse" /> En vivo</p>
          <h2 className="font-display font-black text-3xl tracking-tight flex items-center gap-2.5"><ArrowLeftRight className="text-gold" size={28} /> Trade en Vivo</h2>
          <p className="text-sm text-muted-foreground mt-1">Invita a un jugador conectado y intercambien objetos y Amberiums cara a cara.</p>
        </div>
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar jugador…" data-testid="trade-search"
            className="pl-9 pr-3 py-2.5 rounded-lg glass border border-white/10 text-sm w-full sm:w-64 outline-none focus:border-gold/50" />
        </div>
      </div>

      {/* view toggle */}
      <div className="inline-flex rounded-lg border border-white/10 p-1 mb-5 bg-black/20" data-testid="trade-view-toggle">
        <button onClick={() => setView("live")} data-testid="trade-view-live" className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-semibold transition-colors ${view === "live" ? "bg-gold text-background" : "text-muted-foreground hover:text-foreground"}`}><Radio size={13} /> En vivo</button>
        <button onClick={() => setView("history")} data-testid="trade-view-history" className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-semibold transition-colors ${view === "history" ? "bg-gold text-background" : "text-muted-foreground hover:text-foreground"}`}><History size={13} /> Historial</button>
      </div>

      {view === "history" ? <TradeHistory /> : (<>
      {/* limits notice */}
      <div className="flex flex-wrap gap-3 mb-6 text-xs">
        <span className="inline-flex items-center gap-1.5 glass rounded-full px-3 py-1.5 border border-white/10 text-muted-foreground"><ShieldAlert size={13} className="text-gold" /> Máx. 1.000 Amberiums enviados por día</span>
        <span className="inline-flex items-center gap-1.5 glass rounded-full px-3 py-1.5 border border-white/10 text-muted-foreground">Cooldown de 3h por intercambio con objetos</span>
        {inv?.cooldown_left > 0 && <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 border border-crimson/40 bg-crimson/10 text-crimson">En cooldown: {Math.ceil(inv.cooldown_left / 60)} min</span>}
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3"><Users size={15} /> {online.length} en línea</div>
      {filtered.length === 0 ? (
        <div className="text-center py-20 glass rounded-2xl border border-white/10" data-testid="trade-nobody">
          <Users size={44} className="mx-auto mb-3 opacity-40" />
          <p className="text-muted-foreground">{online.length === 0 ? "Nadie está conectado a los intercambios ahora mismo." : "Ningún jugador coincide con tu búsqueda."}</p>
          <p className="text-xs text-muted-foreground/60 mt-1">Cuando otro jugador abra esta pestaña, aparecerá aquí para invitarlo.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="trade-online-grid">
          {filtered.map((p) => (
            <motion.div key={p.user_id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-3 glass rounded-xl border border-white/10 p-3 hover:border-gold/40 transition-colors">
              <div className="w-11 h-11 rounded-lg overflow-hidden bg-white/5 shrink-0">
                {p.avatar ? <img src={p.avatar} alt={p.name} className="w-full h-full object-cover" /> : <Users className="m-auto mt-3 opacity-40" size={18} />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-sm truncate">{p.name}</p>
                <p className="text-[11px] text-emerald flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald" /> En línea</p>
              </div>
              <button onClick={() => doInvite(p)} data-testid={`invite-btn-${p.user_id}`}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold text-background bg-gold hover:brightness-110 transition-all">
                <ArrowLeftRight size={13} /> Invitar
              </button>
            </motion.div>
          ))}
        </div>
      )}

      </>)}
      {/* incoming invite popup */}
      <AnimatePresence>
        {invite && (
          <motion.div className="fixed inset-0 z-[120] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="trade-invite-popup">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
            <motion.div initial={{ scale: 0.85, y: 20 }} animate={{ scale: 1, y: 0 }} className="relative glass-strong rounded-2xl border border-gold/30 p-7 max-w-sm w-full text-center" style={{ boxShadow: "0 0 60px rgba(202,169,104,0.35)" }}>
              <div className="w-16 h-16 rounded-xl overflow-hidden mx-auto mb-4 bg-white/5">
                {invite.from?.avatar ? <img src={invite.from.avatar} alt="" className="w-full h-full object-cover" /> : <Users className="m-auto mt-4 opacity-40" size={26} />}
              </div>
              <p className="label-overline text-[10px] text-gold">Solicitud de intercambio</p>
              <h3 className="font-display font-bold text-xl mt-1"><b>{invite.from?.name}</b> quiere intercambiar contigo</h3>
              <div className="flex gap-3 mt-6">
                <button onClick={declineInvite} data-testid="invite-decline" className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl py-3 font-bold bg-white/10 hover:bg-white/15 border border-white/10"><X size={16} /> Rechazar</button>
                <button onClick={acceptInvite} data-testid="invite-accept" className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl py-3 font-bold text-background bg-gold hover:brightness-110"><Check size={16} /> Aceptar</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* outgoing waiting popup */}
      <AnimatePresence>
        {outgoing && (
          <motion.div className="fixed inset-0 z-[120] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="trade-waiting-popup">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={cancelOutgoing} />
            <motion.div initial={{ scale: 0.85 }} animate={{ scale: 1 }} className="relative glass-strong rounded-2xl border border-white/10 p-7 max-w-sm w-full text-center">
              <Loader2 size={40} className="mx-auto animate-spin text-gold" />
              <h3 className="font-display font-bold text-lg mt-4">Esperando a <b>{outgoing.name}</b>…</h3>
              <p className="text-sm text-muted-foreground mt-1">Tu invitación fue enviada. Se abrirá la sala cuando acepte.</p>
              <button onClick={cancelOutgoing} className="mt-5 w-full rounded-xl py-2.5 font-bold bg-white/10 hover:bg-white/15 border border-white/10">Cancelar</button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
