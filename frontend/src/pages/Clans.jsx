import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, Crown, Users, Send, Swords, Settings2, LogOut, Trash2, UserPlus, Star, Check, X, Plus, ArrowUpRight, Flame, MessageSquare, Globe, Search, MapPin, BarChart3, Inbox, Clock, Hexagon, ChevronRight, Bell, Calendar, Hash, Paperclip, Smile } from "lucide-react";
import { useTurf } from "@/hooks/useTurf";
import { ClanProvider, useClan } from "@/context/ClanContext";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const PERMS = [
  ["edit_clan", "Editar clan"], ["manage_ranks", "Gestionar rangos"], ["assign_ranks", "Asignar rangos"],
  ["invite", "Invitar"], ["kick", "Expulsar"], ["manage_members", "Gestionar miembros"],
];
const input = "w-full rounded-lg px-3 py-2.5 text-sm bg-white/[0.04] border border-white/12 focus:outline-none focus:border-emerald-400/60 transition";

function TagBadge({ tag, color, size = "md" }) {
  const s = size === "lg" ? "text-lg px-3 py-1.5" : size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-sm px-2 py-1";
  return <span className={`inline-flex items-center font-display font-black uppercase tracking-tight rounded-md ${s}`} style={{ color: "#0a0b0f", background: color || "#7CA842", boxShadow: `0 2px 14px -2px ${color || "#7CA842"}` }}>[{tag}]</span>;
}

const CLAN_COLORS = ["#C08B5C", "#E11D48", "#F59E0B", "#22C55E", "#38BDF8", "#A855F7", "#EC4899", "#7C3AED"];
const BANNER_IMG = "/clan/banner.jpg";
const TREX_IMG = "/clan/trex.jpg";
const PAGE_BG = "/clan/forestbg.jpg";

