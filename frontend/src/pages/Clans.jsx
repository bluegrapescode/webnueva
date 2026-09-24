import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, Crown, Users, Send, Swords, Settings2, LogOut, Trash2, UserPlus, Star, Check, X, Plus, ArrowUpRight, Flame, MessageSquare, Globe } from "lucide-react";
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
  const { messages, globalMessages, sendChat } = useClan();
  const [channel, setChannel] = useState("clan");
  const [text, setText] = useState("");
  const endRef = useRef(null);
  const isGlobal = channel === "global";
  const list = isGlobal ? globalMessages : messages;
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [list.length, channel]);
  const send = () => { const t = text.trim(); if (!t) return; sendChat(t, channel); setText(""); };
  const accent = isGlobal ? "#38BDF8" : "#22C55E";

  return (
    <div className="forge-panel rounded-2xl border flex flex-col h-[560px]" style={{ borderColor: `${accent}33` }} data-testid="clan-chat">
      <div className="flex items-center justify-between gap-3 p-4 pb-3 border-b border-white/8 flex-wrap">
        <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest" style={{ color: accent }}>
          {isGlobal ? <Globe size={16} /> : <MessageSquare size={16} />} {isGlobal ? "Chat Global" : "Chat del clan"}
        </h3>
        {/* Switch Clan <-> Global */}
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide select-none">
          <span className={!isGlobal ? "text-emerald-300" : "text-white/35"}>Chat del Clan</span>
          <button type="button" role="switch" aria-checked={isGlobal} data-testid="chat-channel-toggle" onClick={() => setChannel(isGlobal ? "clan" : "global")}
            className="relative w-11 h-6 rounded-full transition-colors duration-200 shrink-0" style={{ background: accent }}>
            <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all duration-200" style={{ left: isGlobal ? 22 : 2 }} />
          </button>
          <span className={isGlobal ? "text-sky-300" : "text-white/35"}>Chat Global (Clanes)</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pt-3 space-y-2.5" data-testid="chat-messages">
        {list.length === 0 && <p className="text-sm text-white/35 text-center py-10">{isGlobal ? "Aún nadie ha escrito en el chat global de clanes. 🌐" : "Sé el primero en escribir. 💬"}</p>}
        {list.map((m) => m.system ? (
          <p key={m.id} className="text-center text-[11px] text-amber-300/70 italic py-1">{m.text}</p>
        ) : (
          <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col">
            <span className="text-[11px] font-bold flex items-center gap-1.5" style={{ color: isGlobal ? "#7dd3fc" : "#86efac" }}>
              {isGlobal && m.clan_tag && <TagBadge tag={m.clan_tag} color={m.clan_color} size="sm" />}
              {m.name}
            </span>
            <span className="text-sm text-white/85 break-words">{m.text}</span>
          </motion.div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="p-3 border-t border-white/8 flex gap-2">
        <input data-testid="chat-input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={isGlobal ? "Mensaje a todos los clanes…" : "Escribe un mensaje…"} className={input} maxLength={500} />
        <button data-testid="chat-send" onClick={send} className="px-4 rounded-lg text-black font-bold" style={{ background: accent }}><Send size={16} /></button>
      </div>
    </div>
  );
}

// ═══════════ Hub del clan ═══════════
function Hub() {
  const { me, act, busy } = useClan();
  const { user } = useAuth();
  const clan = me.clan; const perms = me.my_perms || {}; const isLeader = me.is_leader;
  const [panel, setPanel] = useState(null); // 'settings' | 'ranks' | 'invite'
  const rankName = (id) => (clan.ranks.find((r) => r.id === id) || {}).name || "Miembro";

  return (
    <div className="space-y-6" data-testid="clan-hub">
      {/* header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} data-testid="clan-header"
        className="relative forge-panel rounded-3xl border overflow-hidden p-6" style={{ borderColor: `${clan.color}66`, boxShadow: `0 24px 80px -34px ${clan.color}` }}>
        <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(60% 100% at 100% 0%, ${clan.color}33, transparent 60%)` }} />
        <div className="relative flex flex-wrap items-center gap-4">
          <TagBadge tag={clan.tag} color={clan.color} size="lg" />
          <div className="flex-1 min-w-0">
            <h1 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl leading-none truncate" style={{ color: clan.color }}>{clan.name}</h1>
            <p className="text-sm text-white/55 mt-1">{clan.description || "Sin descripción."}</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-center"><p className="font-mono font-black text-2xl text-white">{clan.member_count}<span className="text-white/40 text-sm">/{clan.min_members}</span></p><p className="text-[10px] uppercase tracking-widest text-white/45">Miembros</p></div>
            <div className="text-center"><p className="font-mono font-black text-2xl text-amber-300">{clan.notoriety}</p><p className="text-[10px] uppercase tracking-widest text-white/45">Notoriedad</p></div>
            {clan.active ? <span className="text-[10px] font-black uppercase px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-400/40">Activo</span> : <span className="text-[10px] font-black uppercase px-2.5 py-1 rounded bg-white/10 text-white/50">Reclutando</span>}
          </div>
        </div>
        <div className="relative flex flex-wrap gap-2 mt-5">
          {perms.edit_clan && <HdrBtn testid="edit-clan-btn" active={panel === "settings"} onClick={() => setPanel(panel === "settings" ? null : "settings")} icon={Settings2}>Ajustes</HdrBtn>}
          {perms.manage_ranks && <HdrBtn testid="manage-ranks-btn" active={panel === "ranks"} onClick={() => setPanel(panel === "ranks" ? null : "ranks")} icon={Star}>Rangos</HdrBtn>}
          {perms.invite && <HdrBtn testid="invite-btn" active={panel === "invite"} onClick={() => setPanel(panel === "invite" ? null : "invite")} icon={UserPlus}>Invitar</HdrBtn>}
          {isLeader
            ? <HdrBtn testid="disband-btn" danger onClick={() => window.confirm("¿Disolver el clan? Esto es permanente.") && act(() => import("@/lib/api").then(({ api }) => api.clanDisband()), "Clan disuelto")} icon={Trash2}>Disolver</HdrBtn>
            : <HdrBtn testid="leave-clan-btn" danger onClick={() => window.confirm("¿Salir del clan?") && act(() => import("@/lib/api").then(({ api }) => api.clanLeave()), "Saliste del clan")} icon={LogOut}>Salir</HdrBtn>}
        </div>
        <AnimatePresence>
          {panel && <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="relative overflow-hidden">
            <div className="mt-4 pt-4 border-t border-white/10">
              {panel === "settings" && <SettingsPanel clan={clan} />}
              {panel === "ranks" && <RanksPanel clan={clan} />}
              {panel === "invite" && <InvitePanel />}
            </div>
          </motion.div>}
        </AnimatePresence>
      </motion.div>

      {/* miembros + chat */}
      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 forge-panel rounded-2xl border border-white/10 p-5">
          <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-white/80 mb-3"><Users size={16} className="text-emerald-400" /> Miembros ({clan.member_count})</h3>
          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
            {(me.members || []).map((m) => (
              <div key={m.user_id} data-testid={`member-row-${m.user_id}`} className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/30 p-2.5">
                <div className="relative h-9 w-9 rounded-full overflow-hidden bg-white/10 shrink-0">{m.avatar && <img src={m.avatar} alt="" className="w-full h-full object-cover" />}<span className={`absolute -bottom-0 -right-0 h-2.5 w-2.5 rounded-full border-2 border-[#0d0f15] ${m.online ? "bg-emerald-400" : "bg-white/25"}`} /></div>
                <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate flex items-center gap-1.5">{m.name}{clan.leader_id === m.user_id && <Crown size={13} className="text-amber-400" />}</p><p className="text-[11px] text-white/45">{rankName(m.rank_id)}</p></div>
                {perms.assign_ranks && clan.leader_id !== m.user_id && (
                  <select data-testid={`assign-${m.user_id}`} value={m.rank_id} onChange={(e) => act(() => import("@/lib/api").then(({ api }) => api.clanAssign(m.user_id, e.target.value)), "Rango asignado")}
                    className="text-xs rounded-lg bg-white/[0.05] border border-white/12 px-2 py-1.5">
                    {clan.ranks.filter((r) => r.id !== "leader").map((r) => <option key={r.id} value={r.id} className="bg-[#0d0f15]">{r.name}</option>)}
                  </select>
                )}
                {isLeader && clan.leader_id !== m.user_id && <button title="Transferir liderazgo" data-testid={`transfer-${m.user_id}`} onClick={() => window.confirm(`¿Transferir liderazgo a ${m.name}?`) && act(() => import("@/lib/api").then(({ api }) => api.clanTransfer(m.user_id)), "Liderazgo transferido")} className="p-1.5 rounded-lg text-amber-300 hover:bg-amber-400/10"><Crown size={15} /></button>}
                {perms.kick && clan.leader_id !== m.user_id && m.user_id !== user?.id && <button data-testid={`kick-${m.user_id}`} onClick={() => act(() => import("@/lib/api").then(({ api }) => api.clanKick(m.user_id)), "Miembro expulsado")} className="p-1.5 rounded-lg text-white/40 hover:text-red-300"><X size={15} /></button>}
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-2"><ClanChat /></div>
      </div>
    </div>
  );
}

function HdrBtn({ children, icon: Icon, onClick, active, danger, testid }) {
  return <button data-testid={testid} onClick={onClick} className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-black uppercase tracking-wide transition ${danger ? "text-red-300 border border-red-400/30 hover:bg-red-500/10" : active ? "bg-amber-400 text-black" : "bg-white/[0.05] text-white/70 hover:text-white border border-white/10"}`}><Icon size={14} /> {children}</button>;
}

function SettingsPanel({ clan }) {
  const { act } = useClan();
  const [f, setF] = useState({ name: clan.name, tag: clan.tag, color: clan.color, description: clan.description });
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Nombre</span><input className={input} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Tag</span><input className={input + " uppercase"} value={f.tag} onChange={(e) => setF({ ...f, tag: e.target.value.toUpperCase().slice(0, 5) })} /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Color</span><input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="h-11 w-16 rounded-lg bg-transparent border border-white/12" /></label>
      <label className="block"><span className="text-xs text-white/50 mb-1 block">Descripción</span><input className={input} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={120} /></label>
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
    <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-8" data-testid="clan-page" style={{ background: "radial-gradient(1200px 460px at 50% -6%, rgba(124,168,66,0.08), transparent 60%)" }}>
      <div className="mb-6">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-emerald-400/90 font-bold flex items-center gap-2"><Shield size={13} /> Hub de clanes · La Isla Nublar</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-none mt-1 flex items-center gap-3"><Swords className="text-emerald-400" size={38} /> <span className="text-gold-clip">Clanes</span></h1>
      </div>
      {loading ? <div className="h-[520px] rounded-3xl bg-white/[0.03] animate-pulse" /> : (me?.clan ? <Hub /> : <NoClan />)}
    </div>
  );
}

export default function Clans() {
  return <ClanProvider><ClansInner /></ClanProvider>;
}
