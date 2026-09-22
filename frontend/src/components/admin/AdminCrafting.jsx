import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Hammer, Boxes, Settings2, Gift, ScrollText, Plus, Trash2, Save, X } from "lucide-react";
import { api } from "@/lib/api";

const input = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";
const RARITIES = ["common", "uncommon", "rare", "epic", "legendary"];
const SUBTABS = [
  { k: "materials", label: "Materiales", icon: Boxes },
  { k: "recipes", label: "Recetas", icon: Hammer },
  { k: "settings", label: "Ajustes Globales", icon: Settings2 },
  { k: "grant", label: "Otorgar", icon: Gift },
  { k: "logs", label: "Historial", icon: ScrollText },
];

function Field({ label, children }) {
  return <label className="block"><span className="text-xs text-muted-foreground mb-1 block">{label}</span>{children}</label>;
}

export default function AdminCrafting() {
  const [sub, setSub] = useState("materials");
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.craftAdminOverview(); setData(data); }
    catch { toast.error("No se pudo cargar el crafteo"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="admin-crafting">
      <div className="flex items-center gap-3 mb-5">
        <Hammer className="text-gold" size={22} />
        <h2 className="font-display font-extrabold text-2xl">Gestión de Crafteo</h2>
      </div>
      <div className="flex gap-1 mb-5 overflow-x-auto glass rounded-xl p-1.5">
        {SUBTABS.map((t) => (
          <button key={t.k} onClick={() => setSub(t.k)} data-testid={`craft-subtab-${t.k}`}
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold whitespace-nowrap transition ${sub === t.k ? "bg-gold text-background" : "text-muted-foreground hover:text-foreground hover:bg-white/5"}`}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>

      {!data ? <p className="text-muted-foreground text-sm">Cargando…</p> : (
        <>
          {sub === "materials" && <MaterialsSection materials={data.materials} onChange={load} />}
          {sub === "recipes" && <RecipesSection recipes={data.recipes} materials={data.materials} onChange={load} />}
          {sub === "settings" && <SettingsSection settings={data.settings} onChange={load} />}
          {sub === "grant" && <GrantSection materials={data.materials} />}
          {sub === "logs" && <LogsSection />}
        </>
      )}
    </div>
  );
}

function MaterialsSection({ materials, onChange }) {
  const empty = { id: "", name: "", description: "", icon: "", rarity: "common", stack_limit: 999, enabled: true, order: 999 };
  const [form, setForm] = useState(empty);
  const save = async () => {
    if (!form.name.trim()) return toast.error("Nombre requerido");
    try { await api.craftAdminSaveMaterial({ ...form, stack_limit: Number(form.stack_limit) || 999, order: Number(form.order) || 999 }); toast.success("Material guardado"); setForm(empty); onChange(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  const disable = async (id) => { try { await api.craftAdminDeleteMaterial(id); toast.message("Material desactivado"); onChange(); } catch { toast.error("Error"); } };
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="glass rounded-2xl p-5">
        <h3 className="font-bold mb-4">{form.id ? "Editar material" : "Nuevo material"}</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Nombre"><input className={input} data-testid="mat-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Rareza"><select className={input} value={form.rarity} onChange={(e) => setForm({ ...form, rarity: e.target.value })}>{RARITIES.map((r) => <option key={r} value={r} className="bg-background">{r}</option>)}</select></Field>
          <div className="sm:col-span-2"><Field label="Descripción"><input className={input} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
          <div className="sm:col-span-2"><Field label="URL del icono"><input className={input} data-testid="mat-icon" value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} placeholder="https://…" /></Field></div>
          <Field label="Límite de stack"><input type="number" className={input} value={form.stack_limit} onChange={(e) => setForm({ ...form, stack_limit: e.target.value })} /></Field>
          <Field label="Orden"><input type="number" className={input} value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} /></Field>
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={save} data-testid="mat-save" className="inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Save size={15} /> Guardar</button>
          {form.id && <button onClick={() => setForm(empty)} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm border border-white/10"><X size={15} /> Cancelar</button>}
        </div>
      </div>
      <div className="space-y-2">
        {materials.map((m) => (
          <div key={m.id} className={`glass rounded-xl p-3 flex items-center gap-3 ${m.enabled === false ? "opacity-50" : ""}`}>
            <div className="h-11 w-11 rounded-lg overflow-hidden bg-black/40 shrink-0">{m.icon && <img src={m.icon} alt="" className="w-full h-full object-contain p-0.5" />}</div>
            <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{m.name}</p><p className="text-xs text-muted-foreground">{m.rarity} · stack {m.stack_limit}</p></div>
            <button onClick={() => setForm({ ...m, description: m.description || "" })} className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 hover:bg-white/5">Editar</button>
            <button onClick={() => disable(m.id)} className="p-2 rounded-lg text-red-300 hover:bg-red-500/10"><Trash2 size={15} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecipesSection({ recipes, materials, onChange }) {
  const empty = { id: "", name: "", dino: "", dino_slug: "", diet: "carnivore", rarity: "common", image_url: "", crafting_time: 3600, uses_granted: 20, enabled: true, order: 999, materials: [] };
  const [form, setForm] = useState(empty);
  const addMat = () => setForm({ ...form, materials: [...form.materials, { material_id: materials[0]?.id || "", qty: 10 }] });
  const setMat = (i, k, v) => setForm({ ...form, materials: form.materials.map((m, j) => j === i ? { ...m, [k]: v } : m) });
  const delMat = (i) => setForm({ ...form, materials: form.materials.filter((_, j) => j !== i) });
  const save = async () => {
    if (!form.name.trim()) return toast.error("Nombre requerido");
    try {
      await api.craftAdminSaveRecipe({ ...form, crafting_time: Number(form.crafting_time) || 60, uses_granted: Math.max(20, Number(form.uses_granted) || 20), order: Number(form.order) || 999, materials: form.materials.map((m) => ({ material_id: m.material_id, qty: Number(m.qty) || 1 })) });
      toast.success("Receta guardada"); setForm(empty); onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  const disable = async (id) => { try { await api.craftAdminDeleteRecipe(id); toast.message("Receta desactivada"); onChange(); } catch { toast.error("Error"); } };
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="glass rounded-2xl p-5">
        <h3 className="font-bold mb-4">{form.id ? "Editar receta" : "Nueva receta"}</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Nombre de la skin"><input className={input} data-testid="recipe-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Dinosaurio"><input className={input} value={form.dino} onChange={(e) => setForm({ ...form, dino: e.target.value })} placeholder="Tyrannosaurus" /></Field>
          <Field label="Slug (imagen)"><input className={input} value={form.dino_slug} onChange={(e) => setForm({ ...form, dino_slug: e.target.value })} placeholder="trex" /></Field>
          <Field label="Dieta"><select className={input} value={form.diet} onChange={(e) => setForm({ ...form, diet: e.target.value })}><option value="carnivore" className="bg-background">Carnívoro</option><option value="herbivore" className="bg-background">Herbívoro</option></select></Field>
          <Field label="Rareza"><select className={input} value={form.rarity} onChange={(e) => setForm({ ...form, rarity: e.target.value })}>{RARITIES.map((r) => <option key={r} value={r} className="bg-background">{r}</option>)}</select></Field>
          <Field label="Usos otorgados (mín 20)"><input type="number" className={input} value={form.uses_granted} onChange={(e) => setForm({ ...form, uses_granted: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="URL de imagen"><input className={input} value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} placeholder="/dinos/trex.png o https://…" /></Field></div>
          <Field label="Tiempo de crafteo (segundos)"><input type="number" className={input} data-testid="recipe-time" value={form.crafting_time} onChange={(e) => setForm({ ...form, crafting_time: e.target.value })} /></Field>
          <Field label="Orden"><input type="number" className={input} value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} /></Field>
        </div>
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs text-muted-foreground">Materiales requeridos</span><button onClick={addMat} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-white/10"><Plus size={13} /> Añadir</button></div>
          <div className="space-y-2">
            {form.materials.map((m, i) => (
              <div key={i} className="flex items-center gap-2">
                <select className={input} value={m.material_id} onChange={(e) => setMat(i, "material_id", e.target.value)}>{materials.map((mm) => <option key={mm.id} value={mm.id} className="bg-background">{mm.name}</option>)}</select>
                <input type="number" className={input + " w-24"} value={m.qty} onChange={(e) => setMat(i, "qty", e.target.value)} />
                <button onClick={() => delMat(i)} className="p-2 rounded-lg text-red-300 hover:bg-red-500/10"><X size={15} /></button>
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={save} data-testid="recipe-save" className="inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Save size={15} /> Guardar</button>
          {form.id && <button onClick={() => setForm(empty)} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm border border-white/10"><X size={15} /> Cancelar</button>}
        </div>
      </div>
      <div className="space-y-2">
        {recipes.map((r) => (
          <div key={r.id} className={`glass rounded-xl p-3 flex items-center gap-3 ${r.enabled === false ? "opacity-50" : ""}`}>
            <div className="h-11 w-11 rounded-lg overflow-hidden bg-black/40 shrink-0">{r.image_url && <img src={r.image_url} alt="" className="w-full h-full object-contain p-0.5" />}</div>
            <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{r.name}</p><p className="text-xs text-muted-foreground">{r.dino} · {r.rarity} · {Math.round((r.crafting_time || 0) / 60)}min · {(r.materials || []).length} mats</p></div>
            <button onClick={() => setForm({ ...empty, ...r, materials: (r.materials || []).map((m) => ({ ...m })) })} className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 hover:bg-white/5">Editar</button>
            <button onClick={() => disable(r.id)} className="p-2 rounded-lg text-red-300 hover:bg-red-500/10"><Trash2 size={15} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsSection({ settings, onChange }) {
  const [f, setF] = useState({ ...settings, vip: settings.role_limits?.vip ?? 2, apex: settings.role_limits?.apex ?? 3 });
  const toggles = [
    ["crafting_enabled", "Crafteo habilitado"], ["gathering_enabled", "Recolección habilitada"], ["notifications_enabled", "Notificaciones"],
  ];
  const nums = [
    ["crafting_speed_mult", "Velocidad de crafteo (x)"], ["material_drop_mult", "Multiplicador de drops (x)"],
    ["max_active_crafts", "Máx. crafteos activos (base)"], ["node_respawn_mult", "Respawn de nodos (x)"],
  ];
  const save = async () => {
    try {
      await api.craftAdminSaveSettings({
        crafting_enabled: !!f.crafting_enabled, gathering_enabled: !!f.gathering_enabled, notifications_enabled: !!f.notifications_enabled,
        crafting_speed_mult: Number(f.crafting_speed_mult) || 1, material_drop_mult: Number(f.material_drop_mult) || 1,
        max_active_crafts: Number(f.max_active_crafts) || 1, node_respawn_mult: Number(f.node_respawn_mult) || 1,
        role_limits: { vip: Number(f.vip) || 2, apex: Number(f.apex) || 3 },
      });
      toast.success("Ajustes guardados y propagados"); onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  return (
    <div className="glass rounded-2xl p-5 max-w-2xl">
      <div className="grid sm:grid-cols-3 gap-3 mb-5">
        {toggles.map(([k, label]) => (
          <button key={k} data-testid={`setting-${k}`} onClick={() => setF({ ...f, [k]: !f[k] })}
            className={`p-3 rounded-xl text-sm font-semibold border transition ${f[k] ? "bg-emerald-500/20 border-emerald-400/40 text-emerald-200" : "bg-white/[0.03] border-white/10 text-white/50"}`}>
            {label}: {f[k] ? "ON" : "OFF"}
          </button>
        ))}
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {nums.map(([k, label]) => (
          <Field key={k} label={label}><input type="number" step="0.1" className={input} data-testid={`setting-${k}`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
        ))}
        <Field label="Límite VIP"><input type="number" className={input} value={f.vip} onChange={(e) => setF({ ...f, vip: e.target.value })} /></Field>
        <Field label="Límite Apex"><input type="number" className={input} value={f.apex} onChange={(e) => setF({ ...f, apex: e.target.value })} /></Field>
      </div>
      <button onClick={save} data-testid="settings-save" className="mt-5 inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Save size={15} /> Guardar ajustes</button>
    </div>
  );
}

function GrantSection({ materials }) {
  const [f, setF] = useState({ steam_id: "", player_id: "", material_id: materials[0]?.id || "", amount: 50 });
  const grant = async () => {
    if (!f.steam_id && !f.player_id) return toast.error("Indica steam_id o player_id");
    try {
      await api.craftAdminGrant({ steam_id: f.steam_id || undefined, player_id: f.player_id || undefined, material_id: f.material_id, amount: Number(f.amount) || 0 });
      toast.success("Materiales otorgados (empujados por WebSocket)");
    } catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  return (
    <div className="glass rounded-2xl p-5 max-w-xl">
      <h3 className="font-bold mb-1">Otorgar materiales (simular recolección)</h3>
      <p className="text-xs text-muted-foreground mb-4">Server-authoritative. Útil para pruebas; en producción el mod del servidor llamará al endpoint de recolección.</p>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Steam ID"><input className={input} data-testid="grant-steam" value={f.steam_id} onChange={(e) => setF({ ...f, steam_id: e.target.value })} placeholder="7656…" /></Field>
        <Field label="…o Player ID"><input className={input} data-testid="grant-pid" value={f.player_id} onChange={(e) => setF({ ...f, player_id: e.target.value })} /></Field>
        <Field label="Material"><select className={input} data-testid="grant-material" value={f.material_id} onChange={(e) => setF({ ...f, material_id: e.target.value })}>{materials.map((m) => <option key={m.id} value={m.id} className="bg-background">{m.name}</option>)}</select></Field>
        <Field label="Cantidad"><input type="number" className={input} data-testid="grant-amount" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
      </div>
      <button onClick={grant} data-testid="grant-submit" className="mt-4 inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Gift size={15} /> Otorgar</button>
    </div>
  );
}

function LogsSection() {
  const [logs, setLogs] = useState([]);
  const [kind, setKind] = useState("");
  const load = useCallback(async () => { try { const { data } = await api.craftAdminLogs(kind || undefined, 100); setLogs(data.logs || []); } catch { toast.error("Error"); } }, [kind]);
  useEffect(() => { load(); }, [load]);
  return (
    <div>
      <div className="flex gap-2 mb-4">
        {["", "craft", "claim", "gather", "admin"].map((k) => (
          <button key={k} onClick={() => setKind(k)} className={`text-xs px-3 py-1.5 rounded-lg font-semibold ${kind === k ? "bg-gold text-background" : "border border-white/10 text-muted-foreground"}`}>{k || "Todos"}</button>
        ))}
      </div>
      <div className="glass rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-muted-foreground border-b border-white/10"><th className="p-3">Fecha</th><th className="p-3">Tipo</th><th className="p-3">Acción</th><th className="p-3">Jugador</th><th className="p-3">Detalle</th></tr></thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-b border-white/5"><td className="p-3 text-xs whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</td><td className="p-3 text-xs">{l.kind}</td><td className="p-3 text-xs">{l.action}</td><td className="p-3 text-xs font-mono">{(l.player_id || "").slice(0, 8) || "—"}</td><td className="p-3 text-xs text-muted-foreground max-w-[240px] truncate">{JSON.stringify(l.detail)}</td></tr>
            ))}
            {logs.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted-foreground text-sm">Sin registros.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
