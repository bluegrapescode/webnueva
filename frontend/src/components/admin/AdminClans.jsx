import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Shield, Save, Trash2, Users, Flame, Swords, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";

const input = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";

export default function AdminClans() {
  const [s, setS] = useState(null);
  const [clans, setClans] = useState([]);
  const [turf, setTurf] = useState(null);

  const load = useCallback(async () => {
    try {
      const [a, b, t] = await Promise.all([api.clanAdminGetSettings(), api.clanAdminList(), api.turfAdminGetSettings()]);
      setS(a.data); setClans(b.data.clans || []); setTurf(t.data);
    } catch { toast.error("No se pudo cargar clanes"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try { await api.clanAdminSaveSettings(s); toast.success("Ajustes guardados"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  const saveTurf = async () => {
    try { await api.turfAdminSaveSettings(turf); toast.success("Turf Wars actualizado"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
  };
  const resetTurf = async () => { if (!window.confirm("¿Reiniciar TODOS los territorios a neutral?")) return; try { await api.turfAdminReset(); toast.message("Territorios reiniciados"); } catch { toast.error("Error"); } };
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

      {turf && (
        <div className="glass rounded-2xl p-5 mt-6" data-testid="admin-turf">
          <div className="flex items-center gap-2.5 mb-4"><Swords className="text-red-400" size={20} /><h3 className="font-bold text-lg">Turf Wars ⚔️</h3>
            <button onClick={resetTurf} data-testid="turf-reset" className="ml-auto inline-flex items-center gap-1.5 text-xs font-semibold border border-red-400/40 text-red-300 rounded-lg px-3 py-2 hover:bg-red-500/10"><RotateCcw size={13} /> Reiniciar territorios</button>
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Segundos para capturar</span><input type="number" data-testid="turf-capture-secs" className={input} value={turf.capture_seconds} onChange={(e) => setTurf({ ...turf, capture_seconds: Number(e.target.value) })} /></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Presencia mínima</span><input type="number" data-testid="turf-min-presence" className={input} value={turf.min_presence} onChange={(e) => setTurf({ ...turf, min_presence: Number(e.target.value) })} /></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Duración del rally (s)</span><input type="number" data-testid="turf-rally-secs" className={input} value={turf.rally_seconds} onChange={(e) => setTurf({ ...turf, rally_seconds: Number(e.target.value) })} /></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Notoriedad por captura</span><input type="number" data-testid="turf-noto-capture" className={input} value={turf.notoriety_capture} onChange={(e) => setTurf({ ...turf, notoriety_capture: Number(e.target.value) })} /></label>
            <label className="block"><span className="text-xs text-muted-foreground mb-1 block">Notoriedad por zona (renta)</span><input type="number" data-testid="turf-noto-hold" className={input} value={turf.notoriety_hold} onChange={(e) => setTurf({ ...turf, notoriety_hold: Number(e.target.value) })} /></label>
            <button onClick={() => setTurf({ ...turf, sim_enabled: !turf.sim_enabled })} data-testid="turf-sim-toggle" className={`self-end p-2.5 rounded-lg text-sm font-semibold border ${turf.sim_enabled ? "bg-emerald-500/20 border-emerald-400/40 text-emerald-200" : "bg-white/[0.03] border-white/10 text-white/50"}`}>Simulación: {turf.sim_enabled ? "ON" : "OFF"}</button>
          </div>
          <button onClick={saveTurf} data-testid="turf-settings-save" className="mt-4 inline-flex items-center gap-2 bg-gold text-background font-bold px-4 py-2.5 rounded-lg text-sm"><Save size={15} /> Guardar Turf Wars</button>
        </div>
      )}
    </div>
  );
}
