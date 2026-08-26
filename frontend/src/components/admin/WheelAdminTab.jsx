import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Gift, Save, RefreshCw, Plus, Trash2, AlertTriangle, Crown, Users, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

// Nublar Spin — owner console. Every save sends the WHOLE table (the backend
// judges the MERGED config and refuses one that would leave a plate unpayable
// while the wheel is open), so what the owner sees in this editor is exactly
// what the wheel will draw from after "Guardar".
const inputCls = "w-full glass rounded-lg px-3 py-2 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";
const smallCls = "glass rounded-lg px-2 py-1.5 text-xs bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="block text-[10px] label-overline text-muted-foreground mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-muted-foreground mt-1">{hint}</span>}
    </label>
  );
}

const KIND_LABEL = {
  primemeat: "PrimeMeat", amberium: "Amberium", growth_token: "Ficha crecimiento", diet_token: "Ficha dieta",
  glitch_skin: "Skin glitch (aleatoria)", dino_basic: "Dino salvaje (pool basic)", dino_prime: "Dino Prime (pool prime)", gen0_vial: "Vial GEN-Ø",
};
const AMOUNT_KINDS = new Set(["primemeat", "amberium"]);

export function oddsOf(segments) {
  const total = (segments || []).reduce((a, s) => a + Math.max(0, Number(s.weight) || 0), 0);
  return (segments || []).map((s) => (total > 0 ? (Math.max(0, Number(s.weight) || 0) / total) * 100 : 0));
}

