import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { format } from "date-fns";
import {
  Plus, Trash2, Loader2, CalendarIcon, ImageIcon, Sparkles, DollarSign,
  Package, Eye, Ban, Pencil, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RARITY, RARITY_ORDER, SECTION_LABEL, rarityOf } from "@/components/shop/shopRarity";

const EMPTY = {
  name: "", description: "", image_url: "", rarity: "epic", section: "destacados",
  dino_species: "", skin_type: "", price_usd: "", skin_data: "", start_at: null, end_at: null, active: true,
};

function DateField({ label, value, onChange }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-wider text-white/50">{label}</label>
      <Popover>
        <PopoverTrigger asChild>
          <button type="button" className="mt-1 w-full inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 text-sm hover:bg-white/[0.06] transition-colors">
            <CalendarIcon size={14} className="text-white/50" />
            {value ? format(new Date(value), "dd MMM yyyy") : <span className="text-white/40">Sin límite</span>}
            {value && <X size={13} className="ml-auto text-white/40 hover:text-white" onClick={(e) => { e.stopPropagation(); onChange(null); }} />}
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 glass-strong border-white/10" align="start">
          <Calendar mode="single" selected={value ? new Date(value) : undefined}
            onSelect={(d) => onChange(d ? d.toISOString() : null)} initialFocus />
        </PopoverContent>
      </Popover>
    </div>
  );
}

