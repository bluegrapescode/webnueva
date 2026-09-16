import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Skull, Droplet, History, Trophy, X, Zap, Target } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { useBounty } from "@/context/BountyContext";
import { BountyCard } from "@/components/bounty/BountyCard";
import { TargetList } from "@/components/bounty/TargetList";
import { ContractModal } from "@/components/bounty/ContractModal";
import { fmtNum, fmtCountdown } from "@/lib/bountyMeta";

function SelfBountyPanel({ mine, config, onStart, busy }) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  const self = mine && mine.self;
  const cdLeft = (mine && mine.selfCooldownLeft) || 0;
  const perMin = (config && config.self_prime_per_min) || 5000;
  const durMin = ((config && config.self_max_seconds) || 900) / 60;
  const amber = (config && config.self_killer_amber) || 300;

  if (self) {
    return (
      <div className="rounded-2xl border p-5" style={{ borderColor: "rgba(240,180,41,0.4)", background: "linear-gradient(150deg, rgba(240,180,41,0.06), transparent)" }} data-testid="bounty-self-active">
        <div className="flex items-center gap-2 mb-3">
          <Droplet className="w-4 h-4 text-[#F0B429]" />
          <h3 className="text-sm font-bold uppercase tracking-widest text-[#F0B429]">Tu cabeza tiene precio</h3>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-center">
            <p className="text-2xl font-black text-[#F0B429] tabular-nums" data-testid="bounty-self-accrued-val">{fmtNum(self.accrued)}</p>
            <p className="text-[10px] uppercase tracking-wider text-white/40">🥩 Acumulado</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black text-white tabular-nums" data-testid="bounty-self-timer-val">{fmtCountdown(self.endsAt)}</p>
            <p className="text-[10px] uppercase tracking-wider text-white/40">Restante</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold text-white">🥩 {fmtNum(self.primePerMin)}<span className="text-white/40 text-xs">/min</span></p>
            <p className="text-[10px] uppercase tracking-wider text-white/40">Ganas mientras vivas</p>
          </div>
        </div>
        <p className="text-xs text-white/45 mt-3">Sobrevive para seguir ganando. Si te eliminan, el cazador recibe <span className="text-[#F0B429]">{fmtNum(amber)} Amberium</span> y tú conservas lo acumulado.</p>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5" data-testid="bounty-self-cta">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Droplet className="w-4 h-4 text-[#F0B429]" />
            <h3 className="text-sm font-bold uppercase tracking-widest text-white/80">Pon precio a tu cabeza</h3>
          </div>
          <p className="text-xs text-white/50">Gana 🥩 <span className="text-white font-semibold">{fmtNum(perMin)}</span>/min mientras sobrevivas (hasta {durMin} min). Quien te elimine se lleva <span className="text-[#F0B429]">{fmtNum(amber)} Amberium</span>.</p>
        </div>
        <button
          data-testid="bounty-self-start" disabled={busy || cdLeft > 0} onClick={onStart}
          className="shrink-0 flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-bold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: "linear-gradient(180deg, #F0B429, #b9860f)", color: "#1a1206", boxShadow: "0 10px 30px -12px rgba(240,180,41,0.8)" }}
        >
          <Droplet className="w-4 h-4" /> {cdLeft > 0 ? `Cooldown ${fmtCountdown(Date.now() + cdLeft * 1000)}` : "Ponerme precio"}
        </button>
      </div>
    </div>
  );
}

function AdminPanel({ config, targets, refresh }) {
  const { play } = useSound();
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [killSid, setKillSid] = useState("");
  useEffect(() => { if (config && !form) setForm({ ...config }); }, [config, form]);
  const act = async (fn, msg) => { setBusy(true); try { await fn(); play("click"); msg && toast.success(msg); refresh && refresh(); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } finally { setBusy(false); } };
  const fields = [["min_contract_prime", "Min PrimeMeat"], ["reward_amber_bonus", "Amber recompensa"], ["self_prime_per_min", "Self /min"], ["self_max_seconds", "Self máx (s)"], ["self_killer_amber", "Amber al cazador"], ["self_cooldown", "Cooldown (s)"]];
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5" data-testid="bounty-admin-panel">
      <div className="flex items-center gap-2 mb-4"><Zap className="w-4 h-4 text-[#F0B429]" /><h3 className="text-sm font-bold uppercase tracking-widest text-white/80">Control de Admin</h3></div>
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <select data-testid="bounty-admin-kill-select" value={killSid} onChange={(e) => setKillSid(e.target.value)} className="bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none">
          <option value="">Objetivo a "matar"…</option>
          {(targets || []).filter((t) => t.bounty.primeMeat > 0 || true).map((t) => <option key={t.sid} value={t.sid}>{t.name} · {t.species}</option>)}
        </select>
        <button data-testid="bounty-admin-simkill" disabled={busy || !killSid} onClick={() => act(() => api.bountySimulateKill(killSid), "Muerte simulada")}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-[#E11D2A]/40 text-[#ff6b74] text-xs font-semibold uppercase tracking-wider hover:bg-[#E11D2A]/10 disabled:opacity-40">
          <Skull className="w-3.5 h-3.5" /> Simular muerte
        </button>
      </div>
      {form && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {fields.map(([k, l]) => (
              <label key={k} className="block">
                <span className="text-[10px] uppercase tracking-wider text-white/40">{l}</span>
                <input data-testid={`bounty-cfg-${k}`} type="number" value={form[k] ?? ""} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                  className="mt-1 w-full bg-black/40 border border-white/10 rounded-md px-2.5 py-1.5 text-sm text-white focus:border-[#E11D2A]/50 outline-none" />
              </label>
            ))}
          </div>
          <button data-testid="bounty-cfg-save" disabled={busy} onClick={() => act(() => api.bountySetConfig(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v)]))), "Configuración guardada")}
            className="mt-4 flex items-center gap-2 px-3.5 py-2 rounded-lg border border-[#E11D2A]/40 text-[#ff6b74] text-xs font-semibold uppercase tracking-wider hover:bg-[#E11D2A]/10">
            Guardar configuración
          </button>
        </>
      )}
    </div>
  );
}

