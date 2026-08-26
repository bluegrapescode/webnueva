import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Radio, Plus, Save, Search, PauseCircle, PlayCircle, Trophy, Crown, RefreshCw, Coins, AlertTriangle, Download, ShieldCheck, ShieldOff } from "lucide-react";
import { api } from "@/lib/api";
import { GlitchProx } from "@/components/common/GlitchProx";

const inputCls = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";
const btnPrimary = "inline-flex items-center justify-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg hover:brightness-110 transition-all text-sm";
const btnGhost = "inline-flex items-center justify-center gap-1.5 border border-white/10 bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-all";

// creator_alerts.type, translated for display (only BURST_DETECTED exists today).
const ALERT_TYPE_ES = { BURST_DETECTED: "RÁFAGA DETECTADA" };

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">{label}</span>
      {children}
    </label>
  );
}

function CreateForm({ onCreated }) {
  const [steamId, setSteamId] = useState("");
  const [code, setCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!steamId || !code) { toast.error("Steam ID y code son requeridos"); return; }
    setBusy(true);
    try {
      const r = await api.cpAdminCreate({ steam_id: steamId.trim(), code: code.trim().toUpperCase(), display_name: displayName.trim() || undefined });
      toast.success(`✓ Creator ${r.data.creator.code} creado`);
      setSteamId(""); setCode(""); setDisplayName("");
      onCreated && onCreated();
    } catch (e) {
      const d = e?.response?.data?.detail;
      const map = {
        INVALID_CODE: "Código inválido (A-Z, 0-9, _, 3-20 chars)",
        STEAM_USER_NOT_FOUND: "No hay ningún usuario con ese Steam ID en la web (aún no se logueó)",
        INVALID_STEAM_ID: "Steam ID inválido",
        ALREADY_EXISTS: "Ese código o ese Steam ID ya son creator",
      };
      toast.error(map[d] || d || "No se pudo crear");
    } finally { setBusy(false); }
  };

  return (
    <div className="glass rounded-2xl p-4 sm:p-5" data-testid="admin-cp-create">
      <div className="flex items-center gap-2 mb-3">
        <Plus size={14} className="text-gold" />
        <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">CREAR CREATOR</span>
      </div>
      <div className="grid sm:grid-cols-3 gap-3">
        <Field label="Steam ID (SteamID64)">
          <input value={steamId} onChange={(e) => setSteamId(e.target.value)} placeholder="76561198…" className={inputCls} data-testid="cp-create-steamid" />
        </Field>
        <Field label="Código (A-Z 0-9 _)">
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="XGHESSY" maxLength={20} className={inputCls} data-testid="cp-create-code" />
        </Field>
        <Field label="Nombre para mostrar (opcional)">
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="XGhessy" className={inputCls} data-testid="cp-create-name" />
        </Field>
      </div>
      <p className="mt-2 text-[11px] text-white/40">
        El usuario debe haberse logueado al menos una vez con Steam en tu web para que el Steam ID esté registrado.
      </p>
      <div className="mt-3">
        <button onClick={submit} disabled={busy} className={btnPrimary} data-testid="cp-create-submit">
          <Plus size={14} /> {busy ? "Creando…" : "CREAR CREATOR"}
        </button>
      </div>
    </div>
  );
}

function SettingsForm({ settings, onSaved }) {
  const [reward, setReward] = useState(settings?.creator_reward ?? 50000);
  const [mult, setMult] = useState(settings?.player_multiplier ?? 0.5);
  const [minPlaytime, setMinPlaytime] = useState(settings?.min_playtime_minutes ?? 10);
  const [skinTarget, setSkinTarget] = useState(settings?.skin_target ?? 100);
  const [busy, setBusy] = useState(false);
  const playerReward = Math.floor(Number(reward || 0) * Number(mult || 0));

  useEffect(() => {
    setReward(settings?.creator_reward ?? 50000);
    setMult(settings?.player_multiplier ?? 0.5);
    setMinPlaytime(settings?.min_playtime_minutes ?? 10);
    setSkinTarget(settings?.skin_target ?? 100);
  }, [settings]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.cpAdminSetSettings({
        creator_reward: Number(reward), player_multiplier: Number(mult),
        min_playtime_minutes: Number(minPlaytime), skin_target: Number(skinTarget),
      });
      toast.success("✓ Settings guardados");
      onSaved && onSaved(r.data.settings);
    } catch (_) { toast.error("No se pudieron guardar los settings"); }
    finally { setBusy(false); }
  };

  return (
    <div className="glass rounded-2xl p-4 sm:p-5" data-testid="admin-cp-settings">
      <div className="flex items-center gap-2 mb-3">
        <Coins size={14} className="text-gold" />
        <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">CONFIG DE RECOMPENSAS</span>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Field label="Recompensa Creator (PrimeMeat)"><input type="number" min={1} value={reward} onChange={(e) => setReward(e.target.value)} className={inputCls} data-testid="cp-set-reward" /></Field>
        <Field label="Multiplicador Jugador (0..1)"><input type="number" min={0.01} max={1} step={0.05} value={mult} onChange={(e) => setMult(e.target.value)} className={inputCls} data-testid="cp-set-mult" /></Field>
        <Field label="Minutos jugados mínimos"><input type="number" min={0} max={10000} value={minPlaytime} onChange={(e) => setMinPlaytime(e.target.value)} className={inputCls} data-testid="cp-set-minplaytime" /></Field>
        <Field label="Objetivo de skin (referidos)"><input type="number" min={1} max={100000} value={skinTarget} onChange={(e) => setSkinTarget(e.target.value)} className={inputCls} data-testid="cp-set-skintarget" /></Field>
      </div>
      <div className="mt-2 text-[11px] text-white/50">Recompensa del jugador calculada: <span className="text-gold font-black tabular-nums">{playerReward.toLocaleString()}</span> PrimeMeat</div>

      {/* Read-only: the exclusive is a fixed catalog design, never an editable
          image/URL field (fleet order 2026-08-11) — shown here as name + colour
          proximity so admins can see what they're managing without a picture. */}
      {settings?.skin_card?.name && (
        <div className="mt-3 flex items-center gap-2 text-[11px] text-white/50">
          <div className="h-7 w-7 shrink-0 overflow-hidden rounded border border-white/10">
            <GlitchProx proximity={settings.skin_card.proximity} compact />
          </div>
          Skin exclusiva fija del catálogo: <span className="text-purple-300 font-bold">{settings.skin_card.name}</span>
        </div>
      )}

      <div className="mt-4">
        <button onClick={save} disabled={busy} className={btnPrimary} data-testid="cp-set-save">
          <Save size={14} /> {busy ? "Guardando…" : "GUARDAR CONFIG"}
        </button>
      </div>
    </div>
  );
}

