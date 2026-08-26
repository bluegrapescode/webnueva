import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import { ParkingSquare, Skull, Rocket, Trash2, Crown, Sparkles, Dna, Loader2, RefreshCw, PackageOpen, Drumstick, Pause, Play } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { bodyDropButtonState, parkButtonState } from "@/lib/vaultCooldown";
import { useSound } from "@/context/SoundContext";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { SkinIcon } from "@/components/common/SkinIcon";
import { SpeciesViewer3D } from "@/components/skin3d/SpeciesViewer3D";
import { useViewerSlot } from "@/components/skin3d/useViewerSlot";
import { VaultDinoPreview } from "./VaultDinoPreview";
import { VaultJobModal } from "./VaultJobModal";

// Vault dino entries carry no image URL — cross-reference the existing dinosaur
// catalog by species name/slug for card art. Cards prefer a STILL side-profile
// 3D model in the EXACT stored skin (owner ruling 2026-07-27: no animation, a
// side view, not head-on), viewport- and slot-gated (see useViewerSlot); the
// catalog image / generic icon are the fallbacks. Still cards read the light
// idle export, never the walk gait one — the model no longer moves, so the
// bigger download and the continuous render loop both bought nothing.
function mutationCount(m) {
  // _dino_view ships mutations as the game's "|"-string plus mutations_count;
  // legacy shapes (number / array) are still tolerated.
  if (typeof m === "number" && Number.isFinite(m)) return m;
  if (Array.isArray(m)) return m.length;
  return null;
}

function VaultDinoCard({ d, img, busy, onOpen, onRedeem, onDelete, play }) {
  const cardRef = useRef(null);
  const inView = useInView(cardRef, { amount: 0.15 });
  const [viewerFailed, setViewerFailed] = useState(false);
  const slot = useViewerSlot(inView && !viewerFailed);
  const muts = mutationCount(d.mutations_count ?? d.mutations);

  return (
    <motion.div
      ref={cardRef}
      layoutId={`vault-dino-card-${d.id}`}
      initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }}
      onClick={() => { onOpen(d); play("open"); }}
      className="relative glass rounded-xl overflow-hidden hover:border-gold/40 transition-all cursor-pointer group"
      data-testid={`vault-dino-${d.id}`}
    >
      <div className="aspect-square overflow-hidden relative" style={{ background: "#080d0b" }}>
        {slot ? (
          <SpeciesViewer3D
            species={d.species}
            active={!!d.species}
            skin={d.skin}
            interactive={false}
            liveSnapshotFallback={false}
            preferClip="idle"
            animate={false}
            view="side"
            onStatus={(s) => { if (s === "error") setViewerFailed(true); }}
          />
        ) : img ? (
          <img src={img} alt={d.species} className="w-full h-full object-contain p-2" />
        ) : (
          <SkinIcon rarity="Common" />
        )}
        <div className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-background/90 to-transparent pointer-events-none" />
        <div className="absolute top-2 left-2 flex flex-col gap-1 pointer-events-none">
          {d.is_prime && <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 inline-flex items-center gap-0.5"><Crown size={9} /> PRIME</span>}
          {d.is_elder && <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-sky-400/20 text-sky-300 border border-sky-400/40 inline-flex items-center gap-0.5"><Sparkles size={9} /> ELDER</span>}
        </div>
        <div className="absolute bottom-2 right-2 text-[8px] font-bold px-1.5 py-0.5 rounded-full glass border border-white/10 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          Ver detalles
        </div>
      </div>
      <div className="p-2.5">
        <p className="text-xs font-bold leading-tight truncate" data-testid={`vault-card-name-${d.id}`}>{d.custom_name || d.species}</p>
        {d.custom_name && <p className="text-[9px] text-muted-foreground leading-tight truncate">{d.species}</p>}
        <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground">
          <span>Crecimiento {d.growth_pct ?? Math.round((d.growth ?? 0) * 100)}%</span>
          {muts !== null && <span className="inline-flex items-center gap-0.5" title="Mutaciones"><Dna size={10} /> {muts}</span>}
        </div>
        <div className="grid grid-cols-2 gap-1.5 mt-2">
          <button onClick={(e) => { e.stopPropagation(); onRedeem(d); }} disabled={busy === `redeem-${d.id}`} data-testid={`vault-redeem-${d.id}`}
            className="inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-50">
            {busy === `redeem-${d.id}` ? <Loader2 size={11} className="animate-spin" /> : <Rocket size={11} />} Canjear
          </button>
          <button onClick={(e) => { e.stopPropagation(); onDelete(d); play("click"); }} data-testid={`vault-delete-${d.id}`}
            className="inline-flex items-center justify-center gap-1 text-[10px] font-bold px-2 py-1.5 rounded-lg bg-crimson/15 text-crimson border border-crimson/30 hover:bg-crimson/25 transition-all">
            <Trash2 size={11} /> Eliminar
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// Backend gate failures (park/redeem) raise HTTP 400/409 with `detail` as an OBJECT
// ({message, reasons:[...]}), not a string. Handing that object straight to toast/React
// children throws "Objects are not valid as a React child" -> ErrorBoundary -> a blank
// screen. Always resolve to a plain string here, for every handler below.
function errorMessage(e, fallback) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const parts = [];
    if (typeof detail.message === "string" && detail.message.trim()) parts.push(detail.message);
    if (Array.isArray(detail.reasons)) {
      detail.reasons.forEach((r) => { if (typeof r === "string" && r.trim()) parts.push(r); });
    }
    if (parts.length) return parts.join("\n");
  }
  if (e && !e.response) return "No se pudo contactar al servidor. Revisa tu conexión.";
  return fallback;
}

