import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, Crown, Users, Send, Swords, Settings2, LogOut, Trash2, UserPlus, Star, Check, X, Plus, ArrowUpRight, Flame } from "lucide-react";
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

// ═══════════ Sin clan: fundar / invitaciones / directorio ═══════════
function NoClan() {
  const { me, act, busy } = useClan();
  const { play } = useSound();
  const cfg = me?.config || {};
  const [f, setF] = useState({ name: "", tag: "", color: "#22c55e", description: "" });
  const [dir, setDir] = useState([]);
  useEffect(() => { import("@/lib/api").then(({ api }) => api.clanDirectory().then(({ data }) => setDir(data.clans || [])).catch(() => {})); }, [me]);

  const found = () => act(() => import("@/lib/api").then(({ api }) => api.clanFound({ ...f, tag: f.tag.toUpperCase() })), "¡Clan fundado!");

  return (
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

        <div className="forge-panel rounded-2xl border border-amber-500/25 p-6" data-testid="found-form">
          <div className="flex items-center gap-3 mb-1"><Shield className="text-amber-400" size={26} /><h2 className="font-display font-black uppercase tracking-tighter text-2xl sm:text-3xl">Funda tu clan</h2></div>
          <p className="text-sm text-white/55 mb-5">Reúne a tu manada, domina territorios y gana notoriedad en La Isla.</p>
          {!cfg.creation_enabled && <p className="text-red-300 text-sm mb-3">La creación de clanes está deshabilitada temporalmente.</p>}
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="block"><span className="text-xs text-white/50 mb-1 block">Nombre del clan</span><input data-testid="found-name" className={input} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Raptores del Norte" maxLength={28} /></label>
            <label className="block"><span className="text-xs text-white/50 mb-1 block">Tag (2-5, A-Z 0-9)</span><input data-testid="found-tag" className={input + " uppercase font-black tracking-widest"} value={f.tag} onChange={(e) => setF({ ...f, tag: e.target.value.toUpperCase().slice(0, 5) })} placeholder="RN" /></label>
            <label className="block"><span className="text-xs text-white/50 mb-1 block">Color del clan</span>
              <div className="flex items-center gap-2"><input type="color" data-testid="found-color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="h-11 w-14 rounded-lg bg-transparent border border-white/12 cursor-pointer" /><TagBadge tag={f.tag || "TAG"} color={f.color} size="lg" /></div>
            </label>
            <label className="block"><span className="text-xs text-white/50 mb-1 block">Descripción (opcional)</span><input className={input} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={120} /></label>
          </div>
          <div className="flex items-center justify-between mt-5 flex-wrap gap-3">
            <div className="text-sm"><span className="text-white/50">Costo: </span><span className="font-mono font-black text-amber-300">{(cfg.founding_cost ?? 20000).toLocaleString()} {cfg.founding_currency_label || "Amberium"}</span></div>
            <button data-testid="found-submit" disabled={busy || !cfg.creation_enabled || f.name.length < 3 || f.tag.length < 2} onClick={() => { play?.("click"); found(); }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-amber-300 to-amber-500 disabled:opacity-40 hover:brightness-105 transition">
              <Shield size={18} /> Fundar clan
            </button>
          </div>
          <p className="text-[11px] text-white/40 mt-3">Necesitas mínimo {cfg.min_members ?? 20} miembros para activar el clan en Turf Wars.</p>
        </div>
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
  );
}

// ═══════════ Chat en vivo ═══════════
function ClanChat() {
  const { messages, sendChat } = useClan();
  const [text, setText] = useState("");
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  const send = () => { const t = text.trim(); if (!t) return; sendChat(t); setText(""); };
  return (
    <div className="forge-panel rounded-2xl border border-emerald-500/20 flex flex-col h-[560px]" data-testid="clan-chat">
      <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-emerald-300 p-4 pb-2"><Users size={16} /> Chat del clan</h3>
      <div className="flex-1 overflow-y-auto px-4 space-y-2.5" data-testid="chat-messages">
        {messages.length === 0 && <p className="text-sm text-white/35 text-center py-10">Sé el primero en escribir. 💬</p>}
        {messages.map((m) => m.system ? (
          <p key={m.id} className="text-center text-[11px] text-amber-300/70 italic py-1">{m.text}</p>
        ) : (
          <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col">
            <span className="text-[11px] font-bold text-emerald-300/90">{m.name}</span>
            <span className="text-sm text-white/85 break-words">{m.text}</span>
          </motion.div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="p-3 border-t border-white/8 flex gap-2">
        <input data-testid="chat-input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Escribe un mensaje…" className={input} maxLength={500} />
        <button data-testid="chat-send" onClick={send} className="px-4 rounded-lg bg-emerald-400 text-black font-bold"><Send size={16} /></button>
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
