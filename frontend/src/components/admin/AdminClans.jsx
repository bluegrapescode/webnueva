import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Shield, Save, Trash2, Users, Flame } from "lucide-react";
import { api } from "@/lib/api";

const input = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";

export default function AdminClans() {
  const [s, setS] = useState(null);
  const [clans, setClans] = useState([]);

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([api.clanAdminGetSettings(), api.clanAdminList()]);
      setS(a.data); setClans(b.data.clans || []);
    } catch { toast.error("No se pudo cargar clanes"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try { await api.clanAdminSaveSettings(s); toast.success("Ajustes guardados"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  const del = async (id) => { if (!window.confirm("¿Eliminar este clan?")) return; try { await api.clanAdminDelete(id); toast.message("Clan eliminado"); load(); } catch { toast.error("Error"); } };

  if (!s) return <p className="text-muted-foreground text-sm">Cargando…</p>;
  return (
    <div data-testid="admin-clans">
      <div className="flex items-center gap-3 mb-5"><Shield className="text-gold" size={22} /><h2 className="font-display font-extrabold text-2xl">Gestión de Clanes</h2></div>
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="glass rounded-2xl p-5">
          <h3 className="font-bold mb-4">Ajustes globales</h3>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Moneda para fundar</span>
              <select data-testid="clan-currency" className={input} value={s.founding_currency} onChange={(e) => setS({ ...s, founding_currency: e.target.value })}>
                <option value="amberium" className="bg-background">Amberium</option>
                <option value="primemeat" className="bg-background">PrimeMeat</option>
              </select></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Costo de fundación</span><input type="number" data-testid="clan-cost" className={input} value={s.founding_cost} onChange={(e) => setS({ ...s, founding_cost: Number(e.target.value) })} /></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Mínimo de miembros</span><input type="number" data-testid="clan-min" className={input} value={s.min_members} onChange={(e) => setS({ ...s, min_members: Number(e.target.value) })} /></label>
            <button onClick={() => setS({ ...s, creation_enabled: !s.creation_enabled })} data-testid="clan-creation-toggle" className={`self-end p-2.5 rounded-lg text-sm font-semibold border ${s.creation_enabled ? "bg-emerald-500/20 border-emerald-400/40 text-emerald-200" : "bg-white/[0.03] border-white/10 text-white/50"}`}>Creación: {s.creation_enabled ? "ON" : "OFF"}</button>
          </div>
          <button onClick={save} data-testid="clan-settings-save" className="mt-4 inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Save size={15} /> Guardar</button>
        </div>
        <div>
          <h3 className="font-bold mb-3">Clanes ({clans.length})</h3>
          <div className="space-y-2">
            {clans.map((c) => (
              <div key={c.id} className="glass rounded-xl p-3 flex items-center gap-3">
                <span className="font-display font-black uppercase rounded-md px-2 py-1 text-sm" style={{ color: "#0a0b0f", background: c.color }}>[{c.tag}]</span>
                <div className="flex-1 min-w-0"><p className="font-bold text-sm truncate">{c.name}</p><p className="text-[11px] text-muted-foreground"><Users size={10} className="inline mr-1" />{c.member_count} · <Flame size={10} className="inline mx-1" />{c.notoriety}</p></div>
                <button onClick={() => del(c.id)} data-testid={`admin-clan-del-${c.id}`} className="p-2 rounded-lg text-red-300 hover:bg-red-500/10"><Trash2 size={15} /></button>
              </div>
            ))}
            {clans.length === 0 && <p className="text-sm text-muted-foreground">No hay clanes.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
