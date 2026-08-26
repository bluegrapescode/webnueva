import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { X, Crown, Sparkles, Rocket, Trash2, Loader2, CalendarClock, Activity, Wheat, Pencil, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { SpeciesViewer3D } from "@/components/skin3d/SpeciesViewer3D";
import { SegBar } from "@/components/common/Hud";
import { MutationEditor } from "./MutationEditor";

// Everything the vault stored about one parked dinosaur, opened from its card
// with a shared-element (layoutId) transition. Data contract = vault.py
// _dino_view: stats/diet carry the raw ABSOLUTE values captured at park time,
// but the DISPLAY is percentages (owner ruling 2026-07-11) — vitals derive
// cur/max here, diet uses the backend-computed diet_pct (its denominator, the
// per-species growth-scaled baseline, only exists backend-side) with the
// absolute value as fallback for species without a baseline.

const VITAL_ROWS = [
  { cur: "health", max: "max_health", label: "Salud", color: "#E24A4A" },
  { cur: "stamina", max: "max_stamina", label: "Estamina", color: "#38bdf8" },
  { cur: "hunger", max: "max_hunger", label: "Hambre", color: "#7CA842" },
  { cur: "thirst", max: "max_thirst", label: "Sed", color: "#34D399" },
  { cur: "oxygen", max: "max_oxygen", label: "Oxígeno", color: "#a78bfa" },
];

const DIET_ROWS = [
  { k: "a", label: "Carbohidratos" },
  { k: "b", label: "Proteínas" },
  { k: "c", label: "Lípidos" },
];

function fmtAbs(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return Math.abs(v) >= 100 ? Math.round(v).toLocaleString("es") : (Math.round(v * 10) / 10).toLocaleString("es");
}

function fmtParkedAt(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("es", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function VitalAbsRow({ label, color, cur, max }) {
  const hasMax = typeof max === "number" && Number.isFinite(max) && max > 0;
  const hasCur = typeof cur === "number" && Number.isFinite(cur);
  const pct = hasMax && hasCur ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        <span className="font-display font-bold text-[12px] tabular-nums" style={{ color: hasCur ? color : undefined }}>
          {hasCur ? (hasMax ? `${Math.round(pct)}%` : fmtAbs(cur)) : "Sin datos"}
        </span>
      </div>
      <SegBar value={pct} max={100} color={hasCur ? color : "#4b5563"} height={6} />
    </div>
  );
}

export function VaultDinoPreview({ dino, busy, onClose, onRedeem, onDelete, onChanged }) {
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [savingName, setSavingName] = useState(false);

  // Close on Escape — the preview is a full-screen surface. While the rename
  // input is open, Escape only closes the editor.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      if (editingName) { setEditingName(false); return; }
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, editingName]);

  if (!dino) return null;

  const saveName = async () => {
    if (savingName) return;
    setSavingName(true);
    try {
      const r = await api.meVaultRename(dino.id, nameDraft);
      toast.success(r?.data?.custom_name ? "Nombre guardado" : "Nombre restablecido");
      setEditingName(false);
      onChanged && onChanged();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" && d.trim() ? d : "No se pudo renombrar el dinosaurio");
    } finally {
      setSavingName(false);
    }
  };

  const growthPct = typeof dino.growth_pct === "number" ? dino.growth_pct
    : (typeof dino.growth === "number" ? Math.round(dino.growth * 100) : null);
  const stats = dino.stats || {};
  const diet = dino.diet || {};
  const dietPct = dino.diet_pct || {};
  const parkedAt = fmtParkedAt(dino.parked_at);

  return (
    <motion.div
      className="fixed inset-0 z-[110] flex items-center justify-center p-4"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      data-testid="vault-dino-preview"
    >
      <motion.div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.div
        layoutId={`vault-dino-card-${dino.id}`}
        transition={{ type: "spring", stiffness: 320, damping: 32 }}
        className="relative glass-strong rounded-2xl w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden"
        data-testid={`vault-dino-preview-${dino.id}`}
      >
        {/* Header — identity + badges */}
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-white/10 shrink-0">
          <div className="min-w-0">
            <p className="label-overline text-[10px] text-gold">Bóveda de Dinosaurios</p>
            {editingName ? (
              <div className="flex items-center gap-2 mt-1" data-testid="vault-preview-rename-editor">
                <input
                  autoFocus value={nameDraft} maxLength={32}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") saveName(); }}
                  placeholder={dino.species}
                  data-testid="vault-preview-rename-input"
                  className="glass rounded-lg px-3 py-2 text-lg font-display font-bold bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/40 min-w-0 flex-1"
                />
                <button onClick={saveName} disabled={savingName} data-testid="vault-preview-rename-save"
                  className="p-2 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-50 shrink-0">
                  {savingName ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                </button>
                <button onClick={() => setEditingName(false)} disabled={savingName}
                  className="p-2 rounded-lg glass hover:bg-white/10 transition-colors shrink-0">
                  <X size={15} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 min-w-0">
                <h3 className="font-display font-extrabold text-3xl tracking-tight leading-tight truncate" data-testid="vault-preview-species">
                  {dino.custom_name || dino.species}
                </h3>
                <button
                  onClick={() => { setNameDraft(dino.custom_name || ""); setEditingName(true); }}
                  title="Renombrar dinosaurio" data-testid="vault-preview-rename"
                  className="p-1.5 rounded-lg glass text-muted-foreground hover:text-gold hover:bg-white/10 transition-colors shrink-0">
                  <Pencil size={14} />
                </button>
              </div>
            )}
            {dino.custom_name && !editingName && (
              <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{dino.species}</p>
            )}
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              {dino.is_prime && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded bg-gold/20 text-gold border border-gold/40 inline-flex items-center gap-1"><Crown size={10} /> PRIME</span>}
              {dino.is_elder && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded bg-sky-400/20 text-sky-300 border border-sky-400/40 inline-flex items-center gap-1"><Sparkles size={10} /> ELDER</span>}
              {growthPct !== null && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded glass border border-white/15">Crecimiento {growthPct}%</span>}
              {dino.elder_stacks > 0 && <span className="text-[9px] font-extrabold px-2 py-0.5 rounded glass border border-white/15">Acumulaciones de Anciano: {dino.elder_stacks}</span>}
            </div>
          </div>
          <button onClick={onClose} data-testid="vault-preview-close"
            className="p-2 rounded-lg glass hover:bg-white/10 transition-colors shrink-0">
            <X size={18} />
          </button>
        </div>

        {/* Body — landscape 3D stage left (the hero), scrollable record right */}
        <div className="flex-1 min-h-0 md:flex-none md:h-[500px] flex flex-col md:flex-row overflow-y-auto md:overflow-hidden">
          <div className="relative md:w-[58%] shrink-0 min-h-[340px] md:min-h-0 md:self-stretch border-b md:border-b-0 md:border-r border-white/10"
            style={{ background: "radial-gradient(closest-side at 50% 62%, rgba(124,168,66,0.10), rgba(8,13,11,0) 78%), #080d0b" }}>
            {/* Still side profile, matching the card it opened from and the
                live viewer (owner 2026-07-27). No turntable — it "shouldn't
                spin"; drag-to-rotate stays. */}
            <SpeciesViewer3D
              species={dino.species}
              active={!!dino.species}
              skin={dino.skin}
              interactive
              liveSnapshotFallback={false}
              preferClip="idle"
              animate={false}
              view="side"
            />
          </div>

          <div className="md:w-[42%] px-6 py-5 space-y-5 md:overflow-y-auto">
            <div className="space-y-2.5">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Activity size={11} /> Constantes al Aparcar</p>
              {VITAL_ROWS.map((v) => (
                <VitalAbsRow key={v.cur} label={v.label} color={v.color} cur={stats[v.cur]} max={stats[v.max]} />
              ))}
            </div>

            {DIET_ROWS.some((r) => typeof diet[r.k] === "number" && Number.isFinite(diet[r.k])) && (
              <div>
                <p className="label-overline text-[10px] text-muted-foreground mb-1.5 inline-flex items-center gap-1.5"><Wheat size={11} /> Dieta Almacenada</p>
                <div className="grid grid-cols-3 gap-2">
                  {DIET_ROWS.map((r) => (
                    <div key={r.k} className="glass rounded-lg px-2.5 py-2 text-center">
                      <p className="font-display font-bold text-sm tabular-nums">{typeof dietPct[r.k] === "number" ? `${dietPct[r.k]}%` : (fmtAbs(diet[r.k]) ?? "—")}</p>
                      <p className="text-[9px] text-muted-foreground mt-0.5">{r.label}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Editable mutation panel (paid, Dino Den style; 6 visible slots per
                owner ruling 2026-07-16) — MutationEditor owns the whole surface.
                The "Piel Almacenada" swatch block was removed the same day (owner
                ask); the stored skin still renders on the 3D model itself. */}
            <MutationEditor dino={dino} onChanged={onChanged} />

            {parkedAt && (
              <p className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5" data-testid="vault-preview-parked-at">
                <CalendarClock size={12} /> Aparcado el {parkedAt}
              </p>
            )}
          </div>
        </div>

        {/* Footer — actions */}
        <div className="px-6 py-4 border-t border-white/10 grid grid-cols-2 gap-2.5 shrink-0">
          <button onClick={() => onRedeem(dino)} disabled={busy === `redeem-${dino.id}`} data-testid={`vault-preview-redeem-${dino.id}`}
            className="inline-flex items-center justify-center gap-1.5 text-sm font-bold px-3 py-2.5 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-50">
            {busy === `redeem-${dino.id}` ? <Loader2 size={14} className="animate-spin" /> : <Rocket size={14} />} Canjear
          </button>
          <button onClick={() => onDelete(dino)} data-testid={`vault-preview-delete-${dino.id}`}
            className="inline-flex items-center justify-center gap-1.5 text-sm font-bold px-3 py-2.5 rounded-lg bg-crimson/15 text-crimson border border-crimson/30 hover:bg-crimson/25 transition-all">
            <Trash2 size={14} /> Eliminar
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default VaultDinoPreview;