function roleColor(order, isLeader) {
  if (isLeader) return "#F5B841";
  if (order <= 1) return "#A855F7";
  if (order === 2) return "#38BDF8";
  if (order === 3) return "#22C55E";
  return "#7CA842";
}
function fmtDate(iso) { try { return new Date(iso).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" }); } catch { return "—"; } }
function fmtTime(iso) { try { return new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } }
function Avatar({ src, size = 34 }) {
  return <div className="rounded-full overflow-hidden bg-white/10 shrink-0 ring-1 ring-white/10" style={{ width: size, height: size }}>{src ? <img src={src} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full grid place-items-center text-white/30"><Users size={size * 0.5} /></div>}</div>;
}
function fmtAgo(iso) {
  try { const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "Ahora"; if (s < 3600) return `Hace ${Math.floor(s / 60)} min`;
    if (s < 86400) return `Hace ${Math.floor(s / 3600)} h`; return `Hace ${Math.floor(s / 86400)} d`;
  } catch { return ""; }
}
function RoleBadge({ clan, rankId, isLeader }) {
  const r = (clan.ranks || []).find((x) => x.id === rankId) || {};
  const name = isLeader ? "Líder" : (r.name || "Miembro");
  const c = roleColor(r.order ?? 5, isLeader);
  return <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: c, background: `${c}1f`, border: `1px solid ${c}55` }}>{isLeader && <Crown size={9} />}{name}</span>;
}
const STATUS_COLOR = { "En línea": "#22C55E", "En partida": "#F59E0B", "Ausente": "#EF4444" };

// ═══════════ Modal: Fundar un clan ═══════════
function FoundModal({ cfg, onClose }) {
  const { act, busy } = useClan();
  const { play } = useSound();
  const [f, setF] = useState({ name: "", tag: "", color: "#C08B5C", description: "" });
  const valid = f.name.trim().length >= 3 && f.tag.length === 4 && cfg.creation_enabled;
  const found = () => act(() => import("@/lib/api").then(({ api }) => api.clanFound({ ...f, tag: f.tag.toUpperCase() })), "¡Clan fundado!").then(onClose).catch(() => {});

  return (
    <motion.div className="fixed inset-0 z-[120] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="found-modal">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onClose} />
      <motion.div initial={{ scale: 0.94, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 8 }}
        className="relative w-full max-w-lg forge-panel rounded-2xl border border-amber-500/30 overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/10">
          <span className="w-10 h-10 rounded-lg bg-amber-500/20 border border-amber-400/40 flex items-center justify-center"><Shield className="text-amber-400" size={20} /></span>
          <h2 className="font-display font-black uppercase tracking-tight text-xl flex-1">Fundar un clan</h2>
          <button onClick={onClose} data-testid="found-close" className="p-2 rounded-lg text-white/50 hover:bg-white/10 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Vista previa */}
          <div className="flex items-center gap-3 rounded-xl border border-white/12 bg-black/40 px-4 py-3.5">
            <TagBadge tag={f.tag || "????"} color={f.color} size="md" />
            <span className="font-display font-black text-lg truncate">{f.name.trim() || "Nombre de tu clan"}</span>
          </div>

          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-white/50 mb-1 flex justify-between"><span>Nombre del clan</span><span className="text-white/35">{f.name.length}/28</span></span>
            <input data-testid="found-name" className={input} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="La Manada Ápice" maxLength={28} />
          </label>

          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-white/50 mb-1 block">Tag (4 caracteres, letras/números, único)</span>
            <input data-testid="found-tag" className={input + " uppercase font-black tracking-[0.3em]"} value={f.tag}
              onChange={(e) => setF({ ...f, tag: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4) })} placeholder="APEX" />
            {f.tag.length > 0 && f.tag.length < 4 && <span className="text-[10px] text-amber-300 mt-1 block">El tag debe tener exactamente 4 caracteres.</span>}
          </label>

          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-white/50 mb-2 block">Color</span>
            <div className="flex flex-wrap gap-2.5" data-testid="found-colors">
              {CLAN_COLORS.map((c) => (
                <button key={c} data-testid={`found-color-${c.replace("#", "")}`} onClick={() => setF({ ...f, color: c })}
                  className={`w-9 h-9 rounded-md transition-transform ${f.color === c ? "ring-2 ring-white ring-offset-2 ring-offset-black scale-105" : "hover:scale-110"}`}
                  style={{ background: c }} aria-label={c} />
              ))}
            </div>
          </div>

          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-white/50 mb-1 block">Descripción (opcional)</span>
            <input className={input} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={120} placeholder="Domina los territorios de La Isla" />
          </label>

          {!cfg.creation_enabled && <p className="text-red-300 text-sm">La creación de clanes está deshabilitada temporalmente.</p>}

          <div className="flex items-center justify-between gap-3 pt-1">
            <div className="text-sm"><span className="text-[11px] uppercase tracking-wider text-white/45 block">Costo</span>
              <span className="font-mono font-black text-amber-300 text-lg">{(cfg.founding_cost ?? 20000).toLocaleString()} {cfg.founding_currency_label || "Amberium"}</span></div>
            <button data-testid="found-submit" disabled={busy || !valid} onClick={() => { play?.("click"); found(); }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-emerald-300 to-emerald-500 disabled:opacity-40 hover:brightness-105 transition">
              <Shield size={18} /> Fundar clan
            </button>
          </div>
          <p className="text-[11px] text-white/40">Necesitas mínimo {cfg.min_members ?? 20} miembros para activar el clan en Turf Wars.</p>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ═══════════ Sin clan: estado vacío / fundar / invitaciones / directorio ═══════════
function NoClan() {
  const { me, act } = useClan();
  const cfg = me?.config || {};
  const [dir, setDir] = useState([]);
  const [showFound, setShowFound] = useState(false);
  useEffect(() => { import("@/lib/api").then(({ api }) => api.clanDirectory().then(({ data }) => setDir(data.clans || [])).catch(() => {})); }, [me]);

  return (
    <div className="space-y-6">
      {/* Estado vacío */}
      <div className="rounded-2xl border border-white/10 forge-panel px-6 py-14 text-center" data-testid="no-clan-empty">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-amber-500/10 border border-amber-400/30 flex items-center justify-center mb-5">
          <div className="relative"><Shield className="text-amber-400/70" size={30} /><Plus className="text-amber-300 absolute -bottom-0.5 -right-0.5 bg-black rounded-full" size={13} /></div>
        </div>
        <h2 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">No estás en un clan aún</h2>
        <p className="text-sm text-white/55 max-w-md mx-auto mt-3">Funda tu propio clan con un tag único, o espera la invitación de un líder. Los clanes son solo por invitación.</p>
        <button data-testid="open-found-modal" disabled={!cfg.creation_enabled} onClick={() => setShowFound(true)}
          className="mt-6 inline-flex items-center gap-2 px-6 py-3 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-amber-300 to-amber-500 disabled:opacity-40 hover:brightness-105 transition">
          <Shield size={18} /> Fundar un clan · {(cfg.founding_cost ?? 20000).toLocaleString()}
        </button>
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 space-y-6">
          {(me?.invites || []).length > 0 && (
            <div className="forge-panel rounded-2xl border border-emerald-500/25 p-5" data-testid="clan-invites">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-emerald-300 mb-3"><UserPlus size={16} /> Invitaciones</h3>
              <div className="space-y-2">
                {me.invites.map((iv) => (
                  <div key={iv.clan_id} className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/30 p-2.5">
                    <TagBadge tag={iv.tag} color={iv.color} />
                    <span className="flex-1 font-bold text-sm truncate">{iv.name}</span>
                    <button data-testid={`invite-accept-${iv.clan_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanInviteAccept(iv.clan_id)), "¡Te uniste al clan!")} className="text-xs font-black px-3 py-1.5 rounded-lg bg-emerald-400 text-black">Aceptar</button>
                    <button onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanInviteDecline(iv.clan_id)))} className="p-1.5 rounded-lg text-white/40 hover:text-red-300"><X size={15} /></button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          <div className="forge-panel rounded-2xl border border-white/10 p-5" data-testid="clan-directory">
            <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-white/80 mb-3"><Swords size={16} className="text-amber-400" /> Clanes de La Isla</h3>
            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
              {dir.length === 0 && <p className="text-sm text-white/40 py-6 text-center">Aún no hay clanes. ¡Sé el primero!</p>}
              {dir.map((c) => (
                <div key={c.id} data-testid={`directory-card-${c.id}`} className="flex items-center gap-3 rounded-xl border p-2.5 bg-black/30" style={{ borderColor: `${c.color}44` }}>
                  <TagBadge tag={c.tag} color={c.color} />
                  <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{c.name}</p><p className="text-[11px] text-white/45"><Users size={10} className="inline mr-1" />{c.member_count} · <Flame size={10} className="inline mx-1 text-amber-400" />{c.notoriety}</p></div>
                  {c.active ? <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-400/40">Activo</span> : <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded bg-white/10 text-white/45">Reclutando</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <AnimatePresence>{showFound && <FoundModal cfg={cfg} onClose={() => setShowFound(false)} />}</AnimatePresence>
    </div>
  );
}

// ═══════════ Chat en vivo (Clan / Global de clanes) ═══════════
function ClanChat() {
  const { me, messages, globalMessages, sendChat } = useClan();
  const { play } = useSound();
  const clan = me?.clan || {};
  const [channel, setChannel] = useState("clan");
  const [text, setText] = useState("");
  const endRef = useRef(null);
  const isGlobal = channel === "global";
  const list = isGlobal ? globalMessages : messages;
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [list.length, channel]);
  const send = () => { const t = text.trim(); if (!t) return; play?.("click"); sendChat(t, channel); setText(""); };
  const toggle = () => { play?.("click"); setChannel(isGlobal ? "clan" : "global"); };
  const accent = isGlobal ? "#38BDF8" : "#22C55E";
  const roleOf = (uid) => { const m = (me?.members || []).find((x) => x.user_id === uid); return { rankId: m?.rank_id || "member", isLeader: clan.leader_id === uid }; };

  return (
    <div className="forge-panel rounded-2xl border flex flex-col h-[600px]" style={{ borderColor: `${accent}33` }} data-testid="clan-chat">
      <div className="flex items-center justify-between gap-3 p-4 pb-3 border-b border-white/8 flex-wrap">
        <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest" style={{ color: accent }}>
          {isGlobal ? <Globe size={16} /> : <MessageSquare size={16} />} {isGlobal ? "Chat Global" : "Chat del clan"}
        </h3>
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide select-none">
          <span className={!isGlobal ? "text-emerald-300" : "text-white/35"}>Chat del Clan</span>
          <button type="button" role="switch" aria-checked={isGlobal} data-testid="chat-channel-toggle" onClick={toggle}
            className="relative w-11 h-6 rounded-full transition-colors duration-200 shrink-0" style={{ background: accent, boxShadow: `0 0 10px ${accent}88` }}>
            <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all duration-200" style={{ left: isGlobal ? 22 : 2 }} />
          </button>
          <span className={isGlobal ? "text-sky-300" : "text-white/35"}>Chat Global (Clanes)</span>
          <Settings2 size={15} className="text-white/30 ml-1" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pt-3 space-y-2" data-testid="chat-messages">
        {list.length === 0 && <p className="text-sm text-white/35 text-center py-10">{isGlobal ? "Aún nadie ha escrito en el chat global de clanes. 🌐" : "Sé el primero en escribir. 💬"}</p>}
        {list.map((m) => m.system ? (
          <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-lg border-l-2 border-emerald-400 bg-emerald-500/[0.08] px-3 py-2 flex items-start gap-2">
            <Settings2 size={15} className="text-emerald-400 mt-0.5 shrink-0" />
            <div className="min-w-0"><span className="text-emerald-300 font-bold text-[11px]">Sistema · {fmtTime(m.created_at)}</span><p className="text-sm text-white/75 break-words">{m.text}</p></div>
          </motion.div>
        ) : (() => {
          const r = roleOf(m.user_id);
          return (
            <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2.5">
              <Avatar src={m.avatar} size={34} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[13px] font-bold text-white/90 truncate">{m.name}</span>
                  {isGlobal ? (m.clan_tag && <TagBadge tag={m.clan_tag} color={m.clan_color} size="sm" />) : <RoleBadge clan={clan} rankId={r.rankId} isLeader={r.isLeader} />}
                  <span className="ml-auto text-[10px] text-white/35 font-mono shrink-0">{fmtTime(m.created_at)}</span>
                </div>
                <p className="text-sm text-white/85 break-words leading-snug mt-0.5">{m.text}</p>
              </div>
            </motion.div>
          );
        })())}
        <div ref={endRef} />
      </div>

      <div className="p-3 border-t border-white/8 flex items-center gap-2">
        <button type="button" className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors"><Paperclip size={17} /></button>
        <input data-testid="chat-input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={isGlobal ? "Mensaje a todos los clanes…" : "Escribe un mensaje…"} className={input + " flex-1"} maxLength={500} />
        <button type="button" className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors"><Smile size={17} /></button>
        <button data-testid="chat-send" onClick={send} className="px-4 py-2.5 rounded-lg text-black font-bold transition-transform hover:scale-105 active:scale-95" style={{ background: accent, boxShadow: `0 4px 16px -4px ${accent}` }}><Send size={16} /></button>
      </div>
    </div>
  );
}

// ═══════════ Banner del clan ═══════════
function BannerHeader({ clan, online, canEdit, onEdit }) {
  const xpPct = Math.min(100, Math.round((clan.xp_into / Math.max(1, clan.xp_needed)) * 100));
  const stats = [
    { icon: Users, label: "Miembros", val: `${clan.member_count}/${clan.min_members}` },
    { icon: Globe, label: "Online", val: online },
    { icon: Flame, label: "Notoriedad", val: clan.notoriety.toLocaleString() },
    { icon: MapPin, label: "Territorios", val: clan.territories },
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} data-testid="clan-header"
      className="relative rounded-2xl border overflow-hidden" style={{ borderColor: `${clan.color}55` }}>
      <div className="absolute inset-0"><img src={BANNER_IMG} alt="" className="w-full h-full object-cover" /></div>
      <div className="absolute inset-0" style={{ background: "linear-gradient(90deg, rgba(6,9,13,0.94) 0%, rgba(6,9,13,0.6) 38%, rgba(6,9,13,0.2) 68%, transparent 100%)" }} />
      <div className="absolute inset-0 bg-gradient-to-t from-[#06090d] via-transparent to-transparent" />
      <div className="relative p-5 sm:p-6 flex flex-col md:flex-row md:items-start gap-5">
        <div className="flex items-start gap-4 flex-1 min-w-0">
          <div className="font-brush text-4xl sm:text-5xl px-4 py-2 rounded-xl shrink-0" style={{ color: clan.color, background: "rgba(0,0,0,0.4)", border: `2px solid ${clan.color}`, boxShadow: `0 0 22px ${clan.color}, inset 0 0 14px ${clan.color}44`, textShadow: `0 0 12px ${clan.color}` }}>{clan.tag}</div>
          <div className="min-w-0">
            <h1 className="font-brush text-white text-4xl sm:text-6xl leading-[0.95] flex items-center gap-3 drop-shadow-[0_3px_14px_rgba(0,0,0,0.85)]"><span className="truncate">{clan.name}</span><Crown className="text-amber-400 shrink-0" size={30} /></h1>
            <p className="text-sm sm:text-base font-bold uppercase tracking-wide mt-1.5" style={{ color: clan.color }}>“{clan.description || "Fuerza · Unión · Dominio"}”</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 text-[11px] text-white/60">
              <span className="inline-flex items-center gap-1"><Calendar size={11} /> Fundado {fmtDate(clan.created_at)}</span>
              <span className="inline-flex items-center gap-1"><Hash size={11} /> ID del Clan: {clan.code}</span>
              <span className="inline-flex items-center gap-1"><Globe size={11} /> Idioma: {clan.language}</span>
              <span className="inline-flex items-center gap-1"><Swords size={11} /> Tipo: {clan.clan_type}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-col md:items-end gap-3 md:w-[440px] shrink-0">
          {canEdit && <button data-testid="edit-clan-btn" onClick={onEdit} className="self-start md:self-end inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-black uppercase bg-black/55 border border-white/15 hover:bg-black/75 backdrop-blur"><Settings2 size={14} /> Editar clan</button>}
          <div className="flex items-center gap-3">
            <div className="w-14 h-14 flex items-center justify-center rounded-xl font-display font-black text-2xl relative shrink-0" style={{ color: clan.color, background: "rgba(0,0,0,0.55)", border: `2px solid ${clan.color}` }}>
              <Hexagon className="absolute inset-0 m-auto opacity-25" size={54} style={{ color: clan.color }} />{clan.level}
            </div>
            <div className="w-44">
              <p className="text-[10px] uppercase tracking-widest text-white/60 font-bold">Nivel del clan</p>
              <div className="h-2 rounded-full bg-black/60 overflow-hidden mt-1"><div className="h-full rounded-full" style={{ width: `${xpPct}%`, background: clan.color, boxShadow: `0 0 8px ${clan.color}` }} /></div>
              <p className="text-[10px] text-white/55 mt-1 font-mono">{clan.xp_into.toLocaleString()} / {clan.xp_needed.toLocaleString()} XP</p>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-2 w-full">
            {stats.map((s) => (
              <div key={s.label} className="rounded-xl bg-black/45 border border-white/10 px-2.5 py-2 backdrop-blur flex items-center gap-2">
                <s.icon size={16} className="shrink-0" style={{ color: clan.color }} />
                <div className="min-w-0 leading-none"><p className="font-mono font-black text-base leading-none truncate">{s.val}</p><p className="text-[8px] uppercase tracking-widest text-white/45 mt-1">{s.label}</p></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function ClanTabs({ tabs, tab, setTab, me }) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1" data-testid="clan-tabs">
      {tabs.map(([t, label, Icon]) => {
        const badge = t === "invitaciones" ? ((me.join_requests || []).length + (me.sent_invites || []).length) : 0;
        return (
          <button key={t} data-testid={`tab-${t}`} onClick={() => setTab(t)} className={`shrink-0 inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-xs font-black uppercase tracking-wide transition ${tab === t ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/40" : "bg-white/[0.03] text-white/60 hover:text-white border border-white/10"}`}>
            <Icon size={14} /> {label}{badge > 0 && <span className="text-[9px] bg-red-500 text-white rounded-full px-1.5 py-0.5">{badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

function MemberRow({ m, clan, perms, isLeader, user, act }) {
  return (
    <div data-testid={`member-row-${m.user_id}`} className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/30 p-2.5">
      <div className="relative h-9 w-9 rounded-full overflow-hidden bg-white/10 shrink-0">{m.avatar && <img src={m.avatar} alt="" className="w-full h-full object-cover" />}<span className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#0d0f15] ${m.online ? "bg-emerald-400" : "bg-white/25"}`} /></div>
      <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{m.name}</p><RoleBadge clan={clan} rankId={m.rank_id} isLeader={clan.leader_id === m.user_id} /></div>
      {perms.assign_ranks && clan.leader_id !== m.user_id && (
        <select data-testid={`assign-${m.user_id}`} value={m.rank_id} onChange={(e) => act(() => import("@/lib/api").then(({ api }) => api.clanAssign(m.user_id, e.target.value)), "Rango asignado")} className="text-xs rounded-lg bg-white/[0.05] border border-white/12 px-2 py-1.5">
          {clan.ranks.filter((r) => r.id !== "leader").map((r) => <option key={r.id} value={r.id} className="bg-[#0d0f15]">{r.name}</option>)}
        </select>
      )}
      {isLeader && clan.leader_id !== m.user_id && <button title="Transferir liderazgo" data-testid={`transfer-${m.user_id}`} onClick={() => window.confirm(`¿Transferir liderazgo a ${m.name}?`) && act(() => import("@/lib/api").then(({ api }) => api.clanTransfer(m.user_id)), "Liderazgo transferido")} className="p-1.5 rounded-lg text-amber-300 hover:bg-amber-400/10"><Crown size={15} /></button>}
      {perms.kick && clan.leader_id !== m.user_id && m.user_id !== user?.id && <button data-testid={`kick-${m.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanKick(m.user_id)), "Miembro expulsado")} className="p-1.5 rounded-lg text-white/40 hover:text-red-300"><X size={15} /></button>}
    </div>
  );
}

function Panel({ title, icon: Icon, count, children, testid, accent = "#22C55E", right }) {
  return (
    <div className="forge-panel rounded-2xl border border-white/10 p-4" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest" style={{ color: accent }}><Icon size={15} /> {title}{count != null && <span className="text-white/40">({count})</span>}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}
const VerTodas = () => <span className="text-[10px] font-bold text-white/40 hover:text-white/70 inline-flex items-center gap-0.5 cursor-pointer">Ver todas <ChevronRight size={12} /></span>;

// Panel: Invitar jugadores (búsqueda en vivo)
function InvitePlayersPanel({ act }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => { import("@/lib/api").then(({ api }) => api.clanPlayerSearch(q).then(({ data }) => live && setRows(data.players || [])).catch(() => {})); }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [q]);
  return (
    <Panel title="Invitar Jugadores" icon={UserPlus} testid="invite-players">
      <div className="relative mb-2"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><input data-testid="invite-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar jugador…" className={input + " pl-9"} /></div>
      <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
        {rows.length === 0 && <p className="text-xs text-white/35 py-4 text-center">Sin resultados.</p>}
        {rows.map((p) => (
          <div key={p.id} className="flex items-center gap-2.5 rounded-lg border border-white/8 bg-black/30 p-2">
            <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}</div>
            <div className="flex-1 min-w-0"><p className="text-sm font-bold truncate">{p.name}</p><p className="text-[10px] text-white/45 flex items-center gap-1.5">Nivel {p.level}<span className="w-1 h-1 rounded-full" style={{ background: STATUS_COLOR[p.status] }} /><span style={{ color: STATUS_COLOR[p.status] }}>{p.status}</span></p></div>
            <button data-testid={`invite-player-${p.id}`} disabled={p.in_clan || p.invited} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanInvite({ user_id: p.id })), "Invitación enviada")} className="text-xs font-black px-3 py-1.5 rounded-lg bg-emerald-400 text-black disabled:opacity-40 disabled:bg-white/10 disabled:text-white/40">{p.in_clan ? "En clan" : p.invited ? "Invitado" : "Invitar"}</button>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RightPanels({ me, canManage, act }) {
  if (!canManage) return null;
  return (
    <div className="space-y-4" data-testid="hub-right">
      <InvitePlayersPanel act={act} />
      <Panel title="Invitaciones Pendientes" icon={Inbox} count={(me.sent_invites || []).length} testid="pending-invites" accent="#38BDF8" right={<VerTodas />}>
        <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
          {(me.sent_invites || []).length === 0 && <p className="text-xs text-white/35 py-3 text-center">Sin invitaciones pendientes.</p>}
          {(me.sent_invites || []).map((p) => (
            <div key={p.user_id} className="flex items-center gap-2.5 rounded-lg border border-white/8 bg-black/30 p-2">
              <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}</div>
              <div className="flex-1 min-w-0"><p className="text-sm font-bold truncate">{p.name}</p><p className="text-[10px] text-white/45">Nivel {p.level} · {fmtAgo(p.created_at)}</p></div>
              <button data-testid={`cancel-invite-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanCancelInvite(p.user_id)), "Invitación cancelada")} className="p-1.5 rounded-lg text-white/40 hover:text-red-300 border border-white/10"><X size={14} /></button>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Solicitudes para Unirse" icon={Bell} count={(me.join_requests || []).length} testid="join-requests" accent="#F5B841" right={<VerTodas />}>
        <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
          {(me.join_requests || []).length === 0 && <p className="text-xs text-white/35 py-3 text-center">Sin solicitudes.</p>}
          {(me.join_requests || []).map((p) => (
            <div key={p.user_id} className="flex items-center gap-2.5 rounded-lg border border-white/8 bg-black/30 p-2">
              <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}</div>
              <div className="flex-1 min-w-0"><p className="text-sm font-bold truncate">{p.name}</p><p className="text-[10px] text-white/45">Nivel {p.level} · {fmtAgo(p.created_at)}</p></div>
              <button data-testid={`accept-request-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanRequestAccept(p.user_id)), "¡Miembro aceptado!")} className="p-1.5 rounded-lg text-emerald-300 bg-emerald-500/15 border border-emerald-400/30"><Check size={14} /></button>
              <button data-testid={`decline-request-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanRequestDecline(p.user_id)))} className="p-1.5 rounded-lg text-white/40 hover:text-red-300 border border-white/10"><X size={14} /></button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Locked() {
  return <div className="forge-panel rounded-2xl border border-white/10 p-10 text-center text-white/45"><Shield size={30} className="mx-auto mb-3 opacity-50" /><p className="text-sm">No tienes permiso para ver esta sección.</p></div>;
}

function DangerZone({ isLeader, act }) {
  return (
    <div className="pt-4 border-t border-white/10 flex flex-wrap gap-2">
      {isLeader
        ? <button data-testid="disband-btn" onClick={() => window.confirm("¿Disolver el clan? Esto es permanente.") && act(() => import("@/lib/api").then(({ api }) => api.clanDisband()), "Clan disuelto")} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-black uppercase text-red-300 border border-red-400/30 hover:bg-red-500/10"><Trash2 size={14} /> Disolver clan</button>
        : <button data-testid="leave-clan-btn" onClick={() => window.confirm("¿Salir del clan?") && act(() => import("@/lib/api").then(({ api }) => api.clanLeave()), "Saliste del clan")} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-black uppercase text-red-300 border border-red-400/30 hover:bg-red-500/10"><LogOut size={14} /> Salir del clan</button>}
    </div>
  );
}

// ═══════════ Hub del clan ═══════════
function Hub() {
  const { me, act } = useClan();
  const { play } = useSound();
  const { user } = useAuth();
  const clan = me.clan; const perms = me.my_perms || {}; const isLeader = me.is_leader;
  const canManage = isLeader || perms.invite || perms.manage_members;
  const [tab, setTab] = useState("chat");
  const turf = useTurf(true);
  const myZones = (turf.zones || []).filter((z) => z.owner?.id === clan.id);
  const reqCount = (me.join_requests || []).length;
  const invCount = (me.sent_invites || []).length;

  const SIDE = [
    ["chat", "Mi Clan", Shield], ["explorar", "Explorar Clanes", Globe], ["solicitudes", "Solicitudes", Bell],
    ["invitaciones", "Invitaciones", UserPlus], ["territorios", "Territorios", MapPin], ["turfwars", "Turf Wars", Swords],
    ["ranking", "Ranking", BarChart3], ["config", "Configuración", Settings2],
  ];
  const TOP = [
    ["resumen", "Resumen", BarChart3], ["miembros", "Miembros", Users], ["chat", "Chat", MessageSquare],
    ["invitaciones", "Invitaciones", UserPlus], ["rangos", "Rangos", Star], ["territorios", "Territorios", Shield],
    ["turfwars", "Turf Wars", Swords], ["estadisticas", "Estadísticas", BarChart3], ["config", "Configuración", Settings2],
  ];
  const navBtn = (t, label, Icon, mobile) => (
    <button key={label} data-testid={`side-${t}`} onClick={() => { play?.("click"); setTab(t); }}
      className={`flex items-center gap-2.5 rounded-lg text-sm font-bold transition ${mobile ? "shrink-0 px-3 py-2 whitespace-nowrap" : "w-full px-3 py-2.5"} ${tab === t ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/40 shadow-[inset_0_0_22px_rgba(34,197,94,0.18)]" : "text-white/55 hover:text-white hover:bg-white/[0.04] border border-transparent"}`}>
      <Icon size={16} /><span className="truncate">{label}</span>
      {t === "solicitudes" && reqCount > 0 && <span className="ml-auto text-[10px] bg-red-500 text-white rounded-full px-1.5">{reqCount}</span>}
      {t === "invitaciones" && invCount > 0 && <span className="ml-auto text-[10px] bg-red-500 text-white rounded-full px-1.5">{invCount}</span>}
    </button>
  );

  const RequestList = () => (
    <Panel title="Solicitudes para Unirse" icon={Bell} count={reqCount} testid="join-requests" accent="#F5B841">
      <div className="space-y-1.5">{reqCount === 0 && <p className="text-xs text-white/35 py-3 text-center">Sin solicitudes.</p>}
        {(me.join_requests || []).map((p) => (
          <div key={p.user_id} className="flex items-center gap-2.5 rounded-lg border border-white/8 bg-black/30 p-2">
            <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}</div>
            <div className="flex-1 min-w-0"><p className="text-sm font-bold truncate">{p.name}</p><p className="text-[10px] text-white/45">Nivel {p.level} · {fmtAgo(p.created_at)}</p></div>
            <button data-testid={`accept-request-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanRequestAccept(p.user_id)), "¡Miembro aceptado!")} className="p-1.5 rounded-lg text-emerald-300 bg-emerald-500/15 border border-emerald-400/30"><Check size={14} /></button>
            <button data-testid={`decline-request-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanRequestDecline(p.user_id)))} className="p-1.5 rounded-lg text-white/40 hover:text-red-300 border border-white/10"><X size={14} /></button>
          </div>
        ))}</div>
    </Panel>
  );
  const SentList = () => (
    <Panel title="Invitaciones Pendientes" icon={Inbox} count={invCount} testid="pending-invites" accent="#38BDF8">
      <div className="space-y-1.5">{invCount === 0 && <p className="text-xs text-white/35 py-3 text-center">Sin invitaciones pendientes.</p>}
        {(me.sent_invites || []).map((p) => (
          <div key={p.user_id} className="flex items-center gap-2.5 rounded-lg border border-white/8 bg-black/30 p-2">
            <div className="h-8 w-8 rounded-full overflow-hidden bg-white/10 shrink-0">{p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}</div>
            <div className="flex-1 min-w-0"><p className="text-sm font-bold truncate">{p.name}</p><p className="text-[10px] text-white/45">Nivel {p.level} · {fmtAgo(p.created_at)}</p></div>
            <button data-testid={`cancel-invite-${p.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanCancelInvite(p.user_id)), "Invitación cancelada")} className="p-1.5 rounded-lg text-white/40 hover:text-red-300 border border-white/10"><X size={14} /></button>
          </div>
        ))}</div>
    </Panel>
  );

  return (
    <div className="grid lg:grid-cols-[210px_1fr] gap-6" data-testid="clan-hub">
      <aside className="hidden lg:flex flex-col rounded-2xl border border-white/10 forge-panel overflow-hidden self-start sticky top-24">
        <div className="p-4 border-b border-white/10 flex items-center gap-2"><Swords size={18} className="text-emerald-400" /><span className="font-display font-black uppercase tracking-tight">Clanes</span></div>
        <nav className="p-2 space-y-0.5">{SIDE.map(([t, label, Icon]) => navBtn(t, label, Icon, false))}</nav>
        <div className="mt-auto relative h-40 opacity-90" style={{ WebkitMaskImage: "linear-gradient(to top, black 50%, transparent)", maskImage: "linear-gradient(to top, black 50%, transparent)" }}><img src={TREX_IMG} alt="" className="w-full h-full object-cover" /></div>
      </aside>

      <div className="space-y-5 min-w-0">
        <BannerHeader clan={clan} online={me.online_count || 0} canEdit={perms.edit_clan} onEdit={() => setTab("config")} />
        {/* Barra de pestañas horizontal (según diseño) */}
        <div className="flex gap-1.5 overflow-x-auto pb-1 -mt-1" data-testid="clan-top-tabs">
          {TOP.map(([t, label, Icon]) => (
            <button key={label} data-testid={`toptab-${t}`} onClick={() => { play?.("click"); setTab(t); }}
              className={`shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-black uppercase tracking-wide transition ${tab === t ? "bg-emerald-500/25 text-emerald-300 border border-emerald-400/50 shadow-[0_0_18px_rgba(34,197,94,0.28)]" : "bg-black/45 text-white/55 hover:text-white border border-white/10 backdrop-blur"}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
        {/* Nav compacto (móvil) */}
        <nav className="lg:hidden flex gap-1.5 overflow-x-auto pb-1" data-testid="clan-mobile-nav">{SIDE.map(([t, label, Icon]) => navBtn(t, label, Icon, true))}</nav>

        {(tab === "chat" || tab === "resumen") && (
          <div className="grid xl:grid-cols-[1fr_340px] gap-5">
            <ClanChat />
            {canManage ? <RightPanels me={me} canManage={canManage} act={act} /> : (
              <Panel title="Miembros" icon={Users} count={clan.member_count}><div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">{(me.members || []).map((m) => <MemberRow key={m.user_id} m={m} clan={clan} perms={{}} isLeader={false} user={user} act={act} />)}</div></Panel>
            )}
          </div>
        )}

        {tab === "miembros" && (
          <Panel title="Miembros del clan" icon={Users} count={clan.member_count} testid="miembros-tab">
            <div className="grid sm:grid-cols-2 gap-2">{(me.members || []).map((m) => <MemberRow key={m.user_id} m={m} clan={clan} perms={perms} isLeader={isLeader} user={user} act={act} />)}</div>
          </Panel>
        )}

        {tab === "rangos" && <div className="forge-panel rounded-2xl border border-white/10 p-5" data-testid="rangos-tab"><h3 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-amber-300 mb-3"><Star size={15} /> Rangos y permisos</h3><RanksPanel clan={clan} /></div>}

        {tab === "solicitudes" && (canManage ? <div className="grid lg:grid-cols-2 gap-5"><InvitePlayersPanel act={act} /><RequestList /></div> : <Locked />)}

        {tab === "invitaciones" && (canManage ? <div className="grid lg:grid-cols-2 gap-5"><InvitePlayersPanel act={act} /><SentList /></div> : <Locked />)}

        {(tab === "territorios" || tab === "turfwars") && (
          <Panel title={tab === "territorios" ? "Territorios controlados" : "Turf Wars"} icon={tab === "territorios" ? MapPin : Swords} accent="#38BDF8">
            <p className="text-sm text-white/60 mb-3">Tu clan controla <b className="text-white">{myZones.length}</b> {myZones.length === 1 ? "territorio" : "territorios"}. La guerra por las zonas ocurre en el mapa en vivo.</p>
            {myZones.length > 0 && <div className="flex flex-wrap gap-2 mb-4">{myZones.map((z) => <span key={z.id} className="text-xs font-bold px-2.5 py-1 rounded-lg border" style={{ color: clan.color, borderColor: `${clan.color}55`, background: `${clan.color}14` }}>{z.name}</span>)}</div>}
            <a href="/my-dino?tab=map" data-testid="goto-turf-map" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500 text-black font-black text-sm uppercase"><MapPin size={16} /> Abrir mapa · Turf Wars</a>
          </Panel>
        )}

        {tab === "explorar" && <DirectoryList />}
        {(tab === "ranking" || tab === "estadisticas") && <DirectoryList ranking />}

        {tab === "config" && (
          <div className="space-y-5" data-testid="config-tab">
            {perms.edit_clan && <div className="forge-panel rounded-2xl border border-white/10 p-5"><h3 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-amber-300 mb-3"><Settings2 size={15} /> Ajustes del clan</h3><SettingsPanel clan={clan} /></div>}
            <Panel title="Miembros del clan" icon={Users} count={clan.member_count}>
              <div className="grid sm:grid-cols-2 gap-2">{(me.members || []).map((m) => <MemberRow key={m.user_id} m={m} clan={clan} perms={perms} isLeader={isLeader} user={user} act={act} />)}</div>
            </Panel>
            {perms.manage_ranks && <div className="forge-panel rounded-2xl border border-white/10 p-5"><RanksPanel clan={clan} /></div>}
            <div className="forge-panel rounded-2xl border border-white/10 p-5"><DangerZone isLeader={isLeader} act={act} /></div>
          </div>
        )}
      </div>
    </div>
  );
}

function DirectoryList({ ranking }) {
  const [dir, setDir] = useState([]);
  useEffect(() => { import("@/lib/api").then(({ api }) => api.clanDirectory().then(({ data }) => setDir(data.clans || [])).catch(() => {})); }, []);
  return (
    <Panel title={ranking ? "Ranking de clanes" : "Explorar clanes"} icon={ranking ? BarChart3 : Globe} count={dir.length}>
      <div className="space-y-2">
        {dir.map((c, i) => (
          <div key={c.id} className="flex items-center gap-3 rounded-xl border p-2.5 bg-black/30" style={{ borderColor: `${c.color}44` }}>
            {ranking && <span className="w-5 text-center font-black text-white/50">{i === 0 ? <Crown size={14} className="text-amber-400 inline" /> : i + 1}</span>}
            <TagBadge tag={c.tag} color={c.color} />
            <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{c.name}</p><p className="text-[11px] text-white/45"><Users size={10} className="inline mr-1" />{c.member_count} · Nvl {c.level} · <Flame size={10} className="inline mx-1 text-amber-400" />{c.notoriety}</p></div>
            {c.active ? <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-400/40">Activo</span> : <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded bg-white/10 text-white/45">Reclutando</span>}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function HdrBtn({ children, icon: Icon, onClick, active, danger, testid }) {
  return <button data-testid={testid} onClick={onClick} className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-black uppercase tracking-wide transition ${danger ? "text-red-300 border border-red-400/30 hover:bg-red-500/10" : active ? "bg-amber-400 text-black" : "bg-white/[0.05] text-white/70 hover:text-white border border-white/10"}`}><Icon size={14} /> {children}</button>;
}

function SettingsPanel({ clan }) {
  const { act } = useClan();
  const [f, setF] = useState({ name: clan.name, tag: clan.tag, color: clan.color, description: clan.description, language: clan.language, clan_type: clan.clan_type });
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Nombre</span><input className={input} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Tag (4 caracteres)</span><input className={input + " uppercase font-black tracking-[0.3em]"} value={f.tag} onChange={(e) => setF({ ...f, tag: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4) })} /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Color</span>
        <div className="flex flex-wrap gap-2">{CLAN_COLORS.map((c) => <button key={c} onClick={() => setF({ ...f, color: c })} className={`w-8 h-8 rounded-md transition ${f.color === c ? "ring-2 ring-white" : ""}`} style={{ background: c }} />)}</div></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Lema / Descripción</span><input className={input} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={120} placeholder="Fuerza · Unión · Dominio" /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Idioma</span><input className={input} value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })} maxLength={20} placeholder="Español" /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Tipo</span><input className={input} value={f.clan_type} onChange={(e) => setF({ ...f, clan_type: e.target.value })} maxLength={28} placeholder="PvP / Territorios" /></label>
      <button data-testid="save-settings-btn" onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanEdit(f)), "Clan actualizado")} className="sm:col-span-2 py-2.5 rounded-lg bg-amber-400 text-black font-black text-sm uppercase">Guardar cambios</button>
    </div>
  );
}

function RanksPanel({ clan }) {
  const { act } = useClan();
  const [form, setForm] = useState({ id: "", name: "", order: 5, perms: {} });
  const save = () => act(() => import("@/lib/api").then(({ api }) => api.clanSaveRank(form)), "Rango guardado").then(() => setForm({ id: "", name: "", order: 5, perms: {} }));
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="space-y-2">
        {clan.ranks.map((r) => (
          <div key={r.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/30 p-2.5">
            <span className="flex-1 font-bold text-sm">{r.name}</span>
            <span className="text-[10px] text-white/40">{r.id === "leader" ? "Todos los permisos" : Object.values(r.perms || {}).filter(Boolean).length + " permisos"}</span>
            {r.id !== "leader" && <button onClick={() => setForm({ id: r.id, name: r.name, order: r.order, perms: r.perms || {} })} className="text-xs px-2 py-1 rounded border border-white/10">Editar</button>}
            {!["leader", "member"].includes(r.id) && <button data-testid={`del-rank-${r.id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanDeleteRank(r.id)), "Rango eliminado")} className="p-1.5 rounded text-red-300 hover:bg-red-500/10"><Trash2 size={14} /></button>}
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-amber-500/25 bg-black/30 p-4">
        <p className="text-xs font-black uppercase tracking-widest text-amber-400/80 mb-2">{form.id ? "Editar rango" : "Nuevo rango"}</p>
        <input data-testid="rank-name" className={input + " mb-2"} placeholder="Nombre del rango" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="grid grid-cols-2 gap-1.5 mb-3">
          {PERMS.map(([k, label]) => (
            <button key={k} onClick={() => setForm({ ...form, perms: { ...form.perms, [k]: !form.perms[k] } })} className={`text-[11px] px-2 py-1.5 rounded-lg text-left border ${form.perms[k] ? "bg-emerald-500/20 border-emerald-400/40 text-emerald-200" : "bg-white/[0.03] border-white/10 text-white/50"}`}>{form.perms[k] ? <Check size={11} className="inline mr-1" /> : null}{label}</button>
          ))}
        </div>
        <button data-testid="rank-save" onClick={save} className="w-full py-2.5 rounded-lg bg-amber-400 text-black font-black text-sm uppercase flex items-center justify-center gap-1"><Plus size={15} /> {form.id ? "Actualizar" : "Crear rango"}</button>
      </div>
    </div>
  );
}

function InvitePanel() {
  const { act } = useClan();
  const [name, setName] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="block flex-1 min-w-[220px]"><span className="text-xs text-white/50 mb-1 block">Invitar por nombre de jugador</span><input data-testid="invite-input" className={input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Survivor_9945" /></label>
      <button data-testid="invite-submit" onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanInvite({ name })), "Invitación enviada").then(() => setName(""))} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-400 text-black font-black text-sm uppercase"><UserPlus size={16} /> Invitar</button>
    </div>
  );
}

function ClansInner() {
  const { me, loading } = useClan();
  return (
    <div className="relative isolate min-h-screen" data-testid="clan-page">
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <img src={PAGE_BG} alt="" className="w-full h-full object-cover opacity-[0.6]" style={{ objectPosition: "center top" }} />
        {/* Vignette oscuro para mantener legible el HUD, dejando el follaje visible en los bordes */}
        <div className="absolute inset-0" style={{ background: "radial-gradient(115% 75% at 50% 0%, rgba(5,7,10,0.30) 0%, rgba(5,7,10,0.78) 55%, rgba(5,7,10,0.94) 100%)" }} />
        {/* Sombras laterales para enmarcar */}
        <div className="absolute inset-0" style={{ background: "linear-gradient(90deg, rgba(5,7,10,0.55) 0%, transparent 22%, transparent 78%, rgba(5,7,10,0.55) 100%)" }} />
        {/* Brillo verde agresivo superior */}
        <div className="absolute inset-0" style={{ background: "radial-gradient(1200px 500px at 50% -6%, rgba(59,232,84,0.14), transparent 60%)" }} />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#05070a]" />
      </div>
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading ? <div className="h-[520px] rounded-3xl bg-white/[0.03] animate-pulse" /> : (me?.clan ? <Hub /> : <NoClan />)}
      </div>
    </div>
  );
}

export default function Clans() {
  return <ClanProvider><ClansInner /></ClanProvider>;
}