function CreatorRow({ creator, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [newCode, setNewCode] = useState(creator.code);
  const [busy, setBusy] = useState(false);
  const suspended = creator.status === "SUSPENDED";
  const paused = !!creator.paused;

  const update = async (payload) => {
    setBusy(true);
    try {
      await api.cpAdminUpdate({ user_id: creator.user_id, ...payload });
      toast.success("✓ Actualizado");
      onUpdated && onUpdated();
    } catch (e) {
      const d = e?.response?.data?.detail;
      const map = { INVALID_CODE: "Código inválido", CODE_TAKEN: "Ese código ya existe", NOT_FOUND: "Creator no existe" };
      toast.error(map[d] || d || "Error");
    } finally { setBusy(false); setEditing(false); }
  };

  return (
    <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
      className={`grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-3 px-4 py-2.5 border-b border-white/5 last:border-b-0 ${suspended ? "opacity-50" : ""}`}
      data-testid={`cp-row-${creator.code}`}
    >
      {/* Rank / avatar */}
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/20 bg-black/50 font-black text-xs uppercase overflow-hidden">
          {creator.avatar ? <img src={creator.avatar} alt="" className="h-full w-full object-cover" /> : (creator.display_name || "?")[0]}
        </div>
        {creator.exclusive_skin_unlocked && <Crown size={14} className="text-gold" />}
      </div>
      {/* Name + code */}
      <div className="min-w-0">
        <div className="text-sm font-black truncate">{creator.display_name}</div>
        {editing ? (
          <div className="flex items-center gap-1.5 mt-1">
            <input value={newCode} onChange={(e) => setNewCode(e.target.value.toUpperCase())} className={`${inputCls} py-1 text-xs w-32`} />
            <button onClick={() => update({ code: newCode })} disabled={busy} className={btnGhost}>Guardar</button>
            <button onClick={() => { setEditing(false); setNewCode(creator.code); }} className={btnGhost}>Cancelar</button>
          </div>
        ) : (
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-xs text-gold">{creator.code}</span>
            <button onClick={() => setEditing(true)} className="text-[10px] text-white/40 hover:text-white/70">editar</button>
          </div>
        )}
      </div>
      {/* Stats */}
      <div className="text-right hidden sm:block">
        <div className="text-sm font-black tabular-nums">{creator.total_referrals || 0}</div>
        <div className="text-[9px] font-bold tracking-widest text-white/40">TOTAL</div>
      </div>
      <div className="text-right hidden md:block">
        <div className="text-sm font-black tabular-nums text-white/70">{(creator.total_prime_meat_earned || 0).toLocaleString()}</div>
        <div className="text-[9px] font-bold tracking-widest text-white/40">PRIME MEAT</div>
      </div>
      {/* Action */}
      <div className="flex items-center gap-2 flex-wrap justify-end">
        {/* paused_until (anti-abuse auto-pause) is INDEPENDENT of status: a
            creator can read ACTIVO here and still be paused, earning nothing,
            until an admin clears the alert (Reactivar) or the pause expires. */}
        {paused && (
          <span
            className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-black tracking-widest text-amber-400"
            title="Pausado automáticamente por el sistema anti-abuso — ver Alertas arriba"
            data-testid={`cp-paused-${creator.code}`}
          >
            PAUSADO
          </span>
        )}
        <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-black tracking-widest ${
          suspended ? "border-crimson/40 bg-crimson/10 text-crimson" : "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
        }`}>{suspended ? "SUSPENDIDO" : "ACTIVO"}</span>
        <button onClick={() => update({ status: suspended ? "ACTIVE" : "SUSPENDED" })} disabled={busy}
          className={btnGhost} data-testid={`cp-toggle-${creator.code}`}>
          {suspended ? <><PlayCircle size={12} /> ACTIVAR</> : <><PauseCircle size={12} /> SUSPENDER</>}
        </button>
      </div>
    </motion.div>
  );
}

function AlertsPanel({ onChange }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.cpAdminAlerts();
      setAlerts(r.data.alerts || []);
    } catch (_) { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doAction = async (alert_id, action) => {
    try {
      await api.cpAdminAlertAction(alert_id, action);
      toast.success(action === "reactivate" ? "Creator reactivado" : action === "suspend" ? "Creator suspendido" : "Alerta descartada");
      await load();
      onChange && onChange();
    } catch (_) { toast.error("No se pudo aplicar la acción"); }
  };

  const active = alerts.filter((a) => !a.read);
  if (loading) return null;
  if (active.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-4 sm:p-5 border border-red-500/30 bg-red-500/[0.03]" data-testid="admin-cp-alerts">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={14} className="text-red-400" />
        <span className="text-[10px] font-black tracking-[0.3em] text-red-400/90">ALERTAS ANTI-ABUSO · {active.length}</span>
      </div>
      <div className="space-y-2">
        {active.map((a) => (
          <div key={a.id} className="rounded-lg bg-black/30 border border-red-500/20 px-3 py-2.5 flex items-center gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-black">
                <span className="font-mono text-gold">{a.code}</span>
                <span className="text-white/40 mx-2">·</span>
                <span className="text-red-400">{ALERT_TYPE_ES[a.type] || a.type}</span>
              </div>
              <div className="text-[11px] text-white/60 truncate">{a.message}</div>
              <div className="text-[10px] text-white/30 mt-0.5">
                Pausado hasta: {a.paused_until ? new Date(a.paused_until).toLocaleString("es-AR") : "—"}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => doAction(a.id, "reactivate")} className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 px-2.5 py-1 text-[10px] font-black tracking-widest text-emerald-400 transition">
                <ShieldCheck size={11} /> REACTIVAR
              </button>
              <button onClick={() => doAction(a.id, "suspend")} className="inline-flex items-center gap-1 rounded-md border border-crimson/40 bg-crimson/10 hover:bg-crimson/20 px-2.5 py-1 text-[10px] font-black tracking-widest text-crimson transition">
                <ShieldOff size={11} /> SUSPENDER
              </button>
              <button onClick={() => doAction(a.id, "clear")} className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[10px] font-black tracking-widest text-white/70 transition">
                DESCARTAR
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CreatorsTab() {
  const [creators, setCreators] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [l, s] = await Promise.all([api.cpAdminList(), api.cpAdminSettings()]);
      setCreators(l.data.creators || []);
      setSettings(s.data.settings || null);
    } catch (_) { toast.error("No pude cargar el panel de creators"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = creators.filter((c) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.code || "").toLowerCase().includes(s) || (c.display_name || "").toLowerCase().includes(s);
  });

  // The CSV route needs the admin's bearer token, which a plain <a href> download
  // link can never carry — fetch it through the authenticated client as a blob,
  // then trigger the save the same way Economía's client-built CSV does.
  const exportCsv = async () => {
    setExporting(true);
    try {
      const r = await api.cpAdminPayoutsCsv();
      const blob = new Blob([r.data], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "creator_payouts.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (_) {
      toast.error("No se pudo exportar el CSV");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="admin-creators-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Radio size={16} className="text-gold" />
          <h2 className="font-display font-black text-2xl tracking-tight">Programa de Creators</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportCsv} disabled={exporting} className={btnGhost} data-testid="cp-export-csv">
            <Download size={12} /> {exporting ? "EXPORTANDO…" : "EXPORTAR CSV"}
          </button>
          <button onClick={load} className={btnGhost}><RefreshCw size={12} /> ACTUALIZAR</button>
        </div>
      </div>

      <AlertsPanel onChange={load} />

      <SettingsForm settings={settings} onSaved={(s) => setSettings(s)} />
      <CreateForm onCreated={load} />

      <div className="glass rounded-2xl p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <Trophy size={14} className="text-gold" />
            <span className="text-[10px] font-black tracking-[0.3em] text-gold/80">TODOS LOS CREATORS · {creators.length}</span>
          </div>
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-white/40" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar código o nombre…"
              className={`${inputCls} pl-7 py-1.5 text-xs w-56`} data-testid="cp-admin-search" />
          </div>
        </div>
        <div className="divide-y divide-white/5 rounded-xl overflow-hidden bg-black/20" data-testid="cp-admin-list">
          {loading ? (
            <div className="px-4 py-8 text-center text-xs text-white/40">Cargando…</div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-white/40">Todavía no hay creators. Creá uno arriba.</div>
          ) : (
            <AnimatePresence>
              {filtered.map((c) => <CreatorRow key={c.id} creator={c} onUpdated={load} />)}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
}