export default function AdminSkinShop() {
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try { const r = await api.shopAdminList(); setData(r.data); } catch { setData({ items: [], stats: {} }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const reset = () => { setForm(EMPTY); setEditingId(null); };

  const startEdit = (s) => {
    setEditingId(s.id);
    setForm({
      name: s.name || "", description: s.description || "", image_url: s.image_url || "",
      rarity: s.rarity || "epic", section: s.section || "destacados",
      dino_species: s.dino_species || "", skin_type: s.skin_type || "", price_usd: String(s.price_usd ?? ""),
      skin_data: s.skin_data || "", start_at: s.start_at || null, end_at: s.end_at || null,
      active: s.active !== false,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async () => {
    if (!form.name.trim() || !form.image_url.trim() || !form.price_usd) {
      toast.error("Nombre, imagen y precio son obligatorios"); return;
    }
    setSaving(true);
    const body = {
      name: form.name.trim(), description: form.description || null, image_url: form.image_url.trim(),
      rarity: form.rarity, section: form.section, dino_species: form.dino_species || null,
      skin_type: form.skin_type || null,
      price_usd: parseFloat(form.price_usd), skin_data: form.skin_data || null,
      start_at: form.start_at, end_at: form.end_at, active: form.active,
    };
    try {
      if (editingId) { await api.shopAdminUpdate(editingId, body); toast.success("Skin actualizada"); }
      else { await api.shopAdminCreate(body); toast.success("Skin publicada en la tienda"); }
      reset(); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo guardar la skin");
    } finally { setSaving(false); }
  };

  const del = async (id) => {
    if (!window.confirm("¿Eliminar esta skin de la tienda? (se desactiva también en Stripe)")) return;
    try { await api.shopAdminDelete(id); toast.success("Skin eliminada"); load(); if (editingId === id) reset(); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo eliminar"); }
  };

  const toggleActive = async (s) => {
    try { await api.shopAdminUpdate(s.id, { active: !s.active }); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };

  const stats = data?.stats || {};
  const STAT_CARDS = [
    { k: "total_skins", label: "Skins", icon: Package },
    { k: "live_skins", label: "Activas", icon: Eye },
    { k: "total_sold", label: "Vendidas", icon: Sparkles },
    { k: "paid_orders", label: "Órdenes", icon: DollarSign },
    { k: "revenue_usd", label: "Ingresos $", icon: DollarSign },
  ];
  const r = rarityOf(form.rarity);

  return (
    <div className="space-y-8" data-testid="admin-skin-shop">
      {/* stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {STAT_CARDS.map((c) => (
          <div key={c.k} className="glass rounded-xl border border-white/10 p-4">
            <div className="flex items-center gap-2 text-white/45 text-[11px] uppercase tracking-wider"><c.icon size={13} /> {c.label}</div>
            <p className="font-display font-extrabold text-2xl mt-1">{stats[c.k] ?? 0}</p>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-8">
        {/* form */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          className="glass rounded-2xl border border-white/10 p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-display font-bold text-xl">{editingId ? "Editar skin" : "Crear nueva skin"}</h3>
            {editingId && <button onClick={reset} className="text-xs text-white/50 hover:text-white inline-flex items-center gap-1"><X size={13} /> Cancelar edición</button>}
          </div>

          <div className="space-y-4">
            <div>
              <label className="text-[11px] uppercase tracking-wider text-white/50">Nombre</label>
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Tyranno Espectral" data-testid="skin-name-input" className="mt-1 bg-white/[0.03] border-white/10" />
            </div>

            <div>
              <label className="text-[11px] uppercase tracking-wider text-white/50 flex items-center gap-1"><ImageIcon size={12} /> URL de la imagen</label>
              <Input value={form.image_url} onChange={(e) => set("image_url", e.target.value)} placeholder="https://…" data-testid="skin-image-input" className="mt-1 bg-white/[0.03] border-white/10" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/50">Rareza</label>
                <Select value={form.rarity} onValueChange={(v) => set("rarity", v)}>
                  <SelectTrigger className="mt-1 bg-white/[0.03] border-white/10" data-testid="skin-rarity-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {RARITY_ORDER.map((k) => (
                      <SelectItem key={k} value={k}>
                        <span className="inline-flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: RARITY[k].color }} /> {RARITY[k].label}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/50">Sección</label>
                <Select value={form.section} onValueChange={(v) => set("section", v)}>
                  <SelectTrigger className="mt-1 bg-white/[0.03] border-white/10" data-testid="skin-section-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(SECTION_LABEL).map((k) => <SelectItem key={k} value={k}>{SECTION_LABEL[k]}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/50">Precio (USD)</label>
                <Input type="number" min="0.5" step="0.01" value={form.price_usd} onChange={(e) => set("price_usd", e.target.value)} placeholder="9.99" data-testid="skin-price-input" className="mt-1 bg-white/[0.03] border-white/10" />
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/50">Dino (opcional)</label>
                <Input value={form.dino_species} onChange={(e) => set("dino_species", e.target.value)} placeholder="Tyrannosaurus" className="mt-1 bg-white/[0.03] border-white/10" />
              </div>
            </div>

            <div>
              <label className="text-[11px] uppercase tracking-wider text-white/50">Tipo de skin (para el filtro del catálogo)</label>
              <Input value={form.skin_type} onChange={(e) => set("skin_type", e.target.value)} placeholder="Ej: Clásica, Evento, Élite" data-testid="skin-type-input" className="mt-1 bg-white/[0.03] border-white/10" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <DateField label="Inicio" value={form.start_at} onChange={(v) => set("start_at", v)} />
              <DateField label="Fin" value={form.end_at} onChange={(v) => set("end_at", v)} />
            </div>

            <div>
              <label className="text-[11px] uppercase tracking-wider text-white/50">Descripción (opcional)</label>
              <Textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={2} className="mt-1 bg-white/[0.03] border-white/10" />
            </div>

            <div>
              <label className="text-[11px] uppercase tracking-wider text-white/50">skin_data in-game (opcional)</label>
              <Input value={form.skin_data} onChange={(e) => set("skin_data", e.target.value)} placeholder="código para aplicar en el servidor live" className="mt-1 bg-white/[0.03] border-white/10 font-code text-xs" />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
              <span className="text-sm text-white/70">Activa (visible en la tienda)</span>
              <Switch checked={form.active} onCheckedChange={(v) => set("active", v)} data-testid="skin-active-switch" />
            </div>

            <Button onClick={submit} disabled={saving} data-testid="admin-submit-skin"
              className="w-full font-bold text-black" style={{ background: "linear-gradient(135deg,#B8DA7E,#7CA842)" }}>
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              {editingId ? "Guardar cambios" : "Publicar skin"}
            </Button>
          </div>
        </motion.div>

        {/* live preview */}
        <div>
          <p className="text-[11px] uppercase tracking-wider text-white/50 mb-2">Vista previa</p>
          <div className="relative overflow-hidden rounded-xl border h-72"
            style={{ borderColor: `${r.color}55`, boxShadow: `0 14px 44px -16px ${r.color}88` }}>
            <div className="absolute inset-0" style={{ background: `radial-gradient(72% 64% at 50% 34%, ${r.color}40, #0b0d09 78%)` }} />
            {form.image_url ? <img src={form.image_url} alt="preview" className="absolute inset-0 w-full h-full object-cover" /> : <div className="absolute inset-0 grid place-items-center text-white/30"><ImageIcon size={40} /></div>}
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 to-transparent" />
            <div className="absolute top-2.5 left-2.5">
              <span className="label-overline text-[9px] px-2 py-0.5 rounded-full border" style={{ color: r.color, borderColor: `${r.color}66`, background: `${r.color}1f` }}>{r.label}</span>
            </div>
            <div className="absolute inset-x-0 bottom-0 p-3 backdrop-blur-md bg-black/45 border-t border-white/10">
              <p className="font-display font-extrabold uppercase tracking-tight text-white truncate">{form.name || "Nombre de la skin"}</p>
              <span className="font-code font-bold" style={{ color: r.color }}>${form.price_usd ? Number(form.price_usd).toFixed(2) : "0.00"}</span>
            </div>
          </div>

          {/* existing list */}
          <p className="text-[11px] uppercase tracking-wider text-white/50 mt-6 mb-2">Skins publicadas</p>
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {(data?.items || []).length === 0 && <p className="text-sm text-white/40 py-6 text-center">Aún no hay skins.</p>}
            {(data?.items || []).map((s) => {
              const sr = rarityOf(s.rarity);
              return (
                <div key={s.id} data-testid={`admin-skin-row-${s.id}`} className="flex items-center gap-3 glass rounded-lg border border-white/10 p-2">
                  <div className="w-12 h-12 rounded-md overflow-hidden shrink-0 border" style={{ borderColor: `${sr.color}55` }}>
                    <img src={s.image_url} alt={s.name} className="w-full h-full object-cover" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-sm truncate">{s.name}</p>
                    <p className="text-[11px] text-white/45">
                      <span style={{ color: sr.color }}>{sr.label}</span> · {SECTION_LABEL[s.section]} · ${s.price_usd.toFixed(2)} · {s.sold} vend.
                      {!s.live && <span className="text-amber-400"> · inactiva</span>}
                    </p>
                  </div>
                  <button onClick={() => toggleActive(s)} title={s.active ? "Desactivar" : "Activar"} className="p-2 rounded-md hover:bg-white/10 text-white/60"><Ban size={14} /></button>
                  <button onClick={() => startEdit(s)} title="Editar" className="p-2 rounded-md hover:bg-white/10 text-white/60"><Pencil size={14} /></button>
                  <button onClick={() => del(s.id)} data-testid={`admin-delete-skin-${s.id}`} title="Eliminar" className="p-2 rounded-md hover:bg-red-500/20 text-red-400"><Trash2 size={14} /></button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
