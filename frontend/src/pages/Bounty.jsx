import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Skull, Crosshair, Pause, Play, X, Zap, RefreshCw, History } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { useBountySocket } from "@/hooks/useBountySocket";
import { BountyCard } from "@/components/bounty/BountyCard";
import { fmtNum } from "@/lib/bountyMeta";

function AdminButton({ children, onClick, testid, tone = "danger", disabled }) {
  const tones = {
    danger: "border-[#E11D2A]/40 text-[#ff6b74] hover:bg-[#E11D2A]/10",
    amber: "border-[#F0B429]/40 text-[#F0B429] hover:bg-[#F0B429]/10",
    ghost: "border-white/15 text-white/70 hover:bg-white/5",
  };
  return (
    <button
      data-testid={testid} onClick={onClick} disabled={disabled}
      className={`flex items-center gap-2 px-3.5 py-2 rounded-lg border text-xs font-semibold uppercase tracking-wider transition-colors disabled:opacity-40 ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

function AdminPanel({ snapshot, refreshHistory }) {
  const { play } = useSound();
  const cfg = (snapshot && snapshot.config) || {};
  const paused = snapshot && snapshot.paused;
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (cfg && !form) setForm({ ...cfg }); }, [cfg, form]);

  const act = async (fn, msg) => {
    setBusy(true);
    try { await fn(); play("click"); msg && toast.success(msg); refreshHistory && refreshHistory(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Error"); }
    finally { setBusy(false); }
  };

  const saveConfig = async () => {
    if (!form) return;
    await act(() => api.bountySetConfig({
      prime_meat: Number(form.prime_meat), experience: Number(form.experience),
      amberium: Number(form.amberium), next_bounty_delay: Number(form.next_bounty_delay),
      minimum_online_time: Number(form.minimum_online_time),
      recent_target_protection: Number(form.recent_target_protection),
      disconnect_grace: Number(form.disconnect_grace),
    }), "Configuración guardada");
  };

  const fields = [
    ["prime_meat", "Prime Meat"], ["experience", "EXP"], ["amberium", "Amberium"],
    ["next_bounty_delay", "Cooldown (s)"], ["minimum_online_time", "Min. online (s)"],
    ["recent_target_protection", "Protección recientes"], ["disconnect_grace", "Gracia desconexión (s)"],
  ];

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5" data-testid="bounty-admin-panel">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4 text-[#F0B429]" />
        <h3 className="text-sm font-bold uppercase tracking-widest text-white/80">Control de Admin</h3>
      </div>
      <div className="flex flex-wrap gap-2 mb-5">
        <AdminButton testid="bounty-admin-force" tone="danger" disabled={busy}
          onClick={() => act(() => api.bountyForceNew(), "Nuevo bounty generado")}>
          <Crosshair className="w-3.5 h-3.5" /> Forzar nuevo
        </AdminButton>
        <AdminButton testid="bounty-admin-simkill" tone="amber" disabled={busy}
          onClick={() => act(() => api.bountySimulateKill(), "Muerte simulada")}>
          <Skull className="w-3.5 h-3.5" /> Simular muerte
        </AdminButton>
        {paused ? (
          <AdminButton testid="bounty-admin-resume" tone="ghost" disabled={busy}
            onClick={() => act(() => api.bountyResume(), "Reanudado")}>
            <Play className="w-3.5 h-3.5" /> Reanudar
          </AdminButton>
        ) : (
          <AdminButton testid="bounty-admin-pause" tone="ghost" disabled={busy}
            onClick={() => act(() => api.bountyPause(), "Pausado")}>
            <Pause className="w-3.5 h-3.5" /> Pausar
          </AdminButton>
        )}
        <AdminButton testid="bounty-admin-cancel" tone="ghost" disabled={busy}
          onClick={() => act(() => api.bountyCancel(), "Bounty cancelado")}>
          <X className="w-3.5 h-3.5" /> Cancelar
        </AdminButton>
      </div>
      {form && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {fields.map(([k, label]) => (
              <label key={k} className="block">
                <span className="text-[10px] uppercase tracking-wider text-white/40">{label}</span>
                <input
                  data-testid={`bounty-cfg-${k}`} type="number" value={form[k] ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                  className="mt-1 w-full bg-black/40 border border-white/10 rounded-md px-2.5 py-1.5 text-sm text-white focus:border-[#E11D2A]/50 outline-none"
                />
              </label>
            ))}
          </div>
          <div className="mt-4">
            <AdminButton testid="bounty-cfg-save" tone="danger" disabled={busy} onClick={saveConfig}>
              <RefreshCw className="w-3.5 h-3.5" /> Guardar configuración
            </AdminButton>
          </div>
        </>
      )}
    </div>
  );
}

function HistoryRow({ b }) {
  const done = b.status === "completed";
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg border border-white/8 bg-white/[0.02]"
      data-testid={`bounty-history-${b.bountyId}`}>
      <div className="flex items-center gap-3 min-w-0">
        <Skull className="w-4 h-4 shrink-0" style={{ color: done ? "#F0B429" : "#5b5b62" }} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white truncate">{b.targetName}</p>
          <p className="text-[11px] text-white/40 truncate">
            {done ? <>eliminado por <span className="text-white/70">{b.killerName}</span></> : "Cancelado (sin recompensa)"}
          </p>
        </div>
      </div>
      <div className="text-right shrink-0">
        <span className={`text-[10px] font-bold uppercase tracking-wider ${done ? "text-[#F0B429]" : "text-white/30"}`}>
          {done ? "Completado" : "Cancelado"}
        </span>
        <p className="text-[10px] text-white/30">#{b.bountyId}</p>
      </div>
    </div>
  );
}

export default function Bounty() {
  const { user } = useAuth();
  const { play } = useSound();
  const { snapshot, lastEvent, connected } = useBountySocket((event) => {
    if (event === "bounty:completed") play("bountyComplete");
    if (event === "bounty:target_disconnected") play("bountyDisconnect");
  });
  const [history, setHistory] = useState([]);

  const loadHistory = async () => {
    try { const { data } = await api.bountyHistory(15); setHistory(data.items || []); } catch (e) {}
  };
  useEffect(() => { loadHistory(); }, []);
  useEffect(() => {
    if (lastEvent && (lastEvent.event === "bounty:completed" || lastEvent.event === "bounty:cancelled")) loadHistory();
  }, [lastEvent]);

  const isAdmin = user && user.role === "admin";

  return (
    <div className="min-h-screen px-4 sm:px-6 py-10" style={{ background: "radial-gradient(1200px 600px at 50% -10%, rgba(225,29,42,0.06), transparent 60%)" }}>
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <Skull className="w-6 h-6" style={{ color: "#E11D2A" }} />
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white">
              GLOBAL <span style={{ color: "#E11D2A" }}>BOUNTY</span>
            </h1>
          </div>
          <p className="text-sm text-white/50 max-w-lg mx-auto">
            Un objetivo global elegido al azar por el servidor. Elimínalo y reclama la recompensa automáticamente.
          </p>
          <div className="mt-3 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest">
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400" : "bg-white/30"}`} />
            <span className="text-white/40">{connected ? "En vivo" : "Reconectando…"}</span>
          </div>
        </div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <BountyCard snapshot={snapshot} lastEvent={lastEvent} />
        </motion.div>

        {isAdmin && (
          <div className="mt-8">
            <AdminPanel snapshot={snapshot} refreshHistory={loadHistory} />
          </div>
        )}

        <div className="mt-10">
          <div className="flex items-center gap-2 mb-4">
            <History className="w-4 h-4 text-white/50" />
            <h2 className="text-sm font-bold uppercase tracking-widest text-white/70">Historial de cacerías</h2>
          </div>
          {history.length === 0 ? (
            <p className="text-sm text-white/30 py-6 text-center" data-testid="bounty-history-empty">Aún no hay cacerías registradas.</p>
          ) : (
            <div className="grid gap-2" data-testid="bounty-history-list">
              {history.map((b) => <HistoryRow key={b.bountyId} b={b} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
