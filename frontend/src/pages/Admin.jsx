import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";


import { motion, AnimatePresence } from "framer-motion";
import { LayoutDashboard, Ticket, Users, Megaphone, Calendar, ShoppingBag, Bone, ScrollText, Plus, Trash2, Coins, Shield, LifeBuoy, Search, Settings, MessageSquare, Zap, Dice5, Crown, Gift, Server, Radio, Save, RefreshCw, Truck, CheckCircle2, Clock, Gauge, Lock, Unlock, Gavel, ShieldAlert, ShieldCheck, Ban, X, Trophy, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { AnimatedCounter } from "@/components/common/AnimatedCounter";
import { CoinChip } from "@/components/common/CoinChip";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { STANDING_STYLE } from "@/lib/standing";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { BansTab } from "@/components/admin/BansTab";
import { CreatorsTab } from "@/components/admin/CreatorsTab";
import { WheelAdminTab } from "@/components/admin/WheelAdminTab";

// Owner-only tabs are drawn beside their neighbour, never as a separate list:
// "Baneos" (website bans, 2026-08-17) sits right after "Sanciones" for owners
// and is absent for every other admin - the API refuses non-owners too.
const OWNER_TABS = [
  { k: "bans", label: "Baneos", icon: Ban, after: "moderation" },
  // Nublar Spin (daily wheel) — owner-only, like its endpoints.
  { k: "wheel", label: "Ruleta", icon: Gift, after: "battlepass" },
];

const TABS = [
  { k: "overview", label: "Resumen", icon: LayoutDashboard },
  { k: "codes", label: "Códigos", icon: Ticket },
  { k: "users", label: "Usuarios", icon: Users },
  { k: "moderation", label: "Sanciones", icon: Gavel },
  { k: "news", label: "Noticias", icon: Megaphone },
  { k: "events", label: "Eventos", icon: Calendar },
  { k: "store", label: "Tienda", icon: ShoppingBag },
  { k: "dinos", label: "Dinosaurios", icon: Bone },
  { k: "population_control", label: "Control de Población", icon: Gauge },
  { k: "recovery", label: "Recuperación", icon: LifeBuoy },
  { k: "multipliers", label: "Multiplicadores", icon: Zap },
  { k: "battlepass", label: "Pase de Batalla", icon: Trophy },
  { k: "creators", label: "Creators", icon: Radio },
  { k: "settings", label: "Ajustes", icon: Settings },
  { k: "logs", label: "Registros", icon: ScrollText },
];

const inputCls = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";
const btnPrimary = "inline-flex items-center justify-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg hover:brightness-110 transition-all text-sm";

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">{label}</span>
      {children}
    </label>
  );
}

export default function Admin() {
  const { user, loading } = useAuth();
  const { play } = useSound();
  const [tab, setTab] = useState("overview");

  if (loading) return null;
  if (!user || user.role !== "admin") {
    return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Solo administradores" sub="Esta área requiere una cuenta de administrador. Usa la cuenta demo para previsualizar." /></div>;
  }

  const visibleTabs = user.is_owner
    ? TABS.flatMap((t) => [t, ...OWNER_TABS.filter((o) => o.after === t.k)])
    : TABS;

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="mb-8 flex items-center gap-3">
        <Shield className="text-gold" size={28} />
        <div>
          <p className="label-overline text-xs text-gold">Control</p>
          <h1 className="font-display font-extrabold text-4xl tracking-tighter">Panel de Admin</h1>
        </div>
      </motion.div>

      <div className="flex flex-col lg:flex-row gap-6">
        <aside className="lg:w-56 shrink-0">
          <div className="glass rounded-2xl p-2 flex lg:flex-col gap-1 overflow-x-auto" data-testid="admin-tabs">
            {visibleTabs.map((t) => (
              <button key={t.k} onClick={() => { setTab(t.k); play("click"); }} onMouseEnter={() => play("hover")} data-testid={`admin-tab-${t.k}`}
                className={`inline-flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all whitespace-nowrap ${tab === t.k ? "bg-gold text-background" : "text-muted-foreground hover:text-foreground hover:bg-white/5"}`}>
                <t.icon size={16} /> {t.label}
              </button>
            ))}
          </div>
        </aside>

        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              {tab === "overview" && <Overview />}
              {tab === "codes" && <CodesTab />}
              {tab === "users" && <UsersTab canGrantSpins={user.is_owner} />}
              {tab === "moderation" && <ModerationTab />}
              {tab === "bans" && user.is_owner && <BansTab />}
              {tab === "news" && <NewsTab />}
              {tab === "events" && <EventsTab />}
              {tab === "store" && <StoreTab />}
              {tab === "dinos" && <DinosTab />}
              {tab === "population_control" && <PopulationControlTab />}
              {tab === "recovery" && <RecoveryTab />}
              {tab === "multipliers" && <MultiplierEventsTab />}
              {tab === "battlepass" && <BattlePassTab />}
              {tab === "wheel" && user.is_owner && <WheelAdminTab />}
              {tab === "creators" && <CreatorsTab />}
              {tab === "settings" && <SettingsTab />}
              {tab === "logs" && <LogsTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.adminStats().then((r) => setStats(r.data)).catch(() => {}); }, []);
  if (!stats) return <p className="text-muted-foreground">Loading…</p>;
  const cards = [
    { label: "Total Users", value: stats.users },
    { label: "Coins in Circulation", value: stats.coins_in_circulation },
    { label: "Amberium in Circulation", value: stats.vip_in_circulation },
    { label: "Transactions", value: stats.transactions },
    { label: "Purchases", value: stats.purchases },
    { label: "Active Codes", value: stats.codes },
    { label: "Code Redemptions", value: stats.code_redemptions },
    { label: "Dinosaurs", value: stats.dinosaurs },
    { label: "Store Items", value: stats.store_items },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4" data-testid="admin-overview">
      {cards.map((c, i) => (
        <motion.div key={c.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
          className="glass rounded-2xl p-6">
          <p className="font-display font-extrabold text-3xl"><AnimatedCounter value={c.value} /></p>
          <p className="label-overline text-[10px] text-muted-foreground mt-1">{c.label}</p>
        </motion.div>
      ))}
    </div>
  );
}