export default function Bounty() {
  const { user } = useAuth();
  const { play } = useSound();
  const { board, config, connected, lastEvent } = useBounty();
  const [targets, setTargets] = useState([]);
  const [simulated, setSimulated] = useState(false);
  const [mine, setMine] = useState(null);
  const [history, setHistory] = useState([]);
  const [modalTarget, setModalTarget] = useState(null);
  const [busy, setBusy] = useState(false);
  const [, tickNow] = useState(0);
  useEffect(() => { const t = setInterval(() => tickNow((n) => n + 1), 1000); return () => clearInterval(t); }, []);

  const loadTargets = useCallback(async () => {
    if (!user) return;
    try { const { data } = await api.bountyTargets(); setTargets(data.targets || []); setSimulated(data.simulated); } catch (e) {}
  }, [user]);
  const loadMine = useCallback(async () => {
    if (!user) { setMine(null); return; }
    try { const { data } = await api.bountyMine(); setMine(data); } catch (e) {}
  }, [user]);
  const loadHistory = useCallback(async () => {
    try { const { data } = await api.bountyHistory(20); setHistory(data.items || []); } catch (e) {}
  }, []);

  useEffect(() => { loadTargets(); loadMine(); loadHistory(); }, [loadTargets, loadMine, loadHistory]);
  useEffect(() => {
    if (!lastEvent) return;
    const e = lastEvent.event;
    if (["bounty:completed", "bounty:contract_new", "bounty:self_started", "bounty:self_expired"].includes(e)) { loadTargets(); loadHistory(); }
    if (["bounty:completed", "bounty:self_ended", "bounty:self_expired", "bounty:self_started", "bounty:self_tick", "bounty:contract_new"].includes(e)) loadMine();
  }, [lastEvent, loadTargets, loadMine, loadHistory]);

  const myContracts = (mine && mine.contracts) || [];
  const hasContract = myContracts.length > 0;
  const maxContracts = (config && config.max_contracts_per_user) || 3;
  const atLimit = myContracts.length >= maxContracts;

  const onHunt = (t) => { if (atLimit) { toast.error(`Alcanzaste el máximo de ${maxContracts} bounties. Cancela uno primero.`); return; } setModalTarget(t); };
  const confirmContract = async (prime) => {
    setBusy(true);
    try { await api.bountyPlaceContract(modalTarget.sid, prime); play("bountyAlert"); toast.success("¡Bounty publicado! La cacería ha comenzado."); setModalTarget(null); loadMine(); loadTargets(); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo publicar"); }
    finally { setBusy(false); }
  };
  const cancelContract = async (id) => { try { await api.bountyCancelContract(id); toast.success("Bounty cancelado y reembolsado"); loadMine(); loadTargets(); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } };
  const startSelf = async () => { setBusy(true); try { await api.bountySelfStart(); play("bountyAlert"); toast.success("¡Precio puesto sobre tu cabeza!"); loadMine(); } catch (e) { toast.error(e?.response?.data?.detail || "Error"); } finally { setBusy(false); } };

  const scoreOf = (b) => (b.type === "self" ? (b.accrued || 0) + (b.primePerMin || 0) + (b.killerAmber || 0) : (b.reward ? b.reward.primeMeat : 0));
  const allBoard = [...(board.contracts || []), ...(board.self || [])].sort((a, z) => scoreOf(z) - scoreOf(a));
  const isAdmin = user && user.role === "admin";

  return (
    <div className="min-h-screen px-4 sm:px-6 py-8" style={{ background: "radial-gradient(1200px 600px at 50% -10%, rgba(225,29,42,0.06), transparent 60%)" }}>
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 mb-3"><Skull className="w-6 h-6" style={{ color: "#E11D2A" }} /><h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white">LA <span style={{ color: "#E11D2A" }}>CACERÍA</span></h1></div>
          <p className="text-sm text-white/50 max-w-lg mx-auto">Elige a quién cazar y pon precio a su cabeza, o pon precio a la tuya y gana PrimeMeat por sobrevivir.</p>
          <div className="mt-3 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest"><span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400" : "bg-white/30"}`} /><span className="text-white/40">{connected ? "En vivo" : "Reconectando…"}</span>{simulated && <span className="text-white/30 ml-2">· jugadores simulados (preview)</span>}</div>
        </div>

        {user && <div className="mb-6"><SelfBountyPanel mine={mine} config={config} onStart={startSelf} busy={busy} /></div>}

        {/* Historial (izq) | Tablón de recompensas (centro, atracción principal) | Objetivos (der) */}
        <div className="grid lg:grid-cols-5 gap-6 items-start">
          {/* Historial a la izquierda */}
          <section className="lg:col-span-1 rounded-xl border border-white/8 bg-white/[0.015] p-4 sm:p-5">
            <div className="flex items-center gap-2 mb-4"><History className="w-4 h-4 text-white/50" /><h2 className="text-sm font-bold uppercase tracking-widest text-white/70">Historial de cacerías</h2></div>
            {history.length === 0 ? <p className="text-sm text-white/30 py-6 text-center" data-testid="bounty-history-empty">Aún no hay cacerías registradas.</p> : (
              <div className="grid gap-2 max-h-[560px] overflow-y-auto pr-1" data-testid="bounty-history-list">
                {history.map((b) => {
                  const done = b.status === "completed" || b.status === "dead";
                  return (
                    <div key={b.bountyId} className="flex items-center justify-between gap-2 px-3 py-2.5 rounded-md border border-white/8 bg-white/[0.02]" data-testid={`bounty-history-${b.bountyId}`}>
                      <div className="flex items-center gap-2.5 min-w-0">
                        {b.type === "self" ? <Droplet className="w-4 h-4 shrink-0" style={{ color: done ? "#F0B429" : "#5b5b62" }} /> : <Skull className="w-4 h-4 shrink-0" style={{ color: done ? "#F0B429" : "#5b5b62" }} />}
                        <div className="min-w-0"><p className="text-sm font-semibold text-white truncate">{b.targetName}</p><p className="text-[11px] text-white/40 truncate">{done ? (b.killerName ? <>eliminado por <span className="text-white/70">{b.killerName}</span></> : "eliminado") : b.status === "expired" ? "expiró" : "cancelado"}</p></div>
                      </div>
                      <span className={`text-[9px] font-bold uppercase tracking-wider shrink-0 ${done ? "text-[#F0B429]" : "text-white/30"}`}>{done ? "OK" : b.status === "expired" ? "Expiró" : "Cancel"}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Tablón WANTED — centro, tarjetas en 2 columnas (1 izq · 2 der · 3 abajo-izq · 4 abajo-der) */}
          <section className="lg:col-span-3 rounded-xl border border-white/8 bg-white/[0.015] p-4 sm:p-5">
            <div className="flex items-center gap-2 mb-4"><Trophy className="w-4 h-4 text-[#F0B429]" /><h2 className="text-sm font-bold uppercase tracking-widest text-white/70">Tablón de recompensas</h2><span className="ml-auto text-[10px] uppercase tracking-wider text-white/40 font-mono">{allBoard.length}</span></div>
            {allBoard.length === 0 ? (
              <p className="text-sm text-white/30 py-8 text-center" data-testid="bounty-board-empty">No hay bounties activos. Elige un objetivo o pon precio a tu cabeza.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start" data-testid="bounty-board">
                <AnimatePresence>
                  {allBoard.map((b, i) => (
                    <motion.div key={(b.bountyId || b.targetId) + (b.type || "")} layout
                      initial={{ opacity: 0, y: 20, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                      transition={{ delay: Math.min(i * 0.05, 0.25), duration: 0.35 }}>
                      <BountyCard bounty={b} rank={i} variant="full" />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}
          </section>

          {/* Objetivos en línea + Mis bounties a la derecha */}
          <div className="lg:col-span-1 space-y-6">
            <section className="rounded-xl border border-white/8 bg-white/[0.015] p-4 sm:p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2"><Target className="w-4 h-4 text-[#E11D2A]" /><h2 className="text-sm font-bold uppercase tracking-widest text-white/70">Objetivos</h2></div>
                {user && <span className="text-[10px] uppercase tracking-wider text-white/40 font-mono">{myContracts.length}/{maxContracts}</span>}
              </div>
              {user ? <div className="max-h-[560px] overflow-y-auto pr-1"><TargetList targets={targets} onHunt={onHunt} disabledHunt={atLimit} /></div>
                : <p className="text-sm text-white/40 py-8 text-center">Inicia sesión para cazar.</p>}
            </section>

            {user && (
              <section className="rounded-xl border border-white/8 bg-white/[0.015] p-4 sm:p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2"><Skull className="w-4 h-4 text-[#ff6b74]" /><h2 className="text-sm font-bold uppercase tracking-widest text-white/70">Mis bounties</h2></div>
                  <span className="text-[10px] uppercase tracking-wider text-white/40 font-mono">{myContracts.length}/{maxContracts}</span>
                </div>
                {hasContract ? (
                  <div className="grid gap-2" data-testid="bounty-mine-list">
                    {myContracts.map((c) => (
                      <div key={c.bountyId} className="flex items-center justify-between gap-2 px-3 py-2.5 rounded-md border border-white/8 bg-white/[0.02]" data-testid={`bounty-mine-${c.bountyId}`}>
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Skull className="w-4 h-4 text-[#ff6b74] shrink-0" />
                          <div className="min-w-0"><p className="text-sm font-semibold text-white truncate">{c.targetName}</p><p className="text-[11px] text-white/40 font-mono truncate">🥩 {fmtNum(c.reward.primeMeat)} · {fmtCountdown(c.expiresAt)}</p></div>
                        </div>
                        <button data-testid={`bounty-cancel-${c.bountyId}`} onClick={() => cancelContract(c.bountyId)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold text-white/60 border border-white/15 hover:bg-white/5 shrink-0"><X className="w-3.5 h-3.5" /></button>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-sm text-white/30 py-6 text-center">Sin bounties activos.</p>}
              </section>
            )}
          </div>
        </div>

        {isAdmin && <div className="mt-6"><AdminPanel config={config} targets={targets} refresh={() => { loadTargets(); loadMine(); loadHistory(); }} /></div>}
      </div>

      {modalTarget && <ContractModal target={modalTarget} config={config} wallet={mine && mine.wallet} onConfirm={confirmContract} onClose={() => setModalTarget(null)} busy={busy} />}
    </div>
  );
}