export function WheelAdminTab() {
  const { play } = useSound();
  const [cfg, setCfg] = useState(null);
  const [segments, setSegments] = useState([]);
  const [pools, setPools] = useState({ basic: [], prime: [] });
  const [knobs, setKnobs] = useState({ enabled: true, base_spins: 1, patreon_bonus: true });
  const [saving, setSaving] = useState(false);
  const [recent, setRecent] = useState({ recent: [], attention: 0 });
  const [gift, setGift] = useState({ user_id: "", amount: 1, reason: "" });
  const [confirmReset, setConfirmReset] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.wheelAdminConfig();
      const c = r.data;
      setCfg(c);
      setSegments((c.segments || []).map((s) => ({ ...s })));
      setPools({ basic: [...(c.dino_pools?.basic || [])], prime: [...(c.dino_pools?.prime || [])] });
      setKnobs({ enabled: !!c.enabled, base_spins: Number(c.base_spins ?? 1), patreon_bonus: !!c.patreon_bonus });
    } catch (e) { toast.error("No se pudo cargar la ruleta"); }
    try { const r = await api.wheelAdminRecent(); setRecent(r.data); } catch (_) { /* optional */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const odds = useMemo(() => oddsOf(segments), [segments]);

  const save = async (body, okMsg) => {
    setSaving(true);
    try {
      const r = await api.wheelAdminSave(body);
      play("success"); toast.success(okMsg || "Guardado");
      const c = r.data; setCfg(c);
      setSegments((c.segments || []).map((s) => ({ ...s })));
      setPools({ basic: [...(c.dino_pools?.basic || [])], prime: [...(c.dino_pools?.prime || [])] });
      setKnobs({ enabled: !!c.enabled, base_spins: Number(c.base_spins ?? 1), patreon_bonus: !!c.patreon_bonus });
    } catch (e) {
      play("error");
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "No se pudo guardar");
    } finally { setSaving(false); }
  };

  const setSeg = (i, patch) => setSegments((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const addSeg = () => setSegments((prev) => [...prev, { key: `s${Date.now().toString(36)}`, kind: "primemeat", label: "Nuevo premio", amount: 1000, weight: 1, color: "#8B5CF6", icon: "coin" }]);
  const delSeg = (i) => setSegments((prev) => prev.filter((_, j) => j !== i));
  const togglePool = (tier, slug) => setPools((p) => ({ ...p, [tier]: p[tier].includes(slug) ? p[tier].filter((s) => s !== slug) : [...p[tier], slug] }));

  const doGift = async (e) => {
    e.preventDefault();
    if (!gift.user_id.trim() || !Number(gift.amount)) return;
    try {
      const r = await api.wheelAdminGrantSpins(gift.user_id.trim(), Number(gift.amount), gift.reason);
      play("success"); toast.success(`Giros bonus: ${r.data.bonus_spins}`);
      setGift({ user_id: "", amount: 1, reason: "" });
    } catch (e2) { play("error"); toast.error(e2?.response?.data?.detail || "No se pudo regalar"); }
  };

  const doReset = async () => {
    try { const r = await api.wheelAdminReset(); play("success"); toast.success("Tabla restaurada"); setCfg(r.data); setSegments((r.data.segments || []).map((s) => ({ ...s }))); setPools({ basic: [...(r.data.dino_pools?.basic || [])], prime: [...(r.data.dino_pools?.prime || [])] }); setKnobs({ enabled: !!r.data.enabled, base_spins: Number(r.data.base_spins ?? 1), patreon_bonus: !!r.data.patreon_bonus }); }
    catch (_) { play("error"); toast.error("No se pudo restaurar"); }
    setConfirmReset(false);
  };

  if (!cfg) return <div className="text-sm text-muted-foreground">Cargando ruleta…</div>;

  return (
    <div className="space-y-6" data-testid="wheel-admin">
      {/* Status strip */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`px-2.5 py-1 rounded-lg text-xs font-bold ${cfg.enabled ? "bg-emerald-500/15 text-emerald-400" : "bg-crimson/15 text-crimson"}`} data-testid="wheel-admin-enabled">{cfg.enabled ? "ABIERTA" : "CERRADA"}</span>
        <span className="px-2.5 py-1 rounded-lg text-xs glass">base {cfg.base_spins} giro/día · Patreon {cfg.patreon_bonus ? "+1 por nivel" : "sin bonus"}</span>
        <span className="px-2.5 py-1 rounded-lg text-xs glass">rev {cfg.revision ?? 0}</span>
        {recent.attention > 0 && <span className="px-2.5 py-1 rounded-lg text-xs bg-amber-500/15 text-amber-400 inline-flex items-center gap-1"><AlertTriangle size={12} /> {recent.attention} giros requieren revisión</span>}
      </div>
      {cfg.problems?.length > 0 && (
        <div className="rounded-xl p-3 bg-crimson/10 text-crimson text-xs" data-testid="wheel-admin-problems">
          <b>La tabla no es pagable:</b> {cfg.problems.join(" · ")}
        </div>
      )}

      {/* Knobs */}
      <div className="glass rounded-2xl p-5 space-y-4">
        <p className="label-overline text-xs text-gold inline-flex items-center gap-1.5"><Gift size={12} /> Giros por día</p>
        <div className="grid sm:grid-cols-3 gap-4">
          <Field label="Ruleta abierta">
            <button type="button" onClick={() => setKnobs((k) => ({ ...k, enabled: !k.enabled }))} data-testid="wheel-admin-toggle-enabled"
              className={`w-full rounded-lg px-3 py-2 text-sm font-bold ${knobs.enabled ? "bg-emerald-500/20 text-emerald-400" : "bg-crimson/20 text-crimson"}`}>{knobs.enabled ? "Sí" : "No"}</button>
          </Field>
          <Field label="Giros base (todos)" hint="0 = solo giros bonus/Patreon">
            <input type="number" min={0} max={24} className={inputCls} value={knobs.base_spins} onChange={(e) => setKnobs((k) => ({ ...k, base_spins: Math.max(0, Math.min(24, Number(e.target.value) || 0)) }))} data-testid="wheel-admin-base-spins" />
          </Field>
          <Field label="Patreon +1 por nivel" hint="Juvie +1 · Sub +2 · Adult +3 · Elder +4 · Apex +5 (solo active_patron)">
            <button type="button" onClick={() => setKnobs((k) => ({ ...k, patreon_bonus: !k.patreon_bonus }))} data-testid="wheel-admin-toggle-patreon"
              className={`w-full rounded-lg px-3 py-2 text-sm font-bold ${knobs.patreon_bonus ? "bg-emerald-500/20 text-emerald-400" : "glass"}`}>{knobs.patreon_bonus ? "Activo" : "Apagado"}</button>
          </Field>
        </div>
        <button disabled={saving} onClick={() => save(knobs, "Giros guardados")} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-background text-sm font-bold disabled:opacity-60" data-testid="wheel-admin-save-knobs"><Save size={14} /> Guardar giros</button>
      </div>

      {/* Segments */}
      <div className="glass rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="label-overline text-xs text-gold inline-flex items-center gap-1.5"><Crown size={12} /> Premios ({segments.length})</p>
          <button onClick={addSeg} className="inline-flex items-center gap-1 text-xs glass px-2.5 py-1.5 rounded-lg" data-testid="wheel-admin-add-seg"><Plus size={12} /> Añadir</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="wheel-admin-segments">
            <thead className="text-muted-foreground">
              <tr><th className="text-left p-1">Tipo</th><th className="text-left p-1">Etiqueta</th><th className="p-1">Cantidad</th><th className="p-1">Peso</th><th className="p-1">Prob.</th><th className="p-1">Color</th><th className="p-1">Sabor</th><th className="p-1"></th></tr>
            </thead>
            <tbody>
              {segments.map((s, i) => (
                <tr key={s.key || i} className="border-t border-white/5" data-testid={`wheel-admin-seg-${i}`}>
                  <td className="p-1"><select className={smallCls} value={s.kind} onChange={(e) => setSeg(i, { kind: e.target.value, amount: AMOUNT_KINDS.has(e.target.value) ? (s.amount || 1000) : 1 })}>{(cfg.kinds || Object.keys(KIND_LABEL)).map((k) => <option key={k} value={k}>{KIND_LABEL[k] || k}</option>)}</select></td>
                  <td className="p-1"><input className={smallCls + " w-44"} value={s.label} maxLength={40} onChange={(e) => setSeg(i, { label: e.target.value })} /></td>
                  <td className="p-1 text-center">{AMOUNT_KINDS.has(s.kind) ? <input type="number" min={1} className={smallCls + " w-24 text-right"} value={s.amount} onChange={(e) => setSeg(i, { amount: Number(e.target.value) })} /> : <span className="text-muted-foreground">1</span>}</td>
                  <td className="p-1 text-center"><input type="number" min={0} step={0.5} className={smallCls + " w-20 text-right"} value={s.weight} onChange={(e) => setSeg(i, { weight: Number(e.target.value) })} /></td>
                  <td className="p-1 text-center tabular-nums font-bold">{odds[i].toFixed(odds[i] >= 1 ? 1 : 2)}%</td>
                  <td className="p-1 text-center"><input type="color" value={s.color || "#8B5CF6"} onChange={(e) => setSeg(i, { color: e.target.value })} className="h-7 w-10 bg-transparent" /></td>
                  <td className="p-1 text-center">{s.kind === "growth_token" ? <select className={smallCls} value={s.flavor || "basic"} onChange={(e) => setSeg(i, { flavor: e.target.value })}><option value="basic">básica</option><option value="premium">premium (PRIME)</option></select> : <span className="text-muted-foreground">—</span>}</td>
                  <td className="p-1 text-center"><button onClick={() => delSeg(i)} className="text-crimson/80 hover:text-crimson" title="Quitar"><Trash2 size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-muted-foreground">Los pesos se normalizan solos (no hace falta que sumen 100). Rareza: Vial y Dino Prime = legendario; skins, fichas y dino salvaje = épico; Amberium ≥ 1.000 = épico.</p>
        <button disabled={saving} onClick={() => save({ segments }, "Premios guardados")} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-background text-sm font-bold disabled:opacity-60" data-testid="wheel-admin-save-segments"><Save size={14} /> Guardar premios</button>
      </div>

      {/* Dino pools */}
      <div className="glass rounded-2xl p-5 space-y-4">
        <p className="label-overline text-xs text-gold">Especies de los premios Dino</p>
        {["basic", "prime"].map((tier) => (
          <div key={tier} data-testid={`wheel-admin-pool-${tier}`}>
            <p className="text-xs font-bold mb-2">{tier === "basic" ? "Dino salvaje (75%, 3 mutaciones, dieta 150%)" : "Dino Prime (75%, PRIME, 4 mutaciones, dieta 300%)"} · {pools[tier].length} especies</p>
            <div className="flex flex-wrap gap-1.5">
              {(cfg.species || []).map((sp) => {
                const on = pools[tier].includes(sp.slug);
                return <button key={sp.slug} type="button" onClick={() => togglePool(tier, sp.slug)} className={`px-2 py-1 rounded-lg text-[11px] font-bold ${on ? "bg-gold text-background" : "glass text-muted-foreground"}`}>{sp.name}</button>;
              })}
            </div>
          </div>
        ))}
        <p className="text-[10px] text-muted-foreground">Skins glitch del premio (las de caja): {(cfg.glitch_pool || []).join(", ")}</p>
        <button disabled={saving} onClick={() => save({ dino_pools: pools }, "Especies guardadas")} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-background text-sm font-bold disabled:opacity-60" data-testid="wheel-admin-save-pools"><Save size={14} /> Guardar especies</button>
      </div>

      {/* Gift spins */}
      <form onSubmit={doGift} className="glass rounded-2xl p-5 space-y-3" data-testid="wheel-admin-gift">
        <p className="label-overline text-xs text-gold inline-flex items-center gap-1.5"><Users size={12} /> Regalar giros bonus</p>
        <div className="grid sm:grid-cols-[1fr_120px_1fr_auto] gap-3 items-end">
          <Field label="ID de usuario (web)"><input className={inputCls} value={gift.user_id} onChange={(e) => setGift((g) => ({ ...g, user_id: e.target.value }))} placeholder="id de la pestaña Usuarios" /></Field>
          <Field label="Cantidad (±)"><input type="number" min={-100} max={100} className={inputCls} value={gift.amount} onChange={(e) => setGift((g) => ({ ...g, amount: Number(e.target.value) }))} /></Field>
          <Field label="Motivo"><input className={inputCls} value={gift.reason} maxLength={120} onChange={(e) => setGift((g) => ({ ...g, reason: e.target.value }))} placeholder="evento, compensación…" /></Field>
          <button type="submit" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold text-background text-sm font-bold"><Gift size={14} /> Regalar</button>
        </div>
      </form>

      {/* Recent */}
      <div className="glass rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="label-overline text-xs text-gold inline-flex items-center gap-1.5"><History size={12} /> Últimos giros</p>
          <div className="flex gap-2">
            <button onClick={load} className="inline-flex items-center gap-1 text-xs glass px-2.5 py-1.5 rounded-lg"><RefreshCw size={12} /> Actualizar</button>
            {confirmReset ? (
              <><button onClick={doReset} className="text-xs px-2.5 py-1.5 rounded-lg bg-crimson text-white font-bold" data-testid="wheel-admin-reset-confirm">Restaurar tabla original</button><button onClick={() => setConfirmReset(false)} className="text-xs glass px-2.5 py-1.5 rounded-lg">No</button></>
            ) : (
              <button onClick={() => setConfirmReset(true)} className="text-xs glass px-2.5 py-1.5 rounded-lg text-crimson" data-testid="wheel-admin-reset">Restaurar defaults</button>
            )}
          </div>
        </div>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-[11px]" data-testid="wheel-admin-recent">
            <thead className="text-muted-foreground"><tr><th className="text-left p-1">Cuándo</th><th className="text-left p-1">Jugador</th><th className="text-left p-1">Premio</th><th className="p-1">Vía</th><th className="p-1">Estado</th></tr></thead>
            <tbody>
              {(recent.recent || []).map((r) => (
                <tr key={r.op_key} className="border-t border-white/5">
                  <td className="p-1 whitespace-nowrap">{(r.at || "").replace("T", " ").slice(0, 19)}</td>
                  <td className="p-1">{r.user_name || r.user_id}</td>
                  <td className="p-1">{r.label || "—"}{r.reward?.name ? ` · ${r.reward.name}` : ""}</td>
                  <td className="p-1 text-center">{r.lane || "—"}</td>
                  <td className={`p-1 text-center font-bold ${r.status === "granted" ? "text-emerald-400" : r.status === "refused" ? "text-muted-foreground" : "text-amber-400"}`}>{r.status}</td>
                </tr>
              ))}
              {(recent.recent || []).length === 0 && <tr><td colSpan={5} className="p-3 text-center text-muted-foreground">Sin giros todavía</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default WheelAdminTab;