function CodesTab() {
  const { play } = useSound();
  const [codes, setCodes] = useState([]);
  const [form, setForm] = useState({ code: "", name: "", description: "", max_uses: 0, per_user: 1, coins: 0, vip_coins: 0, spins: 0 });
  const load = () => api.adminCodes().then((r) => setCodes(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!form.code || !form.name) { toast.error("Code and name are required"); return; }
    const spins = Number(form.spins);
    if (!Number.isInteger(spins) || spins < 0 || spins > 100) {
      toast.error("Nublar Spins debe ser un número entero entre 0 y 100");
      return;
    }
    try {
      await api.adminCreateCode({
        code: form.code, name: form.name, description: form.description,
        max_uses: Number(form.max_uses), per_user: Number(form.per_user),
        reward: { coins: Number(form.coins), vip_coins: Number(form.vip_coins), spins, items: [], dinos: [], roles: [] },
        active: true,
      });
      play("success"); toast.success("Code created");
      setForm({ code: "", name: "", description: "", max_uses: 0, per_user: 1, coins: 0, vip_coins: 0, spins: 0 });
      load();
    } catch (err) { play("error"); toast.error(err?.response?.data?.detail || "Failed"); }
  };

  const del = async (id) => { await api.adminDeleteCode(id); play("close"); toast.success("Code deleted"); load(); };

  return (
    <div className="space-y-6">
      <form onSubmit={create} className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-4" data-testid="code-create-form">
        <h3 className="font-display font-bold text-lg sm:col-span-2 inline-flex items-center gap-2"><Plus size={18} className="text-gold" /> Create Code</h3>
        <Field label="Código"><input className={inputCls} data-testid="code-input-code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="SUMMER2026" /></Field>
        <Field label="Nombre"><input className={inputCls} data-testid="code-input-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Evento de Verano" /></Field>
        <Field label="Descripción"><input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Usos máx. (0=∞)"><input type="number" className={inputCls} value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} /></Field>
          <Field label="Por usuario"><input type="number" className={inputCls} value={form.per_user} onChange={(e) => setForm({ ...form, per_user: e.target.value })} /></Field>
        </div>
        <Field label="Reward — PrimeMeat"><input type="number" className={inputCls} data-testid="code-input-coins" value={form.coins} onChange={(e) => setForm({ ...form, coins: e.target.value })} /></Field>
        <Field label="Reward — Amberium"><input type="number" className={inputCls} data-testid="code-input-vip" value={form.vip_coins} onChange={(e) => setForm({ ...form, vip_coins: e.target.value })} /></Field>
        <Field label="Reward — Nublar Spins (bonus)"><input type="number" min={0} max={100} step={1} className={inputCls} data-testid="code-input-spins" value={form.spins} onChange={(e) => setForm({ ...form, spins: e.target.value })} /></Field>
        <div className="sm:col-span-2"><button type="submit" className={btnPrimary} data-testid="code-submit"><Plus size={16} /> Create Code</button></div>
      </form>

      <div className="space-y-2" data-testid="codes-list">
        {codes.map((c) => (
          <div key={c.id} className="glass rounded-xl p-4 flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-display font-bold text-lg tracking-wide text-gold">{c.code}</span>
                <span className="text-sm text-muted-foreground">{c.name}</span>
                {!c.active && <span className="text-[10px] label-overline text-crimson">Inactivo</span>}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Uses {c.uses}/{c.max_uses || "∞"} · {c.reward?.coins || 0} PM · {c.reward?.vip_coins || 0} AMB · {c.reward?.spins || 0} SPINS
              </p>
            </div>
            <button onClick={() => del(c.id)} data-testid={`code-delete-${c.id}`} className="p-2 rounded-lg text-crimson hover:bg-crimson/10 transition-colors"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

const RANK_DESC = {
  owner: "Full control over the entire platform — every permission, no restrictions.",
  admin: "Manages economy, users, codes, staff ranks and can moderate chat.",
  mod: "Moderates chat (delete messages, keep order). No economy access.",
  helper: "Assists players and can moderate chat. No economy access.",
  vip: "Cosmetic supporter rank — colored name & badge, no staff powers.",
};

function RankLegend({ ranks }) {
  const entries = Object.entries(ranks || {});
  if (!entries.length) return null;
  return (
    <div className="glass rounded-2xl p-5" data-testid="rank-legend">
      <h3 className="font-display font-bold text-lg inline-flex items-center gap-2 mb-1"><Shield size={18} className="text-gold" /> Staff Rank Legend</h3>
      <p className="text-xs text-muted-foreground mb-4">What each rank means and the color it shows in chat &amp; profiles.</p>
      <div className="grid sm:grid-cols-2 gap-2.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-start gap-3 rounded-xl p-3 border" style={{ background: `${v.color}0d`, borderColor: `${v.color}33` }} data-testid={`rank-legend-${k}`}>
            <span className="text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wider shrink-0 mt-0.5" style={{ color: v.color, background: `${v.color}22`, border: `1px solid ${v.color}55` }}>{v.label}</span>
            <div className="min-w-0">
              <p className="text-xs text-foreground/90 leading-snug">{RANK_DESC[k] || "Custom rank."}</p>
              {Array.isArray(v.perms) && v.perms.length > 0 && (
                <p className="text-[10px] text-muted-foreground mt-1">Permisos: <span className="text-foreground/70">{v.perms.join(", ")}</span></p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function UsersTab({ canGrantSpins = false }) {
  const { play, } = useSound();
  const { user: currentUser, refresh } = useAuth();
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState("");
  const [grant, setGrant] = useState({});
  const [spinGrant, setSpinGrant] = useState({});
  const [ranks, setRanks] = useState({});
  const [wipeTarget, setWipeTarget] = useState(null);
  const [wiping, setWiping] = useState(false);
  const load = () => api.adminUsers({ search: search || undefined }).then((r) => setUsers(r.data)).catch(() => {});
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [search]);
  useEffect(() => { api.staffRanks().then((r) => setRanks(r.data)).catch(() => {}); }, []);

  const doGrant = async (uid, currency) => {
    const amount = Number(grant[uid] || 0);
    if (!amount) { toast.error("Enter an amount"); return; }
    try {
      await api.adminGrant({ user_id: uid, currency, amount, reason: "Admin grant" });
      play("coins"); toast.success(`Granted ${amount} ${currency === "vip" ? "Amberium" : "PrimeMeat"}`);
      setGrant({ ...grant, [uid]: "" }); load(); refresh();
    } catch (e) { play("error"); toast.error("Failed"); }
  };
  const doGrantSpins = async (uid) => {
    const amount = Number(spinGrant[uid]);
    if (!Number.isInteger(amount) || amount < 1 || amount > 100) {
      toast.error("Los giros deben ser un número entero entre 1 y 100");
      return;
    }
    try {
      const r = await api.wheelAdminGrantSpins(uid, amount, "Admin grant");
      play("success");
      toast.success(`Giros bonus: ${r.data.bonus_spins}`);
      setSpinGrant((current) => ({ ...current, [uid]: "" }));
      load();
      if (currentUser?.id === uid) refresh();
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudieron regalar los giros");
    }
  };
  const setRank = async (u, rank) => {
    try { await api.adminSetStaffRank(u.id, rank || null); play("click"); toast.success(rank ? `Rank set to ${ranks[rank]?.label}` : "Rank cleared"); load(); refresh(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Failed"); }
  };
  const doWipe = async () => {
    if (!wipeTarget) return;
    setWiping(true);
    try {
      const r = await api.adminWipeInventory(wipeTarget.id);
      const d = r.data?.deleted || {};
      play("close");
      toast.success(`Inventario de ${wipeTarget.persona_name} borrado: ${d.inventory ?? 0} objetos, ${d.reward_skins ?? 0} skins glitch`);
      setWipeTarget(null);
      load();
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo borrar el inventario");
    } finally {
      setWiping(false);
    }
  };

  return (
    <div className="space-y-4">
      <RankLegend ranks={ranks} />
      <input className={inputCls + " max-w-sm"} placeholder="Buscar usuarios…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="admin-user-search" />
      <div className="space-y-2" data-testid="admin-users-list">
        {users.map((u) => (
          <div key={u.id} className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3">
            <img src={u.avatar} alt="" className="w-10 h-10 rounded-lg object-cover border border-gold/20" />
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm truncate flex items-center gap-1.5">
                {u.persona_name}
                {u.staff_meta && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase" style={{ color: u.staff_meta.color, background: `${u.staff_meta.color}22`, border: `1px solid ${u.staff_meta.color}55` }}>{u.staff_meta.label}</span>}
              </p>
              <p className="text-[10px] text-muted-foreground font-mono truncate select-all" data-testid={`user-steamid-${u.id}`}>{u.steam_id || "—"}</p>
              <div className="flex gap-3 text-xs text-muted-foreground"><CoinChip type="normal" amount={u.coins} size="sm" /><CoinChip type="vip" amount={u.vip_coins} size="sm" /></div>
              {canGrantSpins && <div className="mt-1 inline-flex items-center gap-1 rounded-lg border border-pink-500/40 bg-pink-500/10 px-2 py-1 text-[11px] font-bold text-pink-300" data-testid={`spin-balance-${u.id}`}><Sparkles size={12} /> {u.wheel_bonus_spins || 0} SPINS</div>}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <select value={u.staff_rank || ""} onChange={(e) => setRank(u, e.target.value)} data-testid={`rank-select-${u.id}`}
                className={inputCls + " w-32 cursor-pointer"} style={u.staff_meta ? { color: u.staff_meta.color } : {}}>
                <option value="">Sin rango</option>
                {Object.entries(ranks).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <input type="number" placeholder="Cantidad" className={inputCls + " w-24"} value={grant[u.id] || ""} onChange={(e) => setGrant({ ...grant, [u.id]: e.target.value })} data-testid={`grant-amount-${u.id}`} />
              <button onClick={() => doGrant(u.id, "normal")} data-testid={`grant-normal-${u.id}`} className="text-xs font-semibold glass px-3 py-2.5 rounded-lg hover:border-emerald/40 text-emerald transition-colors"><Coins size={14} /></button>
              <button onClick={() => doGrant(u.id, "vip")} data-testid={`grant-vip-${u.id}`} className="text-xs font-semibold glass px-3 py-2.5 rounded-lg hover:border-gold/40 text-gold transition-colors">VIP</button>
              {canGrantSpins && <>
                <input type="number" min={1} max={100} step={1} placeholder="Spins" className={inputCls + " w-24"} value={spinGrant[u.id] || ""} onChange={(e) => setSpinGrant((current) => ({ ...current, [u.id]: e.target.value }))} data-testid={`grant-spins-amount-${u.id}`} />
                <button onClick={() => doGrantSpins(u.id)} data-testid={`grant-spins-${u.id}`} title="Regalar giros bonus" className="text-xs font-semibold glass px-3 py-2.5 rounded-lg hover:border-pink-400/40 text-pink-300 transition-colors"><Sparkles size={14} /></button>
              </>}
              <button onClick={() => setWipeTarget(u)} data-testid={`wipe-inventory-${u.id}`} title="Borrar inventario"
                className="text-xs font-semibold glass px-3 py-2.5 rounded-lg hover:border-crimson/40 text-crimson transition-colors"><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
      </div>
      <ConfirmModal
        open={!!wipeTarget}
        onClose={() => { if (!wiping) setWipeTarget(null); }}
        onConfirm={doWipe}
        loading={wiping}
        tone="danger"
        title={wipeTarget ? `¿Borrar inventario de ${wipeTarget.persona_name}?` : ""}
        message={wipeTarget ? <>Se eliminarán permanentemente <b>todos los objetos del inventario web</b> (skins, huevos, cajas y dinos del inventario) y <b>todas las skins glitch</b> de {wipeTarget.persona_name}. Las monedas, los dinos de La Bóveda y las publicaciones del Mercado <b>no se tocan</b>.</> : null}
        warning="Esta acción no se puede deshacer"
        confirmLabel="Borrar inventario"
        abortLabel="Cancelar"
      />
    </div>
  );
}

function NewsTab() {
  const { play } = useSound();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: "", body: "", category: "Update", image: "" });
  const load = () => api.news().then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); if (!form.title) return; try { await api.adminCreateNews(form); play("success"); toast.success("News published"); setForm({ title: "", body: "", category: "Update", image: "" }); load(); } catch { play("error"); toast.error("Failed"); } };
  const del = async (id) => { await api.adminDeleteNews(id); play("close"); load(); };
  return (
    <div className="space-y-6">
      <form onSubmit={create} className="glass rounded-2xl p-6 grid gap-4" data-testid="news-create-form">
        <h3 className="font-display font-bold text-lg inline-flex items-center gap-2"><Plus size={18} className="text-gold" /> Publish News</h3>
        <Field label="Título"><input className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="news-title" /></Field>
        <Field label="Categoría"><input className={inputCls} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
        <Field label="Contenido"><textarea className={inputCls} rows={3} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} data-testid="news-body" /></Field>
        <Field label="URL de imagen (opcional)"><input className={inputCls} value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} /></Field>
        <button type="submit" className={btnPrimary} data-testid="news-submit"><Plus size={16} /> Publish</button>
      </form>
      <div className="space-y-2">
        {items.map((n) => (
          <div key={n.id} className="glass rounded-xl p-4 flex items-center gap-3">
            <span className="label-overline text-[10px] text-gold">{n.category}</span>
            <p className="flex-1 font-semibold text-sm truncate">{n.title}</p>
            <button onClick={() => del(n.id)} className="p-2 rounded-lg text-crimson hover:bg-crimson/10"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function EventsTab() {
  const { play } = useSound();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: "", description: "", date_label: "", type: "Community" });
  const load = () => api.events().then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); if (!form.title) return; try { await api.adminCreateEvent(form); play("success"); toast.success("Event created"); setForm({ title: "", description: "", date_label: "", type: "Community" }); load(); } catch { play("error"); toast.error("Failed"); } };
  const del = async (id) => { await api.adminDeleteEvent(id); play("close"); load(); };
  return (
    <div className="space-y-6">
      <form onSubmit={create} className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-4" data-testid="event-create-form">
        <h3 className="font-display font-bold text-lg sm:col-span-2 inline-flex items-center gap-2"><Plus size={18} className="text-gold" /> Create Event</h3>
        <Field label="Título"><input className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="event-title" /></Field>
        <Field label="Tipo"><input className={inputCls} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} /></Field>
        <Field label="Etiqueta de fecha"><input className={inputCls} value={form.date_label} onChange={(e) => setForm({ ...form, date_label: e.target.value })} placeholder="Sat 21:00 UTC" /></Field>
        <Field label="Descripción"><input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="sm:col-span-2"><button type="submit" className={btnPrimary} data-testid="event-submit"><Plus size={16} /> Create</button></div>
      </form>
      <div className="space-y-2">
        {items.map((n) => (
          <div key={n.id} className="glass rounded-xl p-4 flex items-center gap-3">
            <span className="label-overline text-[10px] text-gold">{n.type}</span>
            <p className="flex-1 font-semibold text-sm truncate">{n.title}</p>
            <span className="text-xs text-muted-foreground">{n.date_label}</span>
            <button onClick={() => del(n.id)} className="p-2 rounded-lg text-crimson hover:bg-crimson/10"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function StoreTab() {
  const { play } = useSound();
  const [items, setItems] = useState([]);
  const [edits, setEdits] = useState({});
  const [form, setForm] = useState({ name: "", description: "", category: "Perks", price: 100, currency: "normal", rarity: "Uncommon", image: "" });
  const load = () => api.storeItems().then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); if (!form.name) return; try { await api.adminCreateStore({ ...form, price: Number(form.price), featured: false }); play("success"); toast.success("Item added"); setForm({ name: "", description: "", category: "Perks", price: 100, currency: "normal", rarity: "Uncommon", image: "" }); load(); } catch { play("error"); toast.error("Failed"); } };
  const del = async (id) => { await api.adminDeleteStore(id); play("close"); load(); };
  const savePrice = async (id) => {
    const price = Number(edits[id]);
    if (!price || price <= 0) { toast.error("Enter a valid price"); return; }
    try { await api.adminUpdateStore(id, { price }); play("success"); toast.success("Price updated"); setEdits((p) => ({ ...p, [id]: undefined })); load(); }
    catch { play("error"); toast.error("Failed to update"); }
  };
  return (
    <div className="space-y-6">
      <form onSubmit={create} className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-4" data-testid="store-create-form">
        <h3 className="font-display font-bold text-lg sm:col-span-2 inline-flex items-center gap-2"><Plus size={18} className="text-gold" /> Add Store Item</h3>
        <Field label="Nombre"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="store-name" /></Field>
        <Field label="Categoría"><input className={inputCls} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Precio"><input type="number" className={inputCls} value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} data-testid="store-price" /></Field>
          <Field label="Currency">
            <select className={inputCls} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
              <option value="normal" className="bg-background">Supervivencia</option>
              <option value="vip" className="bg-background">VIP</option>
            </select>
          </Field>
        </div>
        <Field label="Rareza"><input className={inputCls} value={form.rarity} onChange={(e) => setForm({ ...form, rarity: e.target.value })} /></Field>
        <Field label="Descripción"><input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="URL de imagen (opcional)"><input className={inputCls} value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} /></Field>
        <div className="sm:col-span-2"><button type="submit" className={btnPrimary} data-testid="store-submit"><Plus size={16} /> Add Item</button></div>
      </form>
      <div className="space-y-2" data-testid="admin-store-list">
        {items.map((n) => (
          <div key={n.id} className="glass rounded-xl p-4 flex items-center gap-3" data-testid={`admin-store-item-${n.id}`}>
            <img src={n.image} alt="" className="w-10 h-10 rounded-lg object-cover" />
            <div className="flex-1 min-w-0"><p className="font-semibold text-sm truncate">{n.name}</p><span className="text-[10px] label-overline text-muted-foreground">{n.category}</span></div>
            <div className="flex items-center gap-2">
              <div className="flex flex-col items-end">
                <input type="number" value={edits[n.id] ?? n.price}
                  onChange={(e) => setEdits((p) => ({ ...p, [n.id]: e.target.value }))}
                  data-testid={`store-price-input-${n.id}`} className={inputCls + " w-24 text-right"} />
                {n.category === "Dinosaurs" && (
                  <span className="text-[10px] text-gold mt-1 whitespace-nowrap" data-testid={`store-prime-ref-${n.id}`}>
                    Prime: {(Number(edits[n.id] ?? n.price ?? 0) + 1000).toLocaleString()} AMB
                  </span>
                )}
              </div>
              <span className="text-[10px] label-overline text-muted-foreground w-10">{n.currency === "vip" ? "AMB" : "PM"}</span>
              <button onClick={() => savePrice(n.id)} data-testid={`store-save-price-${n.id}`} className="text-xs font-bold bg-gold text-background px-3 py-2.5 rounded-lg hover:brightness-110 transition-all">Guardar</button>
              <button onClick={() => del(n.id)} className="p-2 rounded-lg text-crimson hover:bg-crimson/10"><Trash2 size={16} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DinosTab() {
  const { play } = useSound();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ slug: "", name: "", type: "Carnivore", diet: "Pure Carnivore", rarity: "Uncommon", description: "", speed: 60, health: 60, weight: 1000, damage: 50, growth_time: "2h 00m", abilities: "" });
  const load = () => api.dinosaurs().then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    if (!form.slug || !form.name) { toast.error("Slug and name required"); return; }
    try {
      await api.adminCreateDino({
        ...form, speed: Number(form.speed), health: Number(form.health), weight: Number(form.weight), damage: Number(form.damage),
        abilities: form.abilities.split(",").map((a) => a.trim()).filter(Boolean), featured: false,
      });
      play("success"); toast.success("Dinosaur added");
      setForm({ slug: "", name: "", type: "Carnivore", diet: "Pure Carnivore", rarity: "Uncommon", description: "", speed: 60, health: 60, weight: 1000, damage: 50, growth_time: "2h 00m", abilities: "" });
      load();
    } catch (err) { play("error"); toast.error(err?.response?.data?.detail || "Failed"); }
  };
  const del = async (slug) => { await api.adminDeleteDino(slug); play("close"); load(); };
  return (
    <div className="space-y-6">
      <form onSubmit={create} className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-4" data-testid="dino-create-form">
        <h3 className="font-display font-bold text-lg sm:col-span-2 inline-flex items-center gap-2"><Plus size={18} className="text-gold" /> Add Dinosaur</h3>
        <Field label="Slug"><input className={inputCls} value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase() })} data-testid="dino-slug" /></Field>
        <Field label="Nombre"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="dino-name" /></Field>
        <Field label="Tipo">
          <select className={inputCls} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {["Carnivore", "Herbivore", "Omnivore"].map((t) => <option key={t} value={t} className="bg-background">{t}</option>)}
          </select>
        </Field>
        <Field label="Dieta"><input className={inputCls} value={form.diet} onChange={(e) => setForm({ ...form, diet: e.target.value })} /></Field>
        <Field label="Rareza"><input className={inputCls} value={form.rarity} onChange={(e) => setForm({ ...form, rarity: e.target.value })} /></Field>
        <Field label="Tiempo de crecimiento"><input className={inputCls} value={form.growth_time} onChange={(e) => setForm({ ...form, growth_time: e.target.value })} /></Field>
        <div className="grid grid-cols-4 gap-2 sm:col-span-2">
          <Field label="Velocidad"><input type="number" className={inputCls} value={form.speed} onChange={(e) => setForm({ ...form, speed: e.target.value })} /></Field>
          <Field label="Salud"><input type="number" className={inputCls} value={form.health} onChange={(e) => setForm({ ...form, health: e.target.value })} /></Field>
          <Field label="Peso"><input type="number" className={inputCls} value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></Field>
          <Field label="Daño"><input type="number" className={inputCls} value={form.damage} onChange={(e) => setForm({ ...form, damage: e.target.value })} /></Field>
        </div>
        <Field label="Habilidades (separadas por comas)"><input className={inputCls} value={form.abilities} onChange={(e) => setForm({ ...form, abilities: e.target.value })} /></Field>
        <Field label="Descripción"><input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="sm:col-span-2"><button type="submit" className={btnPrimary} data-testid="dino-submit"><Plus size={16} /> Add Dinosaur</button></div>
      </form>
      <div className="grid sm:grid-cols-2 gap-2">
        {items.map((n) => (
          <div key={n.slug} className="glass rounded-xl p-4 flex items-center gap-3">
            <img src={n.image} alt="" className="w-10 h-10 rounded-lg object-cover" />
            <div className="flex-1 min-w-0"><p className="font-semibold text-sm truncate">{n.name}</p><p className="text-xs text-muted-foreground">{n.type}</p></div>
            <button onClick={() => del(n.slug)} className="p-2 rounded-lg text-crimson hover:bg-crimson/10"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

// How a dino was lost, in words a person reads. The keys are the mod's own
// vocabulary (main.full.lua ClassifyDeathCause) and the backend normalises to
// it, so every cause that can arrive has a line here.
const DEATH_CAUSE = {
  fall: "Caída", drown: "Se ahogó", dehydrate: "Murió de sed",
  starve: "Murió de hambre", bleed: "Desangrado", poison: "Envenenado",
  unknown: "Causa desconocida",
};

const pillCls = "text-[9px] font-bold px-2 py-0.5 rounded-full";

function Pill({ tone, children }) {
  return <span className={`${pillCls} ${tone}`}>{children}</span>;
}

function whenText(ts) {
  if (!ts) return "";
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (mins < 1) return "ahora";
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `hace ${hrs} h`;
  return `hace ${Math.round(hrs / 24)} días`;
}

// How long before the death we last saw the dino. Shown so the admin can judge
// the capture for themselves — it is a label, never a gate.
function ageText(secs) {
  const s = Math.max(0, Math.round(secs));
  if (s < 90) return `${s} s`;
  const mins = Math.round(s / 60);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs} h`;
  return `${Math.round(hrs / 24)} días`;
}

function RecoveryTab() {
  const { play } = useSound();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [partial, setPartial] = useState(null);

  const lookup = async (term) => {
    const q = (term ?? query).trim();
    if (!q) { toast.error("Escribe el SteamID64 del jugador"); return; }
    setLoading(true);
    try {
      const { data } = await api.adminRecoverable(q);
      setResult(data);
      if (!data.player?.steam_id) toast.error(data.message || "Jugador no encontrado");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo cargar el historial");
    } finally { setLoading(false); }
  };

  // A dino whose state we could not recover comes back EMPTY — right species,
  // right size, no mutations, no Prime, no entombs. The backend refuses that
  // with 409 instead of doing it quietly, and this is where the admin decides.
  const recover = async (item, allowPartial = false) => {
    setBusy(true);
    try {
      const { data } = await api.adminRecoverDino({
        steam_id: result.player.steam_id, death_key: item.death_key,
        allow_partial: allowPartial,
      });
      play("success");
      const bits = [`${data.growth}% de crecimiento`];
      bits.push(`${data.mutations_count} ${data.mutations_count === 1 ? "mutación" : "mutaciones"}`);
      if (data.parent_mutations_count > 0) bits.push(`${data.parent_mutations_count} heredadas`);
      if (data.is_prime) bits.push("Prime");
      if (data.elder_stacks > 0) bits.push(`${data.elder_stacks} entombs`);
      if (data.skin_restored) bits.push("skin restaurada");
      toast.success(`${data.dino} devuelto a ${data.owner}`, {
        description: bits.join(" · ")
          + ". Está en su Bóveda: entra al juego como esa especie y pulsa Recuperar.",
      });
      setPartial(null);
      await lookup(result.player.steam_id);
    } catch (e) {
      const body = e?.response?.data?.detail;
      if (e?.response?.status === 409 && body?.code === "partial_requires_confirm") {
        // Not an error — a question. Keep the dino selected and ask.
        setPartial({ item, info: body });
        return;
      }
      play("error");
      toast.error(typeof body === "string" ? body : (body?.message || "No se pudo recuperar"));
    } finally { setBusy(false); setConfirm(null); }
  };

  const player = result?.player;
  const lost = result?.lost || [];

  return (
    <div className="space-y-6" data-testid="recovery-tab">
      <form onSubmit={(e) => { e.preventDefault(); lookup(); }} className="glass rounded-2xl p-6" data-testid="recover-form">
        <h3 className="font-display font-bold text-lg inline-flex items-center gap-2 mb-1">
          <LifeBuoy size={18} className="text-gold" /> Devolver un dino perdido
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          Escribe el SteamID64 del jugador y verás sus últimos {15} dinos perdidos. Pulsa Devolver
          en el que quieras: aparecerá en su Bóveda con su crecimiento, mutaciones y skin, y el
          jugador lo recupera entrando al juego como esa especie.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <input className={inputCls} value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="76561199009325734" data-testid="recover-steamid-input" />
          <button type="submit" disabled={loading} className={btnPrimary} data-testid="recover-lookup">
            <Search size={16} /> {loading ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </form>

      {player?.steam_id && (
        <div className="glass rounded-2xl p-4" data-testid="recovery-player">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="min-w-0">
              <p className="font-semibold text-sm">{player.persona_name || "Jugador sin cuenta web"}</p>
              <p className="font-mono text-[11px] text-muted-foreground select-all">{player.steam_id}</p>
            </div>
            {!player.has_account && (
              <Pill tone="bg-white/10 text-muted-foreground">sin cuenta web</Pill>
            )}
            <span className="text-[11px] text-muted-foreground ml-auto">
              {result.vault_count || 0} en la Bóveda
            </span>
          </div>
        </div>
      )}

      {player?.steam_id && (
        <div className="glass rounded-2xl p-4">
          <h4 className="font-display font-bold text-sm mb-3">Dinos perdidos</h4>
          <div className="space-y-2" data-testid="recovery-records">
            {lost.length === 0 ? (
              <p className="text-muted-foreground py-8 text-center text-sm">
                Este jugador no tiene dinos perdidos registrados.
              </p>
            ) : lost.map((d) => (
              <div key={d.death_key} className="flex flex-wrap items-center gap-3 glass rounded-xl p-3"
                data-testid={`recovery-record-${d.death_key}`}>
                {d.image ? <img src={d.image} alt="" className="w-10 h-10 rounded-lg object-cover" />
                  : <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center"><Bone size={16} className="text-muted-foreground" /></div>}
                <div className="flex-1 min-w-[9rem]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-sm">{d.species}</p>
                    <Pill tone="bg-crimson/15 text-crimson">
                      {DEATH_CAUSE[d.cause] || DEATH_CAUSE.unknown}
                    </Pill>
                    {d.is_prime && <Pill tone="bg-gold/15 text-gold">Prime</Pill>}
                    {d.is_elder && <Pill tone="bg-sky-400/15 text-sky-300">Elder</Pill>}
                    {d.recovered && <Pill tone="bg-emerald/15 text-emerald">Ya devuelto</Pill>}
                    {d.park_unverified && !d.recovered && (
                      <Pill tone="bg-amber-400/15 text-amber-300">¿guardado?</Pill>
                    )}
                    {d.detail === "lkg" && !d.recovered && (
                      <Pill tone="bg-amber-400/15 text-amber-300">estado aproximado</Pill>
                    )}
                    {d.detail === "partial" && !d.recovered && (
                      <Pill tone="bg-white/10 text-muted-foreground">sin estado</Pill>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {d.growth_pct}% de crecimiento
                    {d.detail !== "partial"
                      ? ` · ${d.mutations_count} ${d.mutations_count === 1 ? "mutación" : "mutaciones"}`
                      : " · mutaciones no registradas"}
                    {d.detail !== "partial" && d.prime_missions_done != null
                      ? ` · ${d.prime_missions_done}/10 misiones Prime` : ""}
                    {d.detail !== "partial" && d.elder_stacks > 0
                      ? ` · ${d.elder_stacks} entombs` : ""}
                    {d.ts ? ` · ${whenText(d.ts)}` : ""}
                  </p>
                  {d.detail !== "partial" && d.snapshot_age_s > 0 && (
                    <p className="text-[10px] text-muted-foreground/70">
                      estado guardado {ageText(d.snapshot_age_s)} antes de morir
                    </p>
                  )}
                </div>
                <button onClick={() => setConfirm(d)} disabled={busy || d.recovered}
                  data-testid={`recover-btn-${d.death_key}`}
                  className="shrink-0 ml-auto text-xs font-bold bg-gold text-background px-3 py-2 rounded-lg hover:brightness-110 transition-all disabled:opacity-40">
                  {d.recovered ? "Devuelto" : "Devolver"}
                </button>
              </div>
            ))}
          </div>
          {lost.some((d) => d.detail === "partial") && (
            <p className="text-[11px] text-muted-foreground mt-3">
              <span className="font-semibold">sin estado</span> — de esos dinos no guardamos nada más
              que la especie y el crecimiento, así que volverían sin mutaciones, sin Prime y sin
              entombs. Te lo preguntaremos antes de devolverlos.
            </p>
          )}
          {lost.some((d) => d.detail === "lkg") && (
            <p className="text-[11px] text-amber-300/80 mt-2">
              <span className="font-semibold">estado aproximado</span> — el jugador cambió de
              especie después de la última vez que guardamos su estado, así que las mutaciones
              vienen de la vez anterior que lo vimos con esa especie. Pueden no ser exactas.
            </p>
          )}
          {lost.some((d) => d.park_unverified && !d.recovered) && (
            <p className="text-[11px] text-amber-300/80 mt-2">
              <span className="font-semibold">¿guardado?</span> — de esas fechas no sabemos si el
              dino se perdió o el jugador lo guardó en su Bóveda y ya lo sacó. Compruébalo con él
              antes de devolvérselo.
            </p>
          )}
        </div>
      )}

      <ConfirmModal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm && recover(confirm)}
        title="Devolver este dino"
        confirmLabel="Devolver"
        tone="gold"
        loading={busy}
        message={confirm
          ? `Se añadirá un ${confirm.species} al ${confirm.growth_pct}% a la Bóveda de `
            + `${player?.persona_name || player?.steam_id}`
            + (confirm.detail === "full" && confirm.mutations_count > 0
              ? ` con sus ${confirm.mutations_count} `
                + `${confirm.mutations_count === 1 ? "mutación" : "mutaciones"}`
                + (confirm.is_prime ? " y su estado Prime" : "")
              : "")
            + ". Solo se puede devolver una vez."
          : ""}
      />

      {/* The bare-grant question. This used to happen silently: the dino came
          back empty and nobody found out until the player said so. */}
      <ConfirmModal
        open={!!partial}
        onClose={() => setPartial(null)}
        onConfirm={() => partial && recover(partial.item, true)}
        title="No guardamos el estado de este dino"
        confirmLabel="Devolver igualmente"
        tone="gold"
        loading={busy}
        message={partial
          ? `${partial.info?.message || ""} Volvería como un ${partial.info?.dino || ""} `
            + `al ${partial.info?.growth_pct ?? ""}% y nada más.`
          : ""}
      />
    </div>
  );
}


// ── Moderation / Sanciones ────────────────────────────────────────────────
// Penalty escalation (distinct from account-standing STATUS colours in @/lib/standing):
// a clear severity gradient emerald -> amber -> orange -> deep-orange -> crimson.
const STRIKE_POLICY = [
  { n: 1, title: "Aviso + Expulsión", sub: "Expulsado del servidor", color: "#34d399", Icon: ShieldAlert },
  { n: 2, title: "Ban de 1 hora", sub: "Expulsión + baneo", color: "#eab308", Icon: Clock },
  { n: 3, title: "Ban de 24 horas", sub: "Baneo de un día", color: "#f59e0b", Icon: Clock },
  { n: 4, title: "Ban de 7 días", sub: "Baneo de una semana", color: "#f97316", Icon: Ban },
  { n: 5, title: "Ban permanente", sub: "Expulsión definitiva", color: "#ef4444", Icon: Gavel },
];

const REASONS = ["Trampas / Cheating", "Comportamiento tóxico", "Combat logging", "Metagaming", "Acoso", "Spam en el chat", "Exploits"];

const nextConsequence = (nextCount) => STRIKE_POLICY[Math.min(Math.max(nextCount, 1), 5) - 1];

function fmtUntil(iso) {
  if (!iso) return null;
  try {
    const diff = new Date(iso) - new Date();
    if (diff <= 0) return null;
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h restantes`;
    if (h >= 1) return `${h}h ${m}m restantes`;
    return `${m}m restantes`;
  } catch { return null; }
}

function strikeToast(standing, enf) {
  const n = standing?.active_strikes ?? 0;
  // A tier-2+ strike whose durable game ban didn't write must NOT read as a mild "aviso";
  // the enforcer self-heals it within a few minutes.
  if (enf.action === "ban" && !enf.banned) {
    return `Strike #${n} registrado — el ban se aplicará en el juego en breve`;
  }
  let tail;
  if (enf.banned) {
    if (enf.ban_permanent) tail = "baneado permanentemente";
    else if (enf.ban_hours >= 24) tail = `baneado por ${enf.ban_hours / 24} día${enf.ban_hours / 24 > 1 ? "s" : ""}`;
    else tail = `baneado por ${enf.ban_hours} hora${enf.ban_hours > 1 ? "s" : ""}`;
  } else {
    // The kick is dispatched to the mod lane and verified async (RCON acks lie) — don't
    // claim a completed removal, say it's in flight / queued for their return.
    tail = enf.online ? "expulsión enviada al juego" : "aviso registrado";
  }
  let msg = `Strike #${n} — ${tail}`;
  if (!enf.online) msg += " · se aplicará al reconectar";
  return msg;
}

function StatusPill({ status, label }) {
  const s = STANDING_STYLE[status] || STANDING_STYLE.good;
  const I = s.Icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1 rounded-full" data-testid="mod-status-pill"
      style={{ color: s.c, background: `${s.c}18`, border: `1px solid ${s.c}44` }}>
      <I size={12} /> {label || s.label}
    </span>
  );
}

function OnlineDot({ online }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold" style={{ color: online ? "#34d399" : "#6b7280" }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: online ? "#34d399" : "#6b7280", boxShadow: online ? "0 0 6px #34d399" : "none" }} />
      {online ? "En servidor" : "Desconectado"}
    </span>
  );
}

function StrikePips({ count }) {
  return (
    <span className="inline-flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className="w-1.5 h-4 rounded-full" style={{ background: i <= count ? STRIKE_POLICY[i - 1].color : "rgba(255,255,255,0.12)" }} />
      ))}
    </span>
  );
}

function ModUserRow({ u, flagged, onManage }) {
  const { play } = useSound();
  const until = fmtUntil(u.banned_until);
  return (
    <div className="flex items-center gap-3 glass rounded-xl p-3" data-testid={`mod-user-${u.id}`}>
      <img src={u.avatar} alt="" className="w-9 h-9 rounded-lg object-cover border border-white/10" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold text-sm truncate">{u.persona_name}</p>
          {u.staff_meta && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase" style={{ color: u.staff_meta.color, background: `${u.staff_meta.color}22` }}>{u.staff_meta.label}</span>}
          {flagged && <StatusPill status={u.status} />}
        </div>
        {flagged ? (
          <div className="flex items-center gap-2.5 mt-1 flex-wrap">
            <StrikePips count={u.active_strikes} />
            <span className="text-[10px] text-muted-foreground">{u.active_strikes} strike{u.active_strikes !== 1 ? "s" : ""}{u.ban_permanent ? " · permanente" : until ? ` · ${until}` : ""}</span>
            <OnlineDot online={u.online} />
          </div>
        ) : (
          <p className="text-[10px] text-muted-foreground font-mono truncate">{u.steam_id || "—"}</p>
        )}
      </div>
      <button onClick={() => { onManage(); play("click"); }} onMouseEnter={() => play("hover")} data-testid={`mod-manage-${u.id}`}
        className="text-xs font-bold px-3 py-2 rounded-lg glass border border-gold/30 text-gold hover:bg-gold/10 transition-all whitespace-nowrap inline-flex items-center gap-1.5">
        <Gavel size={13} /> Gestionar
      </button>
    </div>
  );
}

function UserManageModal({ userId, onClose, onChanged }) {
  const { play } = useSound();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState("");

  const load = () => api.adminUserStanding(userId)
    .then((r) => { setData(r.data); setErr(false); })
    .catch(() => { setErr(true); toast.error("No se pudo cargar el usuario"); });
  useEffect(() => {
    load();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const s = data?.standing;
  const activeCount = s?.active_strikes ?? 0;
  const cons = nextConsequence(activeCount + 1);
  const ConsIcon = cons.Icon;
  const online = data?.online;
  const strikes = data?.strikes || [];

  const issue = async () => {
    const r = reason.trim();
    if (!r) { toast.error("Indica un motivo para el strike"); play("error"); return; }
    setBusy("issue");
    try {
      const { data: res } = await api.adminAddStrike(userId, { reason: r });
      play("success");
      toast.success(strikeToast(res.standing, res.enforcement || {}));
      setReason("");
      await load(); onChanged?.();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo emitir el strike"); }
    finally { setBusy(""); }
  };

  const removeStrike = async (sid) => {
    setBusy("rm-" + sid);
    try { await api.adminRemoveStrike(sid); play("click"); toast.success("Strike retirado"); await load(); onChanged?.(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo retirar"); }
    finally { setBusy(""); }
  };

  const unban = async () => {
    setBusy("unban");
    try {
      const { data } = await api.adminUnban(userId);
      play("success");
      toast.success(data?.native_removed === false
        ? "Sanciones levantadas — quitando el ban del juego (en curso)…"
        : "Sanciones levantadas — ban retirado del juego");
      await load(); onChanged?.();
    }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo levantar"); }
    finally { setBusy(""); }
  };

  return createPortal(
    <AnimatePresence>
      <motion.div className="fixed inset-0 z-[120] flex items-center justify-center p-4"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} data-testid="mod-manage-modal">
        <div className="absolute inset-0 bg-black/75 backdrop-blur-md" />
        <motion.div className="relative w-full max-w-lg bg-[#0c0c0e] border border-white/10 rounded-2xl overflow-hidden max-h-[88vh] flex flex-col"
          initial={{ scale: 0.94, y: 14, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }} exit={{ scale: 0.94, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 26 }}>
          {!data ? (
            <div className="p-8 text-center" data-testid="mod-modal-loadstate">
              <p className="text-sm text-muted-foreground mb-4">{err ? "No se pudo cargar el usuario." : "Cargando…"}</p>
              <button onClick={onClose} data-testid="mod-modal-close" className="text-xs font-semibold px-4 py-2 rounded-lg glass border border-white/10 text-foreground hover:bg-white/5">Cerrar</button>
            </div>
          ) : (
            <>
              <div className="p-5 border-b border-white/10 flex items-center gap-3">
                <img src={data.user.avatar} alt="" className="w-11 h-11 rounded-lg object-cover border border-white/10" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-display font-bold text-lg truncate">{data.user.persona_name}</p>
                    {data.user.staff_meta && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase" style={{ color: data.user.staff_meta.color, background: `${data.user.staff_meta.color}22` }}>{data.user.staff_meta.label}</span>}
                  </div>
                  <div className="flex items-center gap-2.5 mt-1 flex-wrap"><StatusPill status={s.status} /><OnlineDot online={online} /></div>
                </div>
                <button onClick={onClose} className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/5" data-testid="mod-modal-close"><X size={18} /></button>
              </div>

              <div className="p-5 space-y-5 overflow-y-auto">
                <div className="rounded-xl p-4 flex items-center gap-3" style={{ background: `${cons.color}12`, border: `1px solid ${cons.color}40` }} data-testid="mod-consequence">
                  <div className="w-11 h-11 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${cons.color}1f`, color: cons.color }}><ConsIcon size={22} /></div>
                  <div className="min-w-0">
                    <p className="label-overline text-[10px] text-muted-foreground">Próximo strike · #{activeCount + 1}</p>
                    <p className="font-display font-bold text-base" style={{ color: cons.color }}>{cons.title}</p>
                    <p className="text-[11px] text-muted-foreground">{online ? "El jugador será expulsado del servidor ahora." : "El jugador está desconectado — se aplicará al reconectar."}</p>
                  </div>
                </div>

                <div>
                  <p className="label-overline text-[10px] text-muted-foreground mb-2">Motivo</p>
                  <div className="flex flex-wrap gap-1.5 mb-2.5">
                    {REASONS.map((rr) => (
                      <button key={rr} onClick={() => setReason(rr)} data-testid={`mod-reason-chip-${rr}`}
                        className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${reason === rr ? "bg-gold text-background border-gold" : "glass text-muted-foreground border-white/10 hover:text-foreground"}`}>{rr}</button>
                    ))}
                  </div>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={200} placeholder="Describe la razón de la sanción…" data-testid="mod-reason-input" className={inputCls} />
                </div>

                <button onClick={issue} disabled={busy === "issue"} data-testid="mod-issue-strike"
                  className="w-full inline-flex items-center justify-center gap-2 font-bold px-4 py-3 rounded-xl transition-all disabled:opacity-50 hover:brightness-110"
                  style={{ background: "rgba(226,74,74,0.14)", border: "1px solid #E24A4A", color: "#E24A4A" }}>
                  <Gavel size={16} /> {busy === "issue" ? "Emitiendo…" : `Emitir strike #${activeCount + 1}`}
                </button>

                <div>
                  <p className="label-overline text-[10px] text-muted-foreground mb-2">Historial ({activeCount} activo{activeCount !== 1 ? "s" : ""})</p>
                  <div className="space-y-1.5">
                    {strikes.length === 0 && <p className="text-xs text-muted-foreground/70 py-3 text-center">Sin strikes registrados.</p>}
                    {strikes.map((x) => (
                      <div key={x.id} className={`flex items-center gap-2.5 rounded-lg p-2.5 text-xs ${x.active ? "bg-white/[0.04] border border-white/[0.07]" : "bg-white/[0.015] opacity-60"}`} data-testid={`mod-strike-${x.id}`}>
                        <span className="w-1.5 h-6 rounded-full shrink-0" style={{ background: x.active ? "#ef4444" : "#4b5563" }} />
                        <div className="min-w-0 flex-1">
                          <p className={`font-semibold truncate ${x.active ? "" : "line-through"}`}>{x.reason}</p>
                          <p className="text-[10px] text-muted-foreground truncate">{x.issued_by || "—"} · {x.created_at ? new Date(x.created_at).toLocaleString() : ""}{!x.active && x.removed_by ? ` · retirado por ${x.removed_by}` : ""}</p>
                        </div>
                        {x.active && <button onClick={() => removeStrike(x.id)} disabled={busy === "rm-" + x.id} className="p-1.5 rounded-md text-muted-foreground hover:text-crimson hover:bg-crimson/10" data-testid={`mod-remove-strike-${x.id}`}><X size={14} /></button>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {(s.banned || activeCount > 0) && (
                <div className="p-4 border-t border-white/10">
                  <button onClick={unban} disabled={busy === "unban"} data-testid="mod-unban"
                    className="w-full inline-flex items-center justify-center gap-2 text-sm font-bold px-4 py-2.5 rounded-xl glass border border-emerald/30 text-emerald hover:bg-emerald/10 transition-all disabled:opacity-50">
                    <ShieldCheck size={16} /> {busy === "unban" ? "Levantando…" : "Levantar todas las sanciones (unban)"}
                  </button>
                </div>
              )}
            </>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}

function ModerationTab() {
  const [overview, setOverview] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState(null);
  const [manageId, setManageId] = useState(null);

  const load = () => api.adminModeration()
    .then((r) => { setOverview(r.data); setLoadError(false); })
    .catch(() => { setLoadError(true); setOverview((p) => p || { server: { online: false }, flagged: [] }); });
  const runSearch = () => {
    const q = search.trim();
    if (!q) { setResults(null); return; }
    api.adminUsers({ search: q }).then((r) => setResults(r.data)).catch(() => {});
  };
  // After a strike/unban, refresh BOTH the flagged overview and the current search list
  // so a search-opened row doesn't show stale standing.
  const refreshAll = () => { load(); runSearch(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!search.trim()) { setResults(null); return; }
    const t = setTimeout(runSearch, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const server = overview?.server;
  const flagged = overview?.flagged || [];

  return (
    <div className="space-y-6" data-testid="moderation-tab">
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-1"><Gavel size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">Escalación de sanciones</h3></div>
        <p className="text-sm text-muted-foreground mb-4">Cada strike aumenta la penalización. Las expulsiones y baneos se aplican al servidor de juego en tiempo real.</p>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5" data-testid="strike-ladder">
          {STRIKE_POLICY.map((p) => {
            const I = p.Icon;
            return (
              <div key={p.n} className="rounded-xl p-3.5 border" style={{ background: `${p.color}0d`, borderColor: `${p.color}33` }} data-testid={`ladder-rung-${p.n}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-7 h-7 rounded-lg flex items-center justify-center font-display font-extrabold text-sm" style={{ background: `${p.color}1f`, color: p.color }}>{p.n}</span>
                  <I size={15} style={{ color: p.color }} />
                </div>
                <p className="font-bold text-sm leading-tight" style={{ color: p.color }}>{p.title}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{p.sub}</p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="glass rounded-2xl p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
          <div className="flex items-center gap-2">
            <Server size={16} className="text-gold" />
            <span className="text-sm font-bold">Servidor</span>
            {server ? (
              <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${server.online ? "text-emerald" : "text-crimson"}`} data-testid="mod-server-status">
                <span className={`w-1.5 h-1.5 rounded-full ${server.online ? "bg-emerald" : "bg-crimson"}`} />
                {server.online ? `En línea · ${server.players}/${server.max_players}` : "Sin conexión"}
              </span>
            ) : <span className="text-xs text-muted-foreground">…</span>}
          </div>
          <button onClick={load} className="p-1.5 rounded-lg glass text-muted-foreground hover:text-foreground" data-testid="mod-refresh"><RefreshCw size={14} /></button>
        </div>
        <div className="flex items-center gap-2 glass rounded-lg px-3">
          <Search size={15} className="text-muted-foreground" />
          <input className="flex-1 bg-transparent py-2.5 text-sm focus:outline-none" placeholder="Buscar jugador por nombre o Steam ID para sancionar…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="mod-search" />
        </div>
        {results && (
          <div className="mt-3 space-y-1.5" data-testid="mod-search-results">
            {results.length === 0 ? <p className="text-xs text-muted-foreground py-3 text-center">Sin resultados.</p>
              : results.slice(0, 12).map((u) => <ModUserRow key={u.id} u={u} onManage={() => setManageId(u.id)} />)}
          </div>
        )}
      </div>

      <div className="glass rounded-2xl p-5">
        <h4 className="font-display font-bold text-lg mb-3 inline-flex items-center gap-2"><ShieldAlert size={16} className="text-gold" /> Jugadores sancionados ({flagged.length})</h4>
        <div className="space-y-1.5" data-testid="mod-flagged-list">
          {!overview ? <p className="text-sm text-muted-foreground py-6 text-center">Cargando…</p>
            : loadError ? <p className="text-sm text-crimson py-6 text-center">No se pudo cargar la lista de sancionados. Reintenta — no confirmes un unban desde esta vista.</p>
            : flagged.length === 0 ? <p className="text-sm text-muted-foreground py-6 text-center">Nadie tiene sanciones activas. Busca un jugador arriba para emitir un strike.</p>
            : flagged.map((f) => <ModUserRow key={f.id} u={f} flagged onManage={() => setManageId(f.id)} />)}
        </div>
      </div>

      {manageId && <UserManageModal userId={manageId} onClose={() => setManageId(null)} onChanged={refreshAll} />}
    </div>
  );
}

function LogsTab() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.adminLogs().then((r) => setLogs(r.data)).catch(() => {}); }, []);
  return (
    <div className="glass rounded-2xl p-4 space-y-1.5 max-h-[600px] overflow-y-auto" data-testid="admin-logs">
      {logs.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no hay actividad registrada.</p>
        : logs.map((l) => (
          <div key={l.id} className="flex items-center gap-3 text-sm glass rounded-lg p-3">
            <span className="label-overline text-[10px] text-gold w-32 shrink-0 truncate">{l.action}</span>
            <span className="flex-1 truncate text-muted-foreground"><b className="text-foreground">{l.actor}</b> → {l.target || "—"}</span>
            <span className="text-xs text-muted-foreground shrink-0">{new Date(l.created_at).toLocaleString()}</span>
          </div>
        ))}
    </div>
  );
}

function PopSwitch({ on, onClick, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} role="switch" aria-checked={on}
      className="relative w-10 h-[22px] rounded-full transition-all shrink-0 border cursor-pointer"
      style={{
        background: on ? "#7CA842" : "rgba(255,255,255,0.10)",
        borderColor: on ? "#A3C96B" : "rgba(255,255,255,0.18)",
        boxShadow: on ? "0 0 8px rgba(124,168,66,0.5)" : "none",
      }}>
      <span className="absolute top-1/2 rounded-full bg-white transition-all duration-200"
        style={{ height: 16, width: 16, left: on ? 21 : 2, transform: "translateY(-50%)", boxShadow: "0 1px 2px rgba(0,0,0,0.55)" }} />
    </button>
  );
}

function PopulationControlTab() {
  const { play } = useSound();
  const [data, setData] = useState(undefined); // undefined=loading, null=load error
  const [edits, setEdits] = useState({}); // species name -> { cap, locked }
  const [auto, setAuto] = useState(false);
  const [saving, setSaving] = useState(false);
  const [audit, setAudit] = useState([]);

  const load = () => api.adminPopState().then((r) => {
    setData(r.data);
    setAuto(!!r.data?.auto);
    setEdits({});
  }).catch(() => setData((p) => (p === undefined ? null : p)));

  const loadAudit = () => api.adminPopAudit().then((r) => setAudit(Array.isArray(r.data) ? r.data : (r.data?.items || []))).catch(() => {});

  useEffect(() => { load(); loadAudit(); }, []);

  // backend species keys are raw blueprint classes (e.g. "BP_Tyrannosaurus_C");
  // key edits/API calls by the raw value, display the bare species name.
  const prettySpecies = (s) => String(s || "").replace(/^BP_/, "").replace(/_C$/, "").replace(/_/g, " ");
  const species = data?.species || [];
  const capOf = (sp) => edits[sp.species]?.cap ?? sp.cap;
  const lockedOf = (sp) => edits[sp.species]?.locked ?? sp.locked;
  const setCap = (name, v) => setEdits((p) => ({ ...p, [name]: { ...p[name], cap: v } }));
  const toggleLocked = (name, current) => setEdits((p) => ({ ...p, [name]: { ...p[name], locked: !current } }));
  const dirty = Object.keys(edits).length > 0;

  const save = async () => {
    setSaving(true);
    const prevData = data;
    // optimistic UI: reflect the edits immediately, revert if the server rejects them
    setData((d) => ({ ...d, species: species.map((sp) => ({ ...sp, cap: Number(capOf(sp)), locked: lockedOf(sp) })), auto }));
    try {
      // only send dirty entries — backend applies changes/lock/unlock as deltas, not full snapshots
      const changes = []; const lock = []; const unlock = [];
      Object.entries(edits).forEach(([name, e]) => {
        const sp = species.find((s) => s.species === name);
        if (!sp) return;
        if (e.cap !== undefined && Number(e.cap) !== sp.cap) changes.push({ species: name, cap: Number(e.cap) });
        if (e.locked !== undefined && e.locked !== sp.locked) { if (e.locked) lock.push(name); else unlock.push(name); }
      });
      await api.adminPopApply({ changes, lock, unlock, auto, reason: "Panel de administración web" });
      play("success");
      toast.success("Control de población actualizado");
      setEdits({});
      loadAudit();
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo guardar");
      setData(prevData);
    } finally { setSaving(false); }
  };

  if (data === undefined) return <div className="glass rounded-2xl p-8 text-center text-muted-foreground text-sm">Cargando control de población…</div>;
  if (data === null) return <div className="glass rounded-2xl p-8 text-center text-muted-foreground text-sm" data-testid="population-control-error">No se pudo cargar el control de población. Reintenta más tarde.</div>;

  return (
    <div className="space-y-6" data-testid="population-control-tab">
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-2"><Gauge size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">Control de Población</h3></div>
          <label className="inline-flex items-center gap-2.5 cursor-pointer" data-testid="pop-control-auto-toggle">
            <span className="text-sm font-semibold">Aplicación automática</span>
            <PopSwitch on={auto} onClick={() => setAuto((v) => !v)} testid="pop-control-auto-switch" />
          </label>
        </div>
        <p className="text-sm text-muted-foreground mb-4">Ajusta el límite de población por especie y bloquea o abre especies para todo el servidor. Los cambios se aplican al presionar Guardar.</p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[560px]" data-testid="population-control-table">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-white/10">
                <th className="py-2 pr-3">Especie</th>
                <th className="py-2 pr-3">Límite</th>
                <th className="py-2 pr-3">Vivos</th>
                <th className="py-2 pr-3">Estado</th>
              </tr>
            </thead>
            <tbody>
              {species.map((sp) => {
                const cap = capOf(sp);
                const locked = lockedOf(sp);
                return (
                  <tr key={sp.species} className="border-b border-white/5" data-testid={`pop-control-row-${sp.species}`}>
                    <td className="py-2 pr-3 font-semibold">{prettySpecies(sp.species)}</td>
                    <td className="py-2 pr-3">
                      <input type="number" min="0" max="1000" value={cap} onChange={(e) => setCap(sp.species, e.target.value)}
                        data-testid={`pop-control-cap-${sp.species}`} className="w-24 bg-white/[0.05] border border-white/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-gold/40" />
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{sp.count ?? 0}</td>
                    <td className="py-2 pr-3">
                      <button type="button" onClick={() => toggleLocked(sp.species, locked)} data-testid={`pop-control-lock-${sp.species}`}
                        className={`inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1 rounded-full border transition-all ${locked ? "bg-crimson/15 text-crimson border-crimson/30" : "bg-emerald/15 text-emerald border-emerald/30"}`}>
                        {locked ? <><Lock size={11} /> Bloqueada</> : <><Unlock size={11} /> Abierta</>}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {species.length === 0 && (
                <tr><td colSpan={4} className="py-6 text-center text-muted-foreground">No hay especies configuradas.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center gap-3 mt-5">
          <button onClick={save} disabled={saving || species.length === 0} data-testid="population-control-save" className={btnPrimary}>
            {saving ? "Guardando…" : "Guardar"}
          </button>
          {dirty && !saving && <span className="text-[11px] text-gold">Cambios sin guardar</span>}
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <h4 className="font-display font-bold text-lg mb-3 inline-flex items-center gap-2"><ScrollText size={16} className="text-gold" /> Historial de Cambios</h4>
        <div className="space-y-1.5 max-h-[360px] overflow-y-auto" data-testid="population-control-audit">
          {audit.length === 0 ? <p className="text-muted-foreground py-6 text-center text-sm">Aún no hay cambios registrados.</p>
            : audit.map((a, i) => (
              <div key={a.id ?? i} className="flex items-center gap-3 text-sm glass rounded-lg p-3">
                <span className="text-xs text-muted-foreground shrink-0">{(a.fecha || a.date || a.created_at) ? new Date(a.fecha || a.date || a.created_at).toLocaleString() : "—"}</span>
                <span className="font-semibold shrink-0">{a.actor || "—"}</span>
                <span className="flex-1 truncate text-muted-foreground">{[a.action, prettySpecies(a.species)].filter(Boolean).join(" · ") || a.reason || "—"}{a.reason && (a.action || a.species) ? ` — ${a.reason}` : ""}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function SettingsTab() {
  const { play } = useSound();
  const { user } = useAuth();
  const [cooldown, setCooldown] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.adminGetSettings().then((r) => setCooldown(String(r.data.chat_cooldown_seconds ?? 0)))
      .catch(() => {}).finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const val = Math.max(0, Math.min(300, parseInt(cooldown || "0", 10)));
      const r = await api.adminUpdateSettings({ chat_cooldown_seconds: val });
      setCooldown(String(r.data.chat_cooldown_seconds));
      play("success");
      toast.success("Ajustes guardados", { description: `Cooldown de chat: ${r.data.chat_cooldown_seconds}s` });
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo guardar"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="glass rounded-2xl p-8 text-center text-muted-foreground text-sm">Cargando ajustes…</div>;

  return (
    <div className="glass rounded-2xl p-6 max-w-lg" data-testid="admin-settings">
      <div className="flex items-center gap-2 mb-1"><MessageSquare size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">Ajustes de Chat</h3></div>
      <p className="text-sm text-muted-foreground mb-5">Tiempo mínimo (en segundos) que un jugador debe esperar entre mensajes en el chat global. Usa 0 para desactivar el modo lento.</p>
      <Field label="Cooldown entre mensajes (segundos)">
        <div className="flex gap-3">
          <input type="number" min="0" max="300" value={cooldown} onChange={(e) => setCooldown(e.target.value)} data-testid="settings-chat-cooldown"
            className={inputCls} />
          <button onClick={save} disabled={saving} data-testid="settings-save" className={btnPrimary}>{saving ? "Guardando…" : "Guardar"}</button>
        </div>
      </Field>
      <div className="mt-4 flex gap-2 flex-wrap">
        {[0, 3, 5, 10, 30].map((s) => (
          <button key={s} onClick={() => setCooldown(String(s))} data-testid={`settings-preset-${s}`}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg glass text-muted-foreground hover:text-foreground transition-all">{s}s</button>
        ))}
      </div>
      <div className="mt-8"><GiftScheduleEditor /></div>
      {user?.is_owner && <div className="mt-8"><RconPanel /></div>}
      {user?.is_owner && <div className="mt-8"><RollChancesEditor /></div>}
    </div>
  );
}

function RconPanel() {
  const { play } = useSound();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [players, setPlayers] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

  const refresh = async () => {
    setLoading(true);
    try { const r = await api.adminRconStatus(); setStatus(r.data); }
    catch { setStatus({ configured: true, online: false }); }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const loadPlayers = async () => {
    setBusy("players");
    try { const r = await api.adminRconPlayers(); setPlayers(r.data.players); play("click"); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
    finally { setBusy(""); }
  };
  const announce = async () => {
    const m = msg.trim(); if (!m) return;
    setBusy("announce");
    try { await api.adminRconAnnounce(m); setMsg(""); play("success"); toast.success("Anuncio enviado al servidor"); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
    finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("save");
    try { await api.adminRconSave(); play("success"); toast.success("Servidor guardado (save)"); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "Error"); }
    finally { setBusy(""); }
  };

  const on = status?.online;
  return (
    <div className="border-t border-white/10 pt-6" data-testid="admin-rcon-panel">
      <div className="flex items-center gap-2 mb-1">
        <Server size={18} className="text-gold" />
        <h3 className="font-display font-bold text-xl">Servidor RCON (Evrima)</h3>
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-crimson/15 text-crimson border border-crimson/30"><Crown size={10} /> Solo Dueño</span>
        <button onClick={refresh} data-testid="rcon-refresh" className="ml-auto p-1.5 rounded-lg glass text-muted-foreground hover:text-foreground"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
      </div>
      <p className="text-sm text-muted-foreground mb-4">Conexión en vivo con el servidor de juego. Datos reales de población, lista de jugadores y anuncios in-game.</p>

      <div className="grid sm:grid-cols-2 gap-3 mb-4" data-testid="rcon-status">
        <div className={`glass rounded-xl p-4 border ${on ? "border-emerald/30" : "border-crimson/30"}`}>
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${on ? "bg-emerald animate-pulse" : "bg-crimson"}`} />
            <span className={`text-sm font-bold ${on ? "text-emerald" : "text-crimson"}`}>{loading ? "Conectando…" : on ? "En línea" : "Sin conexión"}</span>
          </div>
          {on ? (
            <>
              <p className="font-display font-bold text-base truncate" data-testid="rcon-server-name">{status.name}</p>
              <p className="text-xs text-muted-foreground">Mapa {status.map} · <b className="text-gold">{status.players}/{status.max_players}</b> jugadores</p>
              <div className="flex gap-2 mt-2 flex-wrap text-[10px]">
                <span className={`px-2 py-0.5 rounded ${status.mutations ? "bg-emerald/15 text-emerald" : "bg-white/5 text-muted-foreground"}`}>Mutaciones {status.mutations ? "ON" : "OFF"}</span>
                <span className={`px-2 py-0.5 rounded ${status.humans ? "bg-emerald/15 text-emerald" : "bg-white/5 text-muted-foreground"}`}>Humanos {status.humans ? "ON" : "OFF"}</span>
                <span className={`px-2 py-0.5 rounded ${status.ai ? "bg-emerald/15 text-emerald" : "bg-white/5 text-muted-foreground"}`}>IA {status.ai ? "ON" : "OFF"}</span>
              </div>
            </>
          ) : <p className="text-xs text-muted-foreground">{status?.error || "No se pudo conectar al RCON."}</p>}
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-bold inline-flex items-center gap-1.5"><Users size={14} className="text-gold" /> Jugadores en juego</span>
            <button onClick={loadPlayers} disabled={busy === "players"} data-testid="rcon-players-btn" className="text-[11px] font-semibold px-2.5 py-1 rounded-lg glass text-muted-foreground hover:text-foreground">{busy === "players" ? "…" : "Cargar"}</button>
          </div>
          {players == null ? <p className="text-xs text-muted-foreground/60">Toca "Cargar" para ver la lista.</p>
            : players.length === 0 ? <p className="text-xs text-muted-foreground/60">Nadie conectado ahora mismo.</p>
            : <div className="space-y-1 max-h-32 overflow-y-auto">{players.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-xs"><span className="truncate">{p.name}</span><span className="text-muted-foreground/50 font-mono text-[10px]">{p.steam_id || ""}</span></div>
              ))}</div>}
        </div>
      </div>

      <Field label="Anuncio in-game (se muestra a todos los jugadores)">
        <div className="flex gap-2">
          <input value={msg} maxLength={240} onChange={(e) => setMsg(e.target.value)} data-testid="rcon-announce-input" placeholder="Ej: ¡Evento Triple Verde en la web ahora!" className={inputCls} />
          <button onClick={announce} disabled={busy === "announce" || !msg.trim()} data-testid="rcon-announce-btn" className={btnPrimary}><Radio size={14} /> {busy === "announce" ? "…" : "Anunciar"}</button>
        </div>
      </Field>
      <div className="mt-3">
        <button onClick={save} disabled={busy === "save"} data-testid="rcon-save-btn" className="inline-flex items-center gap-2 text-xs font-semibold px-3 py-2.5 rounded-lg glass text-muted-foreground hover:text-foreground transition-all"><Save size={14} /> {busy === "save" ? "Guardando…" : "Guardar mundo (Save)"}</button>
      </div>
    </div>
  );
}

function RollChancesEditor() {
  const { play } = useSound();
  const [ch, setCh] = useState(null);
  const [mult, setMult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.adminGetRollConfig().then((r) => { setCh(r.data.chances); setMult(r.data.mult); })
      .catch(() => {}).finally(() => setLoading(false));
  }, []);

  const total = ch ? (Number(ch.green) || 0) + (Number(ch.red) || 0) + (Number(ch.black) || 0) : 0;
  const pct = (k) => (total > 0 ? ((Number(ch[k]) || 0) / total) * 100 : 0);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.adminUpdateRollConfig({ green: Number(ch.green) || 0, red: Number(ch.red) || 0, black: Number(ch.black) || 0 });
      setCh(r.data.chances);
      play("success");
      toast.success("Chances del dado actualizados", { description: `🟢 ${r.data.chances.green}% · 🔴 ${r.data.chances.red}% · ⚫ ${r.data.chances.black}%` });
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo guardar"); }
    finally { setSaving(false); }
  };

  const reset = () => setCh({ green: 6.67, red: 46.665, black: 46.665 });

  if (loading) return <div className="glass rounded-2xl p-6 text-center text-muted-foreground text-sm">Cargando config del dado…</div>;
  if (!ch) return null;

  const ROWS = [
    { k: "green", label: "Verde (0)", color: "#10B981" },
    { k: "red", label: "Rojo (1-7)", color: "#F32C2C" },
    { k: "black", label: "Negro (8-14)", color: "#8a8a9a" },
  ];

  return (
    <div className="border-t border-white/10 pt-6" data-testid="admin-roll-chances">
      <div className="flex items-center gap-2 mb-1">
        <Dice5 size={18} className="text-gold" />
        <h3 className="font-display font-bold text-xl">Chances del Dado (Roll)</h3>
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-crimson/15 text-crimson border border-crimson/30"><Crown size={10} /> Solo Dueño</span>
      </div>
      <p className="text-sm text-muted-foreground mb-5">Ajusta la probabilidad de cada color en la ruleta. Los valores se normalizan automáticamente para sumar 100%. El multiplicador de pago se muestra como referencia.</p>
      <div className="space-y-3">
        {ROWS.map((r) => (
          <div key={r.k} className="flex items-center gap-3">
            <span className="w-28 shrink-0 inline-flex items-center gap-2 text-sm font-bold">
              <span className="w-3 h-3 rounded-full" style={{ background: r.color }} />{r.label}
            </span>
            <input type="number" step="0.01" min="0" value={ch[r.k]} onChange={(e) => setCh((c) => ({ ...c, [r.k]: e.target.value }))}
              data-testid={`roll-chance-${r.k}`} className={inputCls + " max-w-[120px]"} />
            <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
              <div className="h-full rounded-full transition-all" style={{ width: `${pct(r.k)}%`, background: r.color }} />
            </div>
            <span className="w-24 text-right text-sm tabular-nums font-bold" style={{ color: r.color }}>{pct(r.k).toFixed(2)}%</span>
            <span className="w-12 text-right text-[11px] text-muted-foreground">×{mult?.[r.k]}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 flex items-center gap-3">
        <button onClick={save} disabled={saving || total <= 0} data-testid="roll-chances-save" className={btnPrimary}>{saving ? "Guardando…" : "Guardar chances"}</button>
        <button onClick={reset} data-testid="roll-chances-reset" className="text-xs font-semibold px-3 py-2.5 rounded-lg glass text-muted-foreground hover:text-foreground transition-all">Restaurar por defecto</button>
        <span className="text-[11px] text-muted-foreground ml-auto">Suma actual: <b className={total > 0 ? "text-foreground" : "text-crimson"}>{total.toFixed(2)}</b></span>
      </div>
    </div>
  );
}

const EGG_LABEL = { common: "Común", uncommon: "Poco Común", rare: "Raro", epic: "Épico", legendary: "Legendario" };

function GiftScheduleEditor() {
  const { play } = useSound();
  const [rows, setRows] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.adminGetGift().then((r) => { setRows(r.data.schedule); setTiers(r.data.egg_tiers || []); }).catch(() => {});
  }, []);

  const upd = (day, key, val) => setRows((rs) => rs.map((r) => (r.day === day ? { ...r, [key]: val } : r)));

  const save = async () => {
    setSaving(true);
    try {
      const payload = rows.map((r) => ({
        day: r.day, coins: parseInt(r.coins || 0, 10), vip: parseInt(r.vip || 0, 10),
        xp: parseInt(r.xp || 0, 10), special: r.special || null,
      }));
      const res = await api.adminSaveGift(payload);
      setRows(res.data.schedule); play("success");
      toast.success("Recompensas de racha guardadas");
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo guardar"); }
    finally { setSaving(false); }
  };

  if (!rows) return <div className="glass rounded-2xl p-6 text-center text-muted-foreground text-sm">Cargando recompensas…</div>;

  return (
    <div className="glass rounded-2xl p-6" data-testid="admin-gift-editor">
      <div className="flex items-center gap-2 mb-1"><Gift size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">Recompensas de Racha (Login diario)</h3></div>
      <p className="text-sm text-muted-foreground mb-5">Edita lo que gana el jugador cada día de su racha de 7 días. El huevo se entrega además de las monedas/XP de ese día.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[560px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-white/10">
              <th className="py-2 pr-3">Día</th>
              <th className="py-2 pr-3">PrimeMeat 🥩</th>
              <th className="py-2 pr-3">Amberium 🟠</th>
              <th className="py-2 pr-3">XP</th>
              <th className="py-2 pr-3">Huevo</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.day} className="border-b border-white/5" data-testid={`gift-row-${r.day}`}>
                <td className="py-2 pr-3 font-bold text-gold">{r.day}</td>
                <td className="py-2 pr-3"><input type="number" min="0" value={r.coins} onChange={(e) => upd(r.day, "coins", e.target.value)} data-testid={`gift-coins-${r.day}`} className="w-24 bg-white/[0.05] border border-white/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-gold/40" /></td>
                <td className="py-2 pr-3"><input type="number" min="0" value={r.vip} onChange={(e) => upd(r.day, "vip", e.target.value)} data-testid={`gift-vip-${r.day}`} className="w-20 bg-white/[0.05] border border-white/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-gold/40" /></td>
                <td className="py-2 pr-3"><input type="number" min="0" value={r.xp} onChange={(e) => upd(r.day, "xp", e.target.value)} data-testid={`gift-xp-${r.day}`} className="w-20 bg-white/[0.05] border border-white/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-gold/40" /></td>
                <td className="py-2 pr-3">
                  <select value={r.special || ""} onChange={(e) => upd(r.day, "special", e.target.value || null)} data-testid={`gift-egg-${r.day}`}
                    className="bg-white/[0.05] border border-white/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-gold/40">
                    <option value="">Ninguno</option>
                    {tiers.map((t) => <option key={t.tier} value={t.tier}>Huevo {EGG_LABEL[t.tier] || t.tier}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={save} disabled={saving} data-testid="gift-save" className={`${btnPrimary} mt-5`}>{saving ? "Guardando…" : "Guardar recompensas"}</button>
    </div>
  );
}


const EVENT_STATUS_STYLE = {
  upcoming: { label: "Programado", cls: "text-sky-300 border-sky-400/40 bg-sky-400/10" },
  active: { label: "Activo", cls: "text-emerald-300 border-emerald-400/40 bg-emerald-400/10" },
  over: { label: "Terminado", cls: "text-muted-foreground border-white/15 bg-white/[0.04]" },
};

function fmtHours(h) {
  h = parseInt(h || 0, 10);
  if (h % 168 === 0 && h >= 168) { const w = h / 168; return w === 1 ? "1 semana" : `${w} semanas`; }
  if (h % 24 === 0 && h >= 24) { const d = h / 24; return d === 1 ? "1 día" : `${d} días`; }
  return h === 1 ? "1 hora" : `${h} horas`;
}

function fmtLeft(s) {
  s = Math.max(0, parseInt(s || 0, 10));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

const EMPTY_MULT_FORM = { species: "", durationPreset: "24", durationCustom: 24, multiplier: 30 };

function MultiplierEventsTab() {
  const { play } = useSound();
  const [events, setEvents] = useState([]);
  const [meta, setMeta] = useState({ species: [], duration_presets: [6, 12, 24, 48, 72, 168, 336],
    max_hours: 720, defaults: { duration_hours: 24, multiplier: 30 },
    multiplier_min: 2, multiplier_max: 1000, base_reward: 350, interval_seconds: 240, announce_available: false });
  const [form, setForm] = useState(EMPTY_MULT_FORM);
  const [saving, setSaving] = useState(false);
  const [busyRow, setBusyRow] = useState(null);

  const load = () => api.adminListMultiplierEvents().then((r) => {
    setEvents(r.data.events || []);
    setMeta((m) => ({ ...m, ...r.data, defaults: r.data.defaults || m.defaults }));
    setForm((f) => ({ ...f, multiplier: f.multiplier || r.data.defaults?.multiplier || 30 }));
  }).catch(() => {});
  useEffect(() => { load(); }, []);

  const durationH = parseInt(form.durationPreset === "custom" ? form.durationCustom : form.durationPreset, 10) || 24;
  const mult = parseInt(form.multiplier, 10) || 0;
  const perCycle = (meta.base_reward || 350) * (mult || 1);
  const intervalMin = Math.round((meta.interval_seconds || 240) / 60);

  const create = async () => {
    if (!form.species) { toast.error("Elige una especie"); return; }
    setSaving(true);
    try {
      await api.adminCreateMultiplierEvent({ species: form.species, duration_hours: durationH, multiplier: mult });
      play("success"); toast.success(`Evento publicado: Día de ${form.species} x${mult}`);
      setForm({ ...EMPTY_MULT_FORM, multiplier: meta.defaults?.multiplier || 30 });
      load();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo crear"); }
    finally { setSaving(false); }
  };

  const endNow = async (ev) => {
    setBusyRow(ev.id);
    try { await api.adminEndMultiplierEvent(ev.id); play("close"); toast.success(`Evento finalizado: ${ev.title}`); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo finalizar"); }
    finally { setBusyRow(null); }
  };

  const del = async (ev) => {
    setBusyRow(ev.id);
    try { await api.adminDeleteMultiplierEvent(ev.id); play("close"); toast.success("Evento eliminado"); load(); }
    catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo eliminar"); }
    finally { setBusyRow(null); }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6" data-testid="admin-multipliers">
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-1"><Zap size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">Crear Evento Multiplicador</h3></div>
        <p className="text-xs text-muted-foreground mb-4">
          Mientras el evento esté activo, todo el PrimeMeat que un jugador gane jugando como la
          especie elegida se multiplica por el valor del evento. Termina solo al vencer la duración.
        </p>
        <div className="space-y-3">
          <Field label="Especie">
            <select value={form.species} onChange={(e) => setForm({ ...form, species: e.target.value })} data-testid="mult-species" className={inputCls}>
              <option value="">Elige una especie…</option>
              {(meta.species || []).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Duración">
              <select value={form.durationPreset} onChange={(e) => setForm({ ...form, durationPreset: e.target.value })} data-testid="mult-duration" className={inputCls}>
                {(meta.duration_presets || []).map((h) => <option key={h} value={String(h)}>{fmtHours(h)}</option>)}
                <option value="custom">Personalizada…</option>
              </select>
            </Field>
            <Field label={`Multiplicador (x${meta.multiplier_min ?? 2} – x${meta.multiplier_max ?? 1000})`}>
              <input type="number" min={meta.multiplier_min ?? 2} max={meta.multiplier_max ?? 1000} value={form.multiplier}
                onChange={(e) => setForm({ ...form, multiplier: e.target.value })} data-testid="mult-value" className={inputCls} />
            </Field>
          </div>
          {form.durationPreset === "custom" && (
            <Field label={`Duración (horas, máx ${meta.max_hours})`}>
              <input type="number" min="1" max={meta.max_hours} value={form.durationCustom}
                onChange={(e) => setForm({ ...form, durationCustom: e.target.value })} data-testid="mult-duration-custom" className={inputCls} />
            </Field>
          )}
          {form.species && mult > 1 && (
            <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.04] p-3 text-sm" data-testid="mult-preview">
              <p className="font-semibold text-emerald-300">Día de {form.species} — x{mult} PrimeMeat</p>
              <p className="text-[11px] text-muted-foreground mt-1">
                Jugando como {form.species}: ~{perCycle.toLocaleString()} PrimeMeat cada {intervalMin} min
                (normal: {(meta.base_reward || 350).toLocaleString()}) durante {fmtHours(durationH)}.
              </p>
            </div>
          )}
          <button onClick={create} disabled={saving} data-testid="mult-create" className={btnPrimary}>
            <Plus size={15} /> {saving ? "Publicando…" : "Publicar Evento"}
          </button>
          {!meta.announce_available && <p className="text-[11px] text-muted-foreground">Para anunciar los eventos en Discord, configura el canal de eventos en el servidor web.</p>}
        </div>
      </div>

      <div className="glass rounded-2xl p-6">
        <h3 className="font-display font-bold text-xl mb-4">Eventos ({events.length})</h3>
        <div className="space-y-2 max-h-[720px] overflow-y-auto">
          {events.length === 0 && <p className="text-sm text-muted-foreground py-6 text-center">Aún no hay eventos. Publica el primero con el formulario.</p>}
          {events.map((ev) => {
            const st = ev.event?.status || "over";
            const stStyle = EVENT_STATUS_STYLE[st] || EVENT_STATUS_STYLE.over;
            return (
              <div key={ev.id} data-testid={`admin-mult-${ev.id}`} className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-sm truncate">
                    {ev.title}
                    <span className="ml-2 align-middle text-[11px] font-bold text-emerald-300">x{ev.multiplier}</span>
                    <span className={`ml-2 align-middle inline-flex items-center text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded border ${stStyle.cls}`}>{stStyle.label.toUpperCase()}</span>
                  </p>
                  <p className="text-[11px] text-muted-foreground truncate">
                    {ev.species} · x{ev.multiplier} PrimeMeat
                    {st === "active" && ` · termina en ${fmtLeft(ev.event?.ends_in)}`}
                    {st === "upcoming" && ` · comienza en ${fmtLeft(ev.event?.starts_in)}`}
                  </p>
                </div>
                {st === "active" && (
                  <button onClick={() => endNow(ev)} disabled={busyRow === ev.id} data-testid={`mult-end-${ev.id}`}
                    className="px-2.5 py-1.5 rounded-lg text-[11px] font-bold text-gold border border-gold/40 hover:bg-gold/10 transition-colors whitespace-nowrap">
                    {busyRow === ev.id ? "…" : "Finalizar"}
                  </button>
                )}
                <button onClick={() => del(ev)} disabled={busyRow === ev.id} data-testid={`mult-delete-${ev.id}`} className="p-2 rounded-lg text-crimson hover:bg-crimson/10 transition-colors"><Trash2 size={15} /></button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


// ── Pase de Batalla ───────────────────────────────────────────────────────
const BP_TIER_LABEL = { free: "Gratis", regular: "Regular", premium_plus: "Premium+" };
const BP_SOURCE_LABEL = { purchase: "Compra", stripe: "Compra", gift: "Regalo", patreon: "Patreon", upgrade: "Mejora" };
const BP_STATUS_STYLE = {
  paid: { label: "Pagado", cls: "text-emerald-300 border-emerald-400/40 bg-emerald-400/10" },
  pending: { label: "Pendiente", cls: "text-amber-300 border-amber-400/40 bg-amber-400/10" },
  expired: { label: "Expirado", cls: "text-muted-foreground border-white/15 bg-white/[0.04]" },
  refunded: { label: "Reembolsado", cls: "text-crimson border-crimson/30 bg-crimson/10" },
  revoked: { label: "Revocado", cls: "text-crimson border-crimson/30 bg-crimson/10" },
};

// Same gold the pass page uses (components/battlepass/RewardCard GOLD), inlined
// so this tab does not pull the whole pass bundle in for one colour.
const BP_GOLD = "#EAB308";

// The season code ("S08") is derived the same way the backend derives it, so the
// preview below never has to guess at what will be saved.
function bpSeasonCode(id) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(id || ""));
  if (!m) return "S--";
  const n = (Number(m[1]) - 2026) * 12 + Number(m[2]);
  return `S${String(n).padStart(2, "0")}`;
}

// Mirror of the server's sanitizer: control characters out, whitespace runs
// collapsed, hard length cap.
export function bpCleanSeasonName(raw, max = 48) {
  return String(raw ?? "")
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, " ")
    .split(/\s+/).filter(Boolean).join(" ")
    .slice(0, max).trim();
}

export function bpPreviewSeasonName(id, raw, verbatim, fallback, max = 48) {
  const name = bpCleanSeasonName(raw, max);
  if (!name) return fallback || "—";
  if (verbatim) return name;
  const y = /^(\d{4})-\d{2}$/.exec(String(id || ""));
  return y ? `${bpSeasonCode(id)} · ${name} ${y[1]}` : name;
}

function SeasonNameCard({ ov, onSaved }) {
  const { play } = useSound();
  const seasonId = ov.season?.id || ov.season_id || "";
  const max = Number(ov.season_name_max) || 48;
  const fallback = ov.season_name_default || ov.season?.name || "—";
  const [text, setText] = useState(ov.season_name_text || "");
  const [verbatim, setVerbatim] = useState(!!ov.season_name_verbatim);
  const [busy, setBusy] = useState(false);

  // A reload (or another admin's save) is the source of truth for the box.
  useEffect(() => {
    setText(ov.season_name_text || "");
    setVerbatim(!!ov.season_name_verbatim);
  }, [ov.season_name_text, ov.season_name_verbatim, seasonId]);

  const clean = bpCleanSeasonName(text, max);
  const preview = bpPreviewSeasonName(seasonId, text, verbatim, fallback, max);
  const dirty = clean !== (ov.season_name_text || "") || verbatim !== !!ov.season_name_verbatim;

  const save = async (nextText, nextVerbatim) => {
    setBusy(true);
    try {
      const r = await api.bpAdminSeasonName({
        season: seasonId, name: nextText, verbatim: !!nextVerbatim,
      });
      play("success");
      toast.success(r.data?.custom ? `Temporada renombrada: ${r.data.name}` : "Nombre por defecto restaurado");
      onSaved();
    } catch (err) {
      play("error");
      toast.error(err?.response?.data?.detail || "No se pudo cambiar el nombre");
    } finally { setBusy(false); }
  };

  return (
    <div className="glass rounded-2xl p-6 space-y-4" data-testid="bp-admin-season-name">
      <div>
        <h3 className="font-display font-bold text-lg inline-flex items-center gap-2">
          <Trophy size={18} className="text-gold" /> Nombre de la temporada
        </h3>
        <p className="text-sm text-muted-foreground mt-1">
          Así se llama el pase en la página. Déjalo vacío para volver al nombre por defecto.
        </p>
      </div>

      <Field label={`Nombre (máximo ${max} caracteres)`}>
        <input
          className={inputCls}
          data-testid="bp-admin-season-name-input"
          value={text}
          maxLength={max}
          onChange={(e) => setText(e.target.value)}
          placeholder={ov.season_name_default || "Cacería Bajo el Sol"}
        />
      </Field>

      {/* A bare <input type=checkbox> renders as a white box on this dark theme,
          so this is the site's own switch shape. */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={verbatim}
          data-testid="bp-admin-season-name-verbatim"
          onClick={() => setVerbatim((v) => !v)}
          className="relative w-10 h-[22px] rounded-full transition-all shrink-0 border cursor-pointer"
          style={{
            background: verbatim ? BP_GOLD : "rgba(255,255,255,0.10)",
            borderColor: verbatim ? BP_GOLD : "rgba(255,255,255,0.18)",
            boxShadow: verbatim ? `0 0 8px ${BP_GOLD}88` : "none",
          }}
        >
          <span
            className="absolute top-1/2 rounded-full bg-white transition-all duration-200"
            style={{ height: 16, width: 16, left: verbatim ? 21 : 2, transform: "translateY(-50%)",
                     boxShadow: "0 1px 2px rgba(0,0,0,0.55)" }}
          />
        </button>
        <span className="text-sm text-muted-foreground">
          Usar exactamente este texto (sin “{bpSeasonCode(seasonId)} ·” ni el año)
        </span>
      </div>

      <div className="rounded-lg border border-gold/25 bg-gold/[0.06] px-4 py-3">
        <p className="label-overline text-[10px] text-gold">Se verá así</p>
        <p className="font-display font-extrabold text-xl mt-1 break-words"
           data-testid="bp-admin-season-name-preview">{preview}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={btnPrimary}
          disabled={busy || !dirty}
          data-testid="bp-admin-season-name-save"
          onClick={() => save(clean, verbatim)}
        >
          <Save size={16} /> Guardar nombre
        </button>
        {ov.season_name_custom && (
          <button
            type="button"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            disabled={busy}
            data-testid="bp-admin-season-name-reset"
            onClick={() => save("", false)}
          >
            Restaurar el nombre por defecto
          </button>
        )}
      </div>
    </div>
  );
}

function bpDaysLeft(iso) {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return null;
  return Math.max(0, Math.ceil(ms / 86400000));
}

function BattlePassTab() {
  const { play } = useSound();
  const [ov, setOv] = useState(null);
  const [failed, setFailed] = useState(false);
  const [gift, setGift] = useState({ user: "", tier: "regular", note: "" });
  const [xp, setXp] = useState({ user: "", amount: 1000 });
  const [busy, setBusy] = useState(null);
  const [confirmSettle, setConfirmSettle] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    api.bpAdminOverview().then((r) => setOv(r.data)).catch(() => setFailed(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const sendGift = async (e) => {
    e.preventDefault();
    if (!gift.user.trim()) { toast.error("Escribe el Steam ID, el Discord o el nombre del jugador"); return; }
    setBusy("gift");
    try {
      await api.bpAdminGift({ user: gift.user.trim(), tier: gift.tier, note: gift.note.trim() });
      play("success");
      toast.success(`Pase ${BP_TIER_LABEL[gift.tier]} regalado`);
      setGift({ user: "", tier: "regular", note: "" });
      load();
    } catch (err) { play("error"); toast.error(err?.response?.data?.detail || "No se pudo regalar el pase"); }
    finally { setBusy(null); }
  };

  const sendXp = async (e) => {
    e.preventDefault();
    const amount = parseInt(xp.amount || 0, 10);
    if (!xp.user.trim()) { toast.error("Escribe el Steam ID, el Discord o el nombre del jugador"); return; }
    if (!amount) { toast.error("La cantidad de XP no puede ser 0"); return; }
    setBusy("xp");
    try {
      await api.bpAdminGrantXp({ user: xp.user.trim(), amount });
      play("success");
      toast.success(`${amount.toLocaleString()} XP otorgados`);
      setXp({ user: "", amount: 1000 });
      load();
    } catch (err) { play("error"); toast.error(err?.response?.data?.detail || "No se pudo otorgar el XP"); }
    finally { setBusy(null); }
  };

  const settle = async () => {
    setBusy("settle");
    try {
      const r = await api.bpAdminSettle({});
      play("success");
      const n = r.data?.settled ?? r.data?.count;
      toast.success(n != null ? `Temporada cerrada · ${n} pases liquidados` : "Temporada cerrada");
      setConfirmSettle(false);
      load();
    } catch (err) { play("error"); toast.error(err?.response?.data?.detail || "No se pudo cerrar la temporada"); }
    finally { setBusy(null); }
  };

  if (failed) {
    return (
      <div className="glass rounded-2xl p-10 text-center" data-testid="bp-admin-error">
        <p className="text-sm text-muted-foreground">No pudimos cargar los datos del pase.</p>
        <button onClick={load} className={`${btnPrimary} mt-4`} data-testid="bp-admin-retry">Reintentar</button>
      </div>
    );
  }
  if (!ov) return <p className="text-muted-foreground">Cargando…</p>;

  const buyers = ov.buyers || {};
  const days = bpDaysLeft(ov.season?.ends_at);
  const cards = [
    { label: "Compradores Regular", value: buyers.regular || 0 },
    { label: "Compradores Premium+", value: buyers.premium_plus || 0 },
    { label: "Pases regalados", value: buyers.gift || 0 },
    { label: "Recompensas reclamadas", value: ov.claims_count || 0 },
  ];

  return (
    <div className="space-y-6" data-testid="admin-battlepass">
      {/* season + revenue */}
      <div className="glass rounded-2xl p-6 flex flex-wrap items-center justify-between gap-4" data-testid="bp-admin-season">
        <div>
          <p className="label-overline text-[10px] text-gold">Temporada actual</p>
          <h3 className="font-display font-extrabold text-2xl">{ov.season?.name || "—"}</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {ov.season?.id ? `${ov.season.id} · ` : ""}
            {days != null ? (days === 1 ? "queda 1 día" : `quedan ${days} días`) : "sin fecha de cierre"}
          </p>
        </div>
        <div className="text-right">
          <p className="font-display font-extrabold text-3xl text-emerald" data-testid="bp-admin-revenue">
            ${((ov.revenue_cents || 0) / 100).toFixed(2)}
          </p>
          <p className="label-overline text-[10px] text-muted-foreground mt-1">Ingresos de la temporada</p>
        </div>
      </div>

      <SeasonNameCard ov={ov} onSaved={load} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="bp-admin-cards">
        {cards.map((c) => (
          <div key={c.label} className="glass rounded-2xl p-5">
            <p className="font-display font-extrabold text-3xl"><AnimatedCounter value={c.value} /></p>
            <p className="label-overline text-[10px] text-muted-foreground mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* gift */}
        <form onSubmit={sendGift} className="glass rounded-2xl p-6 space-y-4" data-testid="bp-admin-gift-form">
          <h3 className="font-display font-bold text-lg inline-flex items-center gap-2"><Gift size={18} className="text-gold" /> Regalar un pase</h3>
          <Field label="Jugador (Steam ID, Discord o nombre)">
            <input className={inputCls} data-testid="bp-admin-gift-user" value={gift.user}
              onChange={(e) => setGift({ ...gift, user: e.target.value })} placeholder="76561198… / usuario#0001 / Nombre" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Tipo de pase">
              <select className={inputCls} data-testid="bp-admin-gift-tier" value={gift.tier}
                onChange={(e) => setGift({ ...gift, tier: e.target.value })}>
                <option value="regular">Pase Regular</option>
                <option value="premium_plus">Pase Premium+</option>
              </select>
            </Field>
            <Field label="Nota (opcional)">
              <input className={inputCls} data-testid="bp-admin-gift-note" value={gift.note}
                onChange={(e) => setGift({ ...gift, note: e.target.value })} placeholder="Motivo" />
            </Field>
          </div>
          <button type="submit" disabled={busy === "gift"} className={btnPrimary} data-testid="bp-admin-gift">
            <Gift size={16} /> {busy === "gift" ? "Regalando…" : "Regalar pase"}
          </button>
        </form>

        {/* xp */}
        <form onSubmit={sendXp} className="glass rounded-2xl p-6 space-y-4" data-testid="bp-admin-xp-form">
          <h3 className="font-display font-bold text-lg inline-flex items-center gap-2"><Zap size={18} className="text-gold" /> Otorgar XP del pase</h3>
          <Field label="Jugador (Steam ID, Discord o nombre)">
            <input className={inputCls} data-testid="bp-admin-xp-user" value={xp.user}
              onChange={(e) => setXp({ ...xp, user: e.target.value })} placeholder="76561198… / usuario#0001 / Nombre" />
          </Field>
          <Field label="XP a sumar">
            <input type="number" className={inputCls} data-testid="bp-admin-xp-amount" value={xp.amount}
              onChange={(e) => setXp({ ...xp, amount: e.target.value })} />
          </Field>
          <button type="submit" disabled={busy === "xp"} className={btnPrimary} data-testid="bp-admin-grant-xp">
            <Zap size={16} /> {busy === "xp" ? "Otorgando…" : "Otorgar XP"}
          </button>
          <p className="text-[11px] text-muted-foreground">
            El XP se suma solo a la temporada en curso; no toca el XP de las recompensas diarias.
          </p>
        </form>
      </div>

      {/* settle */}
      <div className="glass rounded-2xl p-6 flex flex-wrap items-center justify-between gap-4" data-testid="bp-admin-settle-card">
        <div>
          <h3 className="font-display font-bold text-lg">Cerrar la temporada</h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-xl">
            Entrega automáticamente todas las recompensas no reclamadas (menos los dinos, que son elección del
            jugador), quita los roles del pase y marca la temporada como liquidada.
          </p>
        </div>
        <button onClick={() => { play("click"); setConfirmSettle(true); }} disabled={busy === "settle"}
          data-testid="bp-admin-settle"
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-crimson border border-crimson/40 hover:bg-crimson/10 transition-all">
          <CheckCircle2 size={16} /> Cerrar y liquidar
        </button>
      </div>

      {/* purchases */}
      <div className="glass rounded-2xl p-6" data-testid="bp-admin-purchases">
        <h3 className="font-display font-bold text-lg mb-4">Compras del pase</h3>
        {(ov.purchases || []).length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-sm">Todavía no hay compras en esta temporada.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-white/10">
                  <th className="py-2 pr-3">Fecha</th>
                  <th className="py-2 pr-3">Usuario</th>
                  <th className="py-2 pr-3">Pase</th>
                  <th className="py-2 pr-3">Fuente</th>
                  <th className="py-2 pr-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {ov.purchases.map((p, i) => {
                  const st = BP_STATUS_STYLE[p.status] || { label: p.status || "—", cls: "text-muted-foreground border-white/15 bg-white/[0.04]" };
                  return (
                    <tr key={`${p.at}-${i}`} className="border-b border-white/5" data-testid={`bp-admin-purchase-${i}`}>
                      <td className="py-2 pr-3 text-muted-foreground">{p.at ? new Date(p.at).toLocaleString() : "—"}</td>
                      <td className="py-2 pr-3 font-semibold">{p.user_name || "—"}</td>
                      <td className="py-2 pr-3 text-gold">{BP_TIER_LABEL[p.tier] || p.tier}</td>
                      <td className="py-2 pr-3 text-muted-foreground">{BP_SOURCE_LABEL[p.source] || p.source || "—"}</td>
                      <td className="py-2 pr-3">
                        <span className={`inline-flex items-center text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded border ${st.cls}`}>
                          {st.label.toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmModal
        open={confirmSettle}
        onClose={() => setConfirmSettle(false)}
        onConfirm={settle}
        title="Cerrar temporada y auto-otorgar no reclamados"
        confirmLabel="Cerrar temporada"
        tone="danger"
        loading={busy === "settle"}
        warning="Esta acción no se puede deshacer"
        message={`Se liquidará ${ov.season?.name || "la temporada actual"}: cada pase pendiente recibe sus recompensas no reclamadas y los dinos sin elegir caducan.`}
      />
    </div>
  );
}
