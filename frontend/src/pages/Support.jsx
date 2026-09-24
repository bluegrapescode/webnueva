import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  LifeBuoy, Send, Paperclip, Search, Copy, Check, ChevronLeft, Plus, Shield,
  AlertTriangle, Clock, User as UserIcon, MapPin, Tag, Lock, X, Loader2, Link as LinkIcon,
} from "lucide-react";
import { api, ticketsWsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const PRIORITY = { normal: { label: "Normal", color: "#22C55E" }, media: { label: "Media", color: "#EAB308" }, alta: { label: "Alta", color: "#F97316" }, urgente: { label: "Urgente", color: "#EF4444" } };
const STATUS = { open: "Abierto", in_process: "En proceso", waiting_user: "Esperando usuario", resolved: "Resuelto", closed: "Cerrado" };
const STAFF_BOXES = [["new", "Nuevos"], ["unassigned", "Sin asignar"], ["mine", "Mis tickets"], ["in_process", "En proceso"], ["waiting_user", "Esperando usuario"], ["resolved", "Resueltos"], ["closed", "Cerrados"]];
const fmt = (iso) => { try { return new Date(iso).toLocaleString("es", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const isImg = (u) => /\.(png|jpe?g|gif|webp)(\?|$)/i.test(u || "");
const isVid = (u) => /\.(mp4|webm|mov|m4v)(\?|$)/i.test(u || "");

function Copyable({ value, label, testid }) {
  const [ok, setOk] = useState(false);
  if (!value) return null;
  return (
    <button data-testid={testid} onClick={() => { navigator.clipboard?.writeText(value); setOk(true); setTimeout(() => setOk(false), 1200); }}
      className="w-full flex items-center justify-between gap-2 text-left rounded-lg bg-black/30 border border-white/10 px-3 py-2 hover:border-emerald-400/40 transition group">
      <div className="min-w-0"><p className="text-[10px] uppercase tracking-wide text-white/45">{label}</p><p className="text-sm font-mono text-white/90 truncate">{value}</p></div>
      {ok ? <Check size={15} className="text-emerald-400 shrink-0" /> : <Copy size={15} className="text-white/40 group-hover:text-white shrink-0" />}
    </button>
  );
}

export default function Support() {
  const { user } = useAuth();
  const { play } = useSound();
  const [cfg, setCfg] = useState(null);
  const [isStaff, setIsStaff] = useState(false);
  const [mode, setMode] = useState("list");            // list | new | staff
  const [tickets, setTickets] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [staffBox, setStaffBox] = useState("new");
  const [staffCounts, setStaffCounts] = useState({});
  const [staffOnline, setStaffOnline] = useState(0);
  const [search, setSearch] = useState("");
  const [newKey, setNewKey] = useState(0);
  const [active, setActive] = useState(null);          // {ticket, messages, events, can_manage, is_staff}
  const wsRef = useRef(null);
  const activeIdRef = useRef(null);
  const modeRef = useRef(mode);

  useEffect(() => { activeIdRef.current = active?.ticket?.id || null; }, [active]);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  const loadList = useCallback(async () => {
    try { const { data } = await api.ticketMine(statusFilter || undefined); setTickets(data.tickets); } catch {}
  }, [statusFilter]);
  const loadStaff = useCallback(async () => {
    try { const { data } = await api.ticketStaff(staffBox, search); setTickets(data.tickets); setStaffCounts(data.counts); setStaffOnline(data.staff_online); } catch {}
  }, [staffBox, search]);

  useEffect(() => { api.ticketConfig().then(({ data }) => { setCfg(data); setIsStaff(data.is_staff); }).catch(() => {}); }, []);
  useEffect(() => { if (mode === "list") loadList(); if (mode === "staff") loadStaff(); }, [mode, loadList, loadStaff]);

  // WebSocket — una sola conexión estable por sesión de usuario (depende solo de user?.id).
  // Antes dependía de [user, mode] y reconectaba en cada cambio de balance/modo, dejando
  // conexiones huérfanas que duplicaban/triplicaban los mensajes entrantes.
  useEffect(() => {
    let stop = false; let ws;
    const connect = () => {
      if (stop) return;
      ws = new WebSocket(ticketsWsUrl()); wsRef.current = ws;
      ws.onmessage = (e) => {
        let m; try { m = JSON.parse(e.data); } catch { return; }
        const { event, data } = m;
        if (event === "ticket:hello") { setStaffOnline(data.staff_online || 0); }
        else if (event === "message:new") {
          if (data.ticket_id === activeIdRef.current) {
            setActive((a) => a ? { ...a, messages: [...a.messages.filter((x) => x.id !== data.message.id), data.message] } : a);
          }
          if (data.message.author_id && data.message.author_id !== user?.id) play?.("ticketMsg");
        }
        else if (event === "ticket:created") { play?.("ticketNew"); setTickets((t) => (modeRef.current === "staff" ? [data, ...t.filter((x) => x.id !== data.id)] : t)); }
        else if (event === "ticket:updated") {
          setTickets((t) => t.map((x) => x.id === data.id ? data : x));
          setActive((a) => a && a.ticket.id === data.id ? { ...a, ticket: { ...a.ticket, ...data } } : a);
        }
        else if (event === "typing:start" && data.ticket_id === activeIdRef.current) setTyping(data.name);
        else if (event === "typing:stop" && data.ticket_id === activeIdRef.current) setTyping(null);
      };
      ws.onclose = () => { if (!stop) setTimeout(connect, 2500); };
    };
    connect();
    return () => { stop = true; try { ws && ws.close(); } catch {} };
  }, [user?.id]);  // eslint-disable-line

  const [typing, setTyping] = useState(null);
  const wsSend = (event, data) => { try { wsRef.current?.readyState === 1 && wsRef.current.send(JSON.stringify({ event, data })); } catch {} };

  const openTicket = async (id) => {
    try { const { data } = await api.ticketGet(id); setActive(data); wsSend("staff:viewing", { ticket_id: id }); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo abrir el ticket"); }
  };

  if (!cfg) return <div className="min-h-[60vh] grid place-items-center"><Loader2 className="animate-spin text-emerald-400" size={32} /></div>;

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-5" data-testid="support-page">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h1 className="flex items-center gap-2.5 text-2xl font-black text-white"><LifeBuoy className="text-emerald-400" /> Soporte</h1>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-300 bg-emerald-500/10 border border-emerald-400/30 rounded-full px-3 py-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" /> {staffOnline} Staff Online</span>
          {isStaff && <button data-testid="staff-mode-toggle" onClick={() => { setMode(mode === "staff" ? "list" : "staff"); setActive(null); }} className={`text-xs font-black uppercase rounded-lg px-3 py-2 border transition ${mode === "staff" ? "bg-amber-500/20 text-amber-300 border-amber-400/50" : "bg-white/5 text-white/60 border-white/10"}`}><Shield size={13} className="inline mr-1" /> Panel Staff</button>}
          <button data-testid="new-ticket-btn" onClick={() => { setMode("new"); setActive(null); setNewKey((k) => k + 1); }} className="text-xs font-black uppercase rounded-lg px-3 py-2 bg-emerald-500 text-black hover:brightness-110"><Plus size={14} className="inline mr-1" /> Nuevo ticket</button>
        </div>
      </div>

      {mode === "new" ? <NewTicket key={newKey} cfg={cfg} onDone={(t) => { setMode("list"); openTicket(t.id); play?.("ticketNew"); }} onCancel={() => setMode("list")} />
        : (
          <div className="grid lg:grid-cols-[300px_1fr] gap-4">
            {/* Izquierda: lista/colas */}
            <div className="forge-panel rounded-2xl border border-white/10 p-3 h-[calc(100vh-190px)] flex flex-col" data-testid="ticket-list">
              {mode === "staff" ? (
                <>
                  <div className="relative mb-2"><Search size={15} className="absolute left-2.5 top-2.5 text-white/40" /><input data-testid="staff-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="ID, SteamID, usuario…" className="w-full text-sm bg-black/40 border border-white/12 rounded-lg pl-8 pr-2 py-2 text-white/90 outline-none focus:border-amber-400/50" /></div>
                  <div className="flex flex-wrap gap-1 mb-2">{STAFF_BOXES.map(([b, l]) => <button key={b} data-testid={`box-${b}`} onClick={() => setStaffBox(b)} className={`text-[11px] font-bold rounded-lg px-2 py-1 transition ${staffBox === b ? "bg-amber-500/25 text-amber-200" : "bg-white/5 text-white/50 hover:text-white"}`}>{l}{staffCounts[b] ? ` (${staffCounts[b]})` : ""}</button>)}</div>
                </>
              ) : (
                <div className="flex flex-wrap gap-1 mb-2">{[["", "Todos"], ["open", "Abiertos"], ["in_process", "En proceso"], ["resolved", "Resueltos"], ["closed", "Cerrados"]].map(([s, l]) => <button key={s} data-testid={`filter-${s || "all"}`} onClick={() => setStatusFilter(s)} className={`text-[11px] font-bold rounded-lg px-2 py-1 transition ${statusFilter === s ? "bg-emerald-500/25 text-emerald-200" : "bg-white/5 text-white/50 hover:text-white"}`}>{l}</button>)}</div>
              )}
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
                {tickets.length === 0 && <p className="text-sm text-white/35 text-center py-8">Sin tickets.</p>}
                {tickets.map((t) => (
                  <button key={t.id} data-testid={`ticket-item-${t.id}`} onClick={() => openTicket(t.id)}
                    className={`w-full text-left rounded-xl border p-2.5 transition ${active?.ticket?.id === t.id ? "border-emerald-400/50 bg-emerald-500/10" : "border-white/10 bg-black/25 hover:border-white/25"}`}>
                    <div className="flex items-center justify-between gap-2"><span className="font-mono font-black text-xs text-emerald-300">{t.code}</span><span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ color: PRIORITY[t.priority]?.color, background: `${PRIORITY[t.priority]?.color}22` }}>{PRIORITY[t.priority]?.label}</span></div>
                    <p className="text-sm font-bold text-white/90 truncate mt-0.5">{t.subject}</p>
                    <p className="text-[11px] text-white/45 truncate">{t.user_name} · {STATUS[t.status]}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Centro + derecha */}
            {active ? <TicketView key={active.ticket.id} data={active} setActive={setActive} isStaff={isStaff} user={user} typing={typing} wsSend={wsSend} onChanged={() => (mode === "staff" ? loadStaff() : loadList())} play={play} cfg={cfg} />
              : <div className="forge-panel rounded-2xl border border-white/10 grid place-items-center h-[calc(100vh-190px)] text-white/40"><div className="text-center"><LifeBuoy size={40} className="mx-auto mb-2 text-white/20" /><p>Selecciona un ticket o crea uno nuevo.</p></div></div>}
          </div>
        )}
    </div>
  );
}

function NewTicket({ cfg, onDone, onCancel }) {
  const [cat, setCat] = useState(null);
  const [vals, setVals] = useState({});
  const [busy, setBusy] = useState(false);
  const category = cfg.categories.find((c) => c.id === cat);
  const submit = async () => {
    setBusy(true);
    try { const { data } = await api.ticketCreate(cat, vals); toast.success(`Ticket ${data.code} creado`); onDone(data); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo crear"); }
    finally { setBusy(false); }
  };
  if (!cat) return (
    <div className="forge-panel rounded-2xl border border-white/10 p-5" data-testid="category-picker">
      <button onClick={onCancel} className="text-sm text-white/50 hover:text-white flex items-center gap-1 mb-4"><ChevronLeft size={16} /> Volver</button>
      <h2 className="text-lg font-black text-white mb-1">Elige una categoría</h2>
      <p className="text-sm text-white/50 mb-4">Selecciona el tipo de ticket para mostrarte el formulario adecuado.</p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cfg.categories.map((c) => (
          <button key={c.id} data-testid={`cat-${c.id}`} onClick={() => setCat(c.id)} className="text-left rounded-2xl border border-white/10 bg-black/30 p-4 hover:border-emerald-400/50 hover:bg-emerald-500/5 transition">
            <div className="text-3xl mb-1">{c.emoji}</div><p className="font-black text-white">{c.name}</p><p className="text-[12px] text-white/50 mt-0.5 leading-snug">{c.desc}</p>
          </button>
        ))}
      </div>
    </div>
  );
  return (
    <div className="forge-panel rounded-2xl border border-white/10 p-5 max-w-2xl" data-testid="ticket-form">
      <button onClick={() => setCat(null)} className="text-sm text-white/50 hover:text-white flex items-center gap-1 mb-4"><ChevronLeft size={16} /> Cambiar categoría</button>
      <h2 className="text-lg font-black text-white mb-4 flex items-center gap-2">{category.emoji} {category.name}</h2>
      <div className="space-y-3">
        {category.fields.map((f) => (
          <div key={f.key}>
            <label className="text-xs font-bold uppercase tracking-wide text-white/60">{f.label}{f.required && <span className="text-red-400"> *</span>}</label>
            {f.type === "textarea" ? (
              <textarea data-testid={`field-${f.key}`} rows={4} value={vals[f.key] || ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-3 py-2 text-white/90 outline-none focus:border-emerald-400/50 resize-none" />
            ) : f.type === "select" ? (
              <select data-testid={`field-${f.key}`} value={vals[f.key] || ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-3 py-2 text-white/90 outline-none focus:border-emerald-400/50">
                <option value="" className="bg-[#0d0f15]">Selecciona…</option>{f.options.map((o) => <option key={o} value={o} className="bg-[#0d0f15]">{o}</option>)}
              </select>
            ) : f.type === "server" ? (
              <select data-testid={`field-${f.key}`} value={vals[f.key] || ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-3 py-2 text-white/90 outline-none focus:border-emerald-400/50">
                <option value="" className="bg-[#0d0f15]">¿En qué servidor ocurrió?</option>{cfg.servers.map((s) => <option key={s.id} value={s.id} className="bg-[#0d0f15]">{s.name}</option>)}
              </select>
            ) : (
              <input data-testid={`field-${f.key}`} type={f.type === "date" ? "date" : f.type === "time" ? "time" : "text"} value={vals[f.key] || ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-3 py-2 text-white/90 outline-none focus:border-emerald-400/50" />
            )}
          </div>
        ))}
      </div>
      <button data-testid="submit-ticket" disabled={busy} onClick={submit} className="mt-5 w-full py-3 rounded-xl bg-emerald-500 text-black font-black uppercase hover:brightness-110 disabled:opacity-50 flex items-center justify-center gap-2">{busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Crear ticket</button>
    </div>
  );
}

function TicketView({ data, setActive, isStaff, user, typing, wsSend, onChanged, play, cfg }) {
  const t = data.ticket;
  const [text, setText] = useState("");
  const [atts, setAtts] = useState([]);
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(0);
  const fileRef = useRef(null);
  const endRef = useRef(null);
  const typingTO = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [data.messages.length]);
  useEffect(() => { wsSend("message:read", { ticket_id: t.id }); }, [t.id, data.messages.length]);  // eslint-disable-line

  const send = async () => {
    const body = text.trim(); if (!body && atts.length === 0) return;
    setBusy(true);
    try {
      const { data: r } = await api.ticketMessage(t.id, body, atts, internal);
      setActive((a) => a ? { ...a, messages: [...a.messages.filter((x) => x.id !== r.message.id), r.message] } : a);
      setText(""); setAtts([]); wsSend("typing:stop", { ticket_id: t.id });
    } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo enviar"); }
    finally { setBusy(false); }
  };
  const onType = (v) => { setText(v); wsSend("typing:start", { ticket_id: t.id }); clearTimeout(typingTO.current); typingTO.current = setTimeout(() => wsSend("typing:stop", { ticket_id: t.id }), 1500); };
  const addLink = () => { const u = window.prompt("Pega el enlace de la evidencia (imagen, clip, vídeo, link):"); if (u && /^https?:\/\//i.test(u)) setAtts((a) => [...a, u.trim()]); else if (u) toast.error("Debe empezar por http(s)://"); };
  const onFile = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) { toast.error("Archivo demasiado grande (máx 25 MB)."); return; }
    setUploading(1);
    try {
      const { data } = await api.ticketUpload(t.id, f, (p) => setUploading(Math.max(1, p)));
      setAtts((a) => [...a, data.url]);
      toast.success("Archivo subido");
    } catch (err) { toast.error(err?.response?.data?.detail || "No se pudo subir el archivo"); }
    finally { setUploading(0); }
  };
  const doUpdate = async (changes, sound) => { try { await api.ticketUpdate(t.id, changes); if (sound) play?.(sound); onChanged?.(); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } };
  const take = async () => { try { await api.ticketTake(t.id); play?.("ticketMsg"); onChanged?.(); } catch (e) { toast.error("Error"); } };
  const closeTicket = async () => { try { await api.ticketClose(t.id); play?.("ticketMsg"); onChanged?.(); toast.success("Ticket cerrado"); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } };
  const reopenTicket = async () => { try { await api.ticketReopen(t.id); play?.("ticketMsg"); onChanged?.(); toast.success("Ticket reabierto"); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } };
  const isOwner = t.user_id === user?.id;
  const canToggle = isOwner || data.can_manage;

  const cat = cfg.categories.find((c) => c.id === t.category);

  return (
    <div className="grid xl:grid-cols-[1fr_300px] xl:grid-rows-[minmax(0,1fr)] gap-4 h-[calc(100vh-190px)] min-h-0">
      {/* Chat central */}
      <div className="forge-panel rounded-2xl border border-white/10 flex flex-col min-w-0 min-h-0 h-[calc(100vh-190px)] xl:h-full" data-testid="ticket-chat">
        <div className="flex items-center gap-3 p-3 border-b border-white/10">
          <button className="lg:hidden text-white/50" onClick={() => setActive(null)}><ChevronLeft size={18} /></button>
          <div className="min-w-0 flex-1"><p className="font-black text-white truncate">{cat?.emoji} {t.subject}</p><p className="text-[11px] text-white/45 font-mono">{t.code} · {STATUS[t.status]}</p></div>
          <span className="text-[11px] font-bold px-2 py-1 rounded" style={{ color: PRIORITY[t.priority]?.color, background: `${PRIORITY[t.priority]?.color}22` }}>{PRIORITY[t.priority]?.label}</span>
          {canToggle && (t.status === "closed"
            ? <button data-testid="reopen-ticket" onClick={reopenTicket} className="shrink-0 inline-flex items-center gap-1 text-[11px] font-black uppercase rounded-lg px-2.5 py-1.5 bg-emerald-500/15 text-emerald-300 border border-emerald-400/40 hover:bg-emerald-500/25 transition"><Check size={13} /> Reabrir</button>
            : <button data-testid="close-ticket" onClick={closeTicket} className="shrink-0 inline-flex items-center gap-1 text-[11px] font-black uppercase rounded-lg px-2.5 py-1.5 bg-red-500/15 text-red-300 border border-red-400/40 hover:bg-red-500/25 transition"><Lock size={13} /> Cerrar</button>)}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3" data-testid="ticket-messages">
          {data.messages.map((m) => {
            if (m.role === "system") {
              return (
                <div key={m.id} className="flex justify-center my-1" data-testid="system-message">
                  <span className="text-[11px] text-white/50 bg-white/5 border border-white/10 rounded-full px-3 py-1">{m.text} · <span className="font-mono text-white/35">{fmt(m.created_at)}</span></span>
                </div>
              );
            }
            const mine = m.author_id === user?.id;
            return (
              <div key={m.id} className={`flex gap-2.5 ${mine ? "flex-row-reverse" : ""}`}>
                <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{m.author_avatar && <img src={m.author_avatar} alt="" className="w-full h-full object-cover" />}</div>
                <div className={`max-w-[78%] ${mine ? "items-end flex flex-col" : ""}`}>
                  <div className={`flex items-center gap-1.5 mb-1 ${mine ? "flex-row-reverse" : ""}`}>
                    <span className="text-[12px] font-bold text-white/85">{mine ? "Tú" : m.author_name}</span>
                    {m.role === "staff" && <span className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-300">Staff</span>}
                    {m.origin === "discord" && <span data-testid="discord-badge" className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded bg-indigo-400/20 text-indigo-300">Discord</span>}
                    <span className="text-[10px] text-white/40 font-mono">{fmt(m.created_at)}</span>
                  </div>
                  {m.internal ? (
                    <div data-testid="internal-note" className="rounded-xl border border-amber-400/40 bg-amber-500/[0.1] px-3 py-2"><p className="text-[10px] font-black uppercase text-amber-300 flex items-center gap-1"><Lock size={11} /> Nota interna</p><p className="text-sm text-white/90 whitespace-pre-wrap">{m.text}</p></div>
                  ) : (
                    <div className="rounded-2xl px-3 py-2" style={{ background: mine ? "rgba(34,197,94,0.18)" : "rgba(255,255,255,0.06)", borderRadius: mine ? "16px 4px 16px 16px" : "4px 16px 16px 16px" }}>
                      {m.text && <p className="text-sm text-white/90 whitespace-pre-wrap break-words">{m.text}</p>}
                      {(m.attachments || []).map((u, i) => isImg(u)
                        ? <a key={i} href={u} target="_blank" rel="noreferrer"><img src={u} alt="" className="mt-1.5 rounded-lg max-h-48 border border-white/10" /></a>
                        : isVid(u)
                        ? <video key={i} data-testid="attachment-video" src={u} controls className="mt-1.5 rounded-lg max-h-56 max-w-full border border-white/10" />
                        : <a key={i} data-testid="attachment-link" href={u} target="_blank" rel="noreferrer" className="mt-1 block text-sky-300 text-xs underline break-all">🔗 {u}</a>)}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <AnimatePresence>{typing && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2 text-[12px] text-white/50" data-testid="typing-indicator"><span>{typing} está escribiendo</span><span className="flex gap-0.5">{[0, 1, 2].map((i) => <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-white/60" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }} />)}</span></motion.div>}</AnimatePresence>
          <div ref={endRef} />
        </div>
        {t.status !== "closed" && (
          <div className="p-3 border-t border-white/10">
            {atts.length > 0 && <div className="flex flex-wrap gap-1.5 mb-2">{atts.map((u, i) => <span key={i} className="text-[11px] bg-white/10 rounded px-2 py-1 flex items-center gap-1 max-w-[200px]"><span className="truncate">{isImg(u) ? "🖼️" : isVid(u) ? "🎬" : "🔗"} {u.split("/").pop()}</span><button onClick={() => setAtts(atts.filter((_, j) => j !== i))}><X size={11} /></button></span>)}</div>}
            {uploading > 0 && <div className="mb-2" data-testid="upload-progress"><div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full bg-emerald-400 transition-all" style={{ width: `${uploading}%` }} /></div><p className="text-[10px] text-white/50 mt-1">Subiendo… {uploading}%</p></div>}
            {isStaff && data.can_manage && <label className="flex items-center gap-1.5 text-[11px] text-white/60 mb-2 cursor-pointer"><input data-testid="internal-toggle" type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Nota interna (solo staff)</label>}
            <input ref={fileRef} type="file" accept="image/*,video/*" onChange={onFile} className="hidden" data-testid="file-input" />
            <div className="flex items-center gap-2">
              <button data-testid="upload-btn" onClick={() => fileRef.current?.click()} disabled={uploading > 0} title="Subir imagen o vídeo" className="p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/5 disabled:opacity-40">{uploading > 0 ? <Loader2 size={17} className="animate-spin" /> : <Paperclip size={17} />}</button>
              <button data-testid="attach-link-btn" onClick={addLink} title="Adjuntar enlace" className="p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/5"><LinkIcon size={16} /></button>
              <input data-testid="ticket-input" value={text} onChange={(e) => onType(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={internal ? "Escribe una nota interna…" : "Escribe un mensaje…"} className="flex-1 text-sm bg-black/40 border border-white/12 rounded-lg px-3 py-2.5 text-white/90 outline-none focus:border-emerald-400/50" />
              <button data-testid="ticket-send" disabled={busy} onClick={send} className="px-4 py-2.5 rounded-lg text-black font-bold disabled:opacity-50" style={{ background: internal ? "#F59E0B" : "#22C55E" }}><Send size={16} /></button>
            </div>
          </div>
        )}
      </div>

      {/* Panel derecho */}
      <div className="forge-panel rounded-2xl border border-white/10 p-4 overflow-y-auto space-y-3" data-testid="ticket-info">
        <div className="flex items-center gap-2.5"><div className="h-10 w-10 rounded-full overflow-hidden bg-white/10">{t.user_avatar && <img src={t.user_avatar} alt="" className="w-full h-full object-cover" />}</div><div className="min-w-0"><p className="font-black text-white truncate">{t.user_name}</p><p className="text-[11px] text-white/45">{cat?.name}</p></div></div>
        <Copyable label="SteamID" value={t.steam_id} testid="copy-steamid" />
        <Copyable label="Servidor" value={t.server_name} testid="copy-server" />
        <Copyable label="Fecha / Hora del incidente" value={[t.incident_date, t.incident_time].filter(Boolean).join(" ")} testid="copy-incident" />
        {t.discord_id && <Copyable label="Discord ID" value={t.discord_id} testid="copy-discord" />}
        {isStaff && data.can_manage && (
          <div className="space-y-2 pt-2 border-t border-white/10" data-testid="staff-actions">
            {!t.assigned_to && <button data-testid="take-ticket" onClick={take} className="w-full py-2 rounded-lg bg-emerald-500 text-black font-black text-sm">Tomar ticket</button>}
            {t.assigned_name && <p className="text-[12px] text-white/60">Asignado a <b className="text-white">{t.assigned_name}</b></p>}
            <div><label className="text-[10px] uppercase text-white/45">Prioridad</label>
              <select data-testid="set-priority" value={t.priority} onChange={(e) => doUpdate({ priority: e.target.value }, e.target.value === "urgente" ? "ticketUrgent" : null)} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-2 py-1.5 text-white/90">{Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k} className="bg-[#0d0f15]">{v.label}</option>)}</select></div>
            <div><label className="text-[10px] uppercase text-white/45">Estado</label>
              <select data-testid="set-status" value={t.status} onChange={(e) => doUpdate({ status: e.target.value })} className="w-full mt-1 text-sm bg-black/40 border border-white/12 rounded-lg px-2 py-1.5 text-white/90">{Object.entries(STATUS).map(([k, v]) => <option key={k} value={k} className="bg-[#0d0f15]">{v}</option>)}</select></div>
          </div>
        )}
        {isStaff && (data.events || []).length > 0 && (
          <div className="pt-2 border-t border-white/10" data-testid="audit-log">
            <p className="text-[10px] uppercase tracking-wide text-white/45 mb-1.5 flex items-center gap-1"><Clock size={11} /> Auditoría</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">{data.events.map((e, i) => <p key={i} className="text-[11px] text-white/55"><span className="text-white/35 font-mono">{fmt(e.at)}</span> — {e.text}</p>)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