export function VaultSection() {
  const { play } = useSound();
  const [vault, setVault] = useState(undefined); // undefined=loading, null=load error
  const [imgMap, setImgMap] = useState({});
  const [job, setJob] = useState(null); // { id, verb }
  const [confirmSlay, setConfirmSlay] = useState(false);
  const [confirmBodyDrop, setConfirmBodyDrop] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null); // dino object
  const [busy, setBusy] = useState(null); // action key currently in flight
  // Preview tracks the dino ID (not the object) so the 8s vault poll keeps the
  // open preview's data fresh, and a dino redeemed/deleted elsewhere closes it.
  const [previewId, setPreviewId] = useState(null);

  // Stable identity: loadVault is passed to VaultJobModal (onDone) and VaultDinoPreview
  // (onChanged) — a per-render arrow here would churn those props on every render.
  const loadVault = useCallback(
    () => api.meVault().then((r) => setVault(r.data)).catch(() => setVault((p) => (p === undefined ? null : p))),
    []
  );

  useEffect(() => {
    loadVault();
    const t = setInterval(loadVault, 8000);
    return () => clearInterval(t);
  }, [loadVault]);

  useEffect(() => {
    api.dinosaurs().then((r) => {
      const m = {};
      (r.data || []).forEach((d) => { if (d.name) m[d.name] = d.image; if (d.slug) m[d.slug] = d.image; });
      setImgMap(m);
    }).catch(() => {});
  }, []);

  // park/redeem/slay may resolve synchronously OR return a job_id to poll — handle both.
  // `extra` carries job-recovery metadata (dinoId for redeem, baselineSlotsUsed for park)
  // that VaultJobModal uses if the job record itself ever 404s mid-poll.
  const runJobAction = async (key, verb, fn, successMsg, extra) => {
    setBusy(key);
    try {
      const r = await fn();
      const jobId = r?.data?.job_id;
      if (jobId) {
        setJob({ id: jobId, verb, ...(extra || {}) });
      } else {
        play("success");
        toast.success(successMsg);
        loadVault();
      }
    } catch (e) {
      play("error");
      toast.error(errorMessage(e, "No se pudo completar la acción"));
    } finally { setBusy(null); }
  };

  const doPark = () => runJobAction("park", "park", () => api.meVaultPark(), "Dinosaurio aparcado en la bóveda", { baselineSlotsUsed: vault?.slots_used ?? null });
  const doRedeem = (id) => runJobAction(`redeem-${id}`, "redeem", () => api.meVaultRedeem(id), "Dinosaurio canjeado en tu partida", { dinoId: id });
  const doSlay = () => { setConfirmSlay(false); runJobAction("slay", "slay", () => api.meSlay(), "Dinosaurio sacrificado"); };

  // Body Drop: the server drops a fresh corpse NEXT TO the caller so their
  // hungry young carnivore can eat — it never touches the caller's own dino
  // (never wire this to the slay/kill lane). Success copy comes from the
  // backend response (it names the corpse species), so this doesn't ride
  // runJobAction's fixed message. The request blocks until the game confirms
  // (up to ~25 s) — the button spinner covers the wait.
  const doBodyDrop = async () => {
    setConfirmBodyDrop(false);
    setBusy("bodydrop");
    try {
      const r = await api.meBodyDrop();
      play("success");
      toast.success(r?.data?.message || "Body Drop confirmado — un cuerpo fresco cayó junto a ti.");
      loadVault();
    } catch (e) {
      play("error");
      toast.error(errorMessage(e, "No se pudo completar el Body Drop"));
    } finally { setBusy(null); }
  };

  // Growth pause. Since 2026-07-27 this is the ONLY way to pause growth: the
  // in-game /pause + /unpause chat commands were removed, so nothing else drives
  // this queue. Same 75–100% growth requirement, only affects the CALLER's live
  // dino. Success/error copy comes from the backend (it relays
  // the game's real decision), so no fixed message here.
  const doGrowthPause = async (pause) => {
    setBusy(pause ? "gpause" : "gresume");
    try {
      const r = await api.meGrowthPause(pause);
      play("success");
      toast.success(r?.data?.message || (pause ? "Crecimiento pausado." : "Crecimiento reanudado."));
      loadVault(); // flip the Pausado/Creciendo pill immediately, not on the 8s poll
    } catch (e) {
      play("error");
      toast.error(errorMessage(e, "No se pudo cambiar la pausa de crecimiento"));
    } finally { setBusy(null); }
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    const key = `delete-${confirmDelete.id}`;
    setBusy(key);
    try {
      await api.meVaultDelete(confirmDelete.id);
      play("close");
      toast.success("Dinosaurio eliminado de la bóveda");
      setConfirmDelete(null);
      loadVault();
    } catch (e) { play("error"); toast.error(errorMessage(e, "No se pudo eliminar")); }
    finally { setBusy(null); }
  };

  const dinos = vault?.dinos || [];
  const slotsUsed = vault?.slots_used ?? dinos.length;
  const slotsTotal = vault?.slots_total ?? null;
  const pipCount = slotsTotal && slotsTotal <= 20 ? slotsTotal : 0;
  const previewDino = previewId != null ? dinos.find((d) => d.id === previewId) || null : null;
  // Body Drop's 10-min lease, straight off the vault summary, so the futile
  // press is never made. Missing/garbage field = today's always-pressable
  // button — see lib/vaultCooldown.
  const bodyDrop = bodyDropButtonState(vault, busy);
  const park = parkButtonState(vault, busy);

  return (
    <section className="mb-10" data-testid="vault-section">
      <ConfirmModal
        open={confirmSlay} onClose={() => setConfirmSlay(false)} onConfirm={doSlay} loading={busy === "slay"} tone="danger"
        title="¿Sacrificar tu dinosaurio en vivo?"
        message="Matarás permanentemente a tu dinosaurio actual. La criatura y todo su progreso se perderán para siempre."
        warning="ESTO NO SE PUEDE DESHACER" confirmLabel="Confirmar sacrificio" abortLabel="Abortar"
      />
      <ConfirmModal
        open={confirmBodyDrop} onClose={() => setConfirmBodyDrop(false)} onConfirm={doBodyDrop} loading={busy === "bodydrop"} tone="orange"
        title="¿Pedir un Body Drop?"
        message="El servidor dejará caer un cuerpo fresco junto a ti para que tu carnívoro joven pueda comer. No afecta a tu dinosaurio — no es un sacrificio. Requisitos: ser carnívoro, hambre por debajo del 30% y crecimiento menor al 65%. Límite: un Body Drop cada 10 minutos."
        confirmLabel="Pedir Body Drop" abortLabel="Cancelar"
      />
      <ConfirmModal
        open={!!confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={doDelete} loading={busy === `delete-${confirmDelete?.id}`} tone="danger"
        title={confirmDelete ? `¿Eliminar a ${confirmDelete.species}?` : "¿Eliminar dinosaurio?"}
        message="Este dinosaurio se eliminará permanentemente de tu bóveda."
        warning="ESTO NO SE PUEDE DESHACER" confirmLabel="Eliminar" abortLabel="Cancelar"
      />
      <VaultJobModal jobId={job?.id} verb={job?.verb} dinoId={job?.dinoId ?? null} baselineSlotsUsed={job?.baselineSlotsUsed ?? null} onDone={loadVault} onClose={() => setJob(null)} />

      <div className="flex items-center gap-3 mb-4">
        <PackageOpen className="text-gold" size={24} />
        <div>
          <p className="label-overline text-xs text-gold">Almacenamiento de dinosaurios</p>
          <h2 className="font-display font-extrabold text-2xl tracking-tight">Bóveda de Dinosaurios</h2>
        </div>
        <button onClick={() => { loadVault(); play("click"); }} data-testid="vault-refresh" className="ml-auto p-2 rounded-lg glass text-muted-foreground hover:text-foreground transition-colors">
          <RefreshCw size={15} />
        </button>
      </div>

      {vault === undefined ? (
        <p className="text-muted-foreground py-6 text-center text-sm">Cargando bóveda…</p>
      ) : vault === null ? (
        <p className="text-muted-foreground py-6 text-center text-sm" data-testid="vault-error">No se pudo cargar la bóveda. Reintentando automáticamente…</p>
      ) : (
        <div className="glass rounded-2xl p-5" data-testid="vault-panel">
          {/* summary + global actions */}
          <div className="flex flex-col lg:flex-row lg:items-center gap-5 mb-5 pb-5 border-b border-white/10">
            <div className="flex items-center gap-4">
              <div>
                <p className="font-display font-extrabold text-3xl leading-none" data-testid="vault-slots-used">
                  {slotsUsed}<span className="text-muted-foreground text-lg font-semibold"> de {slotsTotal ?? "∞"}</span>
                </p>
                <p className="label-overline text-[10px] text-muted-foreground mt-1">Espacios usados</p>
              </div>
              {pipCount > 0 && (
                <div className="flex items-center gap-1 flex-wrap max-w-[220px]">
                  {Array.from({ length: pipCount }).map((_, i) => (
                    <span key={i} className={`w-2.5 h-2.5 border ${i < slotsUsed ? "bg-gold border-gold" : "border-white/25"}`} style={{ borderRadius: 1 }} />
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2.5 lg:ml-auto">
              <button onClick={doPark} disabled={park.disabled} title={park.title} data-testid="vault-action-park"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold text-background font-bold text-sm hover:brightness-110 transition-all disabled:opacity-50">
                {busy === "park" ? <Loader2 size={15} className="animate-spin" /> : <ParkingSquare size={15} />} {park.label}
              </button>
              <button onClick={() => { setConfirmSlay(true); play("click"); }} disabled={busy === "slay"} data-testid="vault-action-slay"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-crimson/15 text-crimson border border-crimson/30 font-bold text-sm hover:bg-crimson/25 transition-all disabled:opacity-50">
                <Skull size={15} /> Sacrificar
              </button>
              <button
                onClick={() => { setConfirmBodyDrop(true); play("click"); }}
                disabled={bodyDrop.disabled}
                title={bodyDrop.title}
                data-testid="vault-action-bodydrop"
                data-bodydrop-cooldown-min={bodyDrop.minutes}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-orange-500/15 text-orange-400 border border-orange-500/30 font-bold text-sm hover:bg-orange-500/25 transition-all disabled:opacity-50"
              >
                {busy === "bodydrop" ? <Loader2 size={15} className="animate-spin" /> : <Drumstick size={15} />} {bodyDrop.label}
              </button>
              {/* growth pause pair — the only surface that pauses growth (the in-game
                  chat commands were removed 2026-07-27).
                  live.growth_paused mirrors the in-game bit (actor-keyed server-side, so a
                  respawn/relog/restart clears it like the real thing): the pill states it
                  and the active side of the pair is emphasized. */}
              <div className="inline-flex rounded-lg border border-sky-500/30 overflow-hidden"
                title={!vault?.online
                  ? "Debes estar en partida para pausar el crecimiento."
                  : (vault?.growth_pause && vault.growth_pause.enabled === false
                    ? "La pausa de crecimiento está desactivada en el servidor."
                    : "Congela o reanuda el crecimiento de tu dino en vivo (necesitas 75–100% de crecimiento).")}>
                {vault?.online && vault?.live && typeof vault.live.growth_paused === "boolean" && (
                  <span data-testid="vault-growthpause-state"
                    className={`inline-flex items-center gap-1.5 px-3 py-2.5 text-xs font-extrabold uppercase tracking-wide border-r border-sky-500/30 ${vault.live.growth_paused ? "bg-amber-400/20 text-amber-300" : "bg-emerald-500/10 text-emerald-400"}`}>
                    {vault.live.growth_paused ? <Pause size={12} /> : <Play size={12} />}
                    {vault.live.growth_paused ? "Pausado" : "Creciendo"}
                  </span>
                )}
                <button
                  onClick={() => { play("click"); doGrowthPause(true); }}
                  disabled={!!busy || !vault?.online || (vault?.growth_pause ? vault.growth_pause.enabled === false : false)}
                  data-testid="vault-action-growthpause"
                  className={`inline-flex items-center gap-2 px-4 py-2.5 font-bold text-sm transition-all disabled:opacity-50 ${vault?.live?.growth_paused === true ? "bg-sky-500/5 text-sky-400/60 hover:bg-sky-500/15" : "bg-sky-500/25 text-sky-300 hover:bg-sky-500/35"}`}
                >
                  {busy === "gpause" ? <Loader2 size={15} className="animate-spin" /> : <Pause size={15} />} Pausar crecimiento
                </button>
                <button
                  onClick={() => { play("click"); doGrowthPause(false); }}
                  disabled={!!busy || !vault?.online || (vault?.growth_pause ? vault.growth_pause.enabled === false : false)}
                  data-testid="vault-action-growthresume"
                  className={`inline-flex items-center gap-2 px-3.5 py-2.5 font-bold text-sm transition-all disabled:opacity-50 border-l border-sky-500/30 ${vault?.live?.growth_paused === true ? "bg-sky-500/25 text-sky-300 hover:bg-sky-500/35" : "bg-sky-500/5 text-sky-400/60 hover:bg-sky-500/15"}`}
                >
                  {busy === "gresume" ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />} Reanudar
                </button>
              </div>
            </div>
          </div>

          {/* stored dino cards — still side-profile 3D model in the exact stored skin; click for the full preview */}
          {dinos.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center text-sm" data-testid="vault-empty">No tienes dinosaurios guardados en la bóveda todavía.</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3" data-testid="vault-dinos-grid">
              {dinos.map((d) => (
                <VaultDinoCard
                  key={d.id}
                  d={d}
                  img={imgMap[d.species]}
                  busy={busy}
                  play={play}
                  onOpen={(dino) => setPreviewId(dino.id)}
                  onRedeem={(dino) => doRedeem(dino.id)}
                  onDelete={(dino) => setConfirmDelete(dino)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {previewDino && (
          <VaultDinoPreview
            key={previewDino.id}
            dino={previewDino}
            busy={busy}
            onClose={() => setPreviewId(null)}
            onRedeem={(dino) => { setPreviewId(null); doRedeem(dino.id); }}
            onDelete={(dino) => setConfirmDelete(dino)}
            onChanged={loadVault}
          />
        )}
      </AnimatePresence>
    </section>
  );
}

export default VaultSection;
