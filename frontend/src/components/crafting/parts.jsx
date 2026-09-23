import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, Hammer, Clock, Loader2, Sparkles, AlertTriangle, Flame, Anvil, Boxes } from "lucide-react";
import { rarityOf } from "@/components/shop/shopRarity";

export const fmtDur = (secs) => {
  secs = Math.max(0, Math.floor(secs));
  const h = String(Math.floor(secs / 3600)).padStart(2, "0");
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
  const s = String(secs % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
};

const STATUS_META = {
  CRAFTABLE: { label: "Forjable", cls: "bg-amber-500/20 text-amber-300 border-amber-400/40", icon: Hammer },
  MISSING: { label: "Faltan materiales", cls: "bg-red-500/15 text-red-300 border-red-400/30", icon: AlertTriangle },
  CRAFTING: { label: "En la fragua", cls: "bg-orange-500/20 text-orange-300 border-orange-400/40", icon: Flame },
  READY: { label: "¡Lista!", cls: "bg-emerald-500/25 text-emerald-200 border-emerald-400/60", icon: Sparkles },
  OWNED: { label: "En bóveda", cls: "bg-white/10 text-white/60 border-white/15", icon: Check },
};

export function StatusBadge({ status, className = "" }) {
  const m = STATUS_META[status] || STATUS_META.MISSING;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded border ${m.cls} ${className}`}>
      <Icon size={9} className={status === "CRAFTING" ? "animate-pulse" : ""} /> {m.label}
    </span>
  );
}

function Rivets() {
  return <>
    <span className="forge-rivet" style={{ top: 8, left: 8 }} /><span className="forge-rivet" style={{ top: 8, right: 8 }} />
    <span className="forge-rivet" style={{ bottom: 8, left: 8 }} /><span className="forge-rivet" style={{ bottom: 8, right: 8 }} />
  </>;
}

function jobProgress(job, now) {
  const s = new Date(job.started_at).getTime(), f = new Date(job.finish_at).getTime();
  const total = Math.max(1, f - s), left = Math.max(0, f - now);
  return { pct: ((total - left) / total) * 100, leftSecs: left / 1000, done: left <= 0 };
}

function HeatBar({ pct }) {
  return (
    <div className="h-2.5 rounded-full bg-black/50 overflow-hidden border border-amber-500/20">
      <div className="h-full rounded-full forge-progress transition-[width] duration-1000 ease-linear"
        style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: "linear-gradient(90deg,#FF5500,#F59E0B,#FCD34D)" }} />
    </div>
  );
}

// ═══════════ Bandeja de suministros (materiales) ═══════════
export function MaterialsTray({ materials, qtyOf }) {
  return (
    <div className="relative forge-panel rounded-2xl border border-amber-500/20 p-3.5" data-testid="materials-bar">
      <Rivets />
      <h3 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.2em] text-amber-400/90 mb-3"><Boxes size={14} /> Suministros</h3>
      <div className="grid grid-cols-2 gap-2.5">
        {materials.map((m) => {
          const r = rarityOf(m.rarity);
          return (
            <div key={m.id} data-testid={`material-chip-${m.id}`} className="relative flex items-center gap-2 rounded-xl border p-2 bg-black/30" style={{ borderColor: `${r.color}44` }}>
              <div className="relative h-11 w-11 rounded-lg overflow-hidden shrink-0" style={{ background: `radial-gradient(70% 70% at 50% 40%, ${r.color}44, #07080a)` }}>
                {m.icon && <img src={m.icon} alt={m.name} className="absolute inset-0 w-full h-full object-contain p-0.5" />}
              </div>
              <div className="leading-tight min-w-0">
                <p className="text-[10px] font-bold text-white/70 truncate">{m.name}</p>
                <p className="font-mono font-black tabular-nums text-base" style={{ color: r.color }}>{qtyOf(m.id)}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════ Panel de requisitos + Recibirás ═══════════
export function RequirementsPanel({ recipe, qtyOf, matById }) {
  if (!recipe) return null;
  return (
    <div className="relative forge-panel rounded-2xl border border-amber-500/20 p-3.5">
      <Rivets />
      <h3 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.2em] text-amber-400/90 mb-3"><Anvil size={14} /> Requisitos</h3>
      <div className="space-y-1.5">
        {recipe.materials.map((m) => {
          const meta = matById(m.material_id);
          const have = qtyOf(m.material_id);
          return (
            <div key={m.material_id} data-testid={`req-${m.material_id}`} className="flex items-center gap-2.5 rounded-lg border px-2.5 py-2" style={{ borderColor: m.ok ? "rgba(52,211,153,0.35)" : "rgba(248,113,113,0.35)", background: m.ok ? "rgba(52,211,153,0.06)" : "rgba(248,113,113,0.05)" }}>
              <div className="relative h-8 w-8 rounded-md overflow-hidden shrink-0 bg-black/40">{meta?.icon && <img src={meta.icon} alt="" className="absolute inset-0 w-full h-full object-contain p-0.5" />}</div>
              <span className="flex-1 text-[13px] font-semibold text-white/85 truncate">{meta?.name || m.material_id}</span>
              <span className={`font-mono font-black tabular-nums text-sm ${m.ok ? "text-emerald-300" : "text-red-300"}`}>{have}/{m.required}</span>
              {m.ok ? <Check size={16} className="text-emerald-400" /> : <X size={16} className="text-red-400" />}
            </div>
          );
        })}
      </div>
      <div className="mt-3 rounded-xl border border-amber-500/25 bg-gradient-to-br from-amber-500/10 to-transparent p-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-amber-400/80 mb-1">Recibirás</p>
        <div className="flex items-center justify-between">
          <span className="text-sm font-bold text-white truncate">{recipe.name}</span>
          <span className="text-[11px] font-mono text-emerald-300 shrink-0">{recipe.uses_granted} usos</span>
        </div>
      </div>
    </div>
  );
}

// ═══════════ Escenario central de forja ═══════════
export function ForgeStage({ recipe, now, busy, onCraft, onClaim, onCancel, craftingEnabled }) {
  if (!recipe) return (
    <div className="relative forge-panel rounded-3xl border border-amber-500/20 flex items-center justify-center min-h-[520px]" data-testid="recipe-detail">
      <Rivets />
      <div className="text-center"><Anvil size={44} className="mx-auto text-amber-400/40 mb-3" /><p className="text-sm text-white/45">Selecciona una skin para forjar</p></div>
    </div>
  );
  const r = rarityOf(recipe.rarity);
  const job = recipe.job;
  const isCrafting = recipe.status === "CRAFTING" && job;
  const isReady = recipe.status === "READY" && job;
  const missing = recipe.materials.some((m) => !m.ok);
  const prog = job ? jobProgress(job, now) : null;
  const embers = [8, 20, 33, 46, 58, 70, 82, 92];

  return (
    <div className="relative forge-panel rounded-3xl border overflow-hidden min-h-[520px] flex flex-col" data-testid="recipe-detail"
      style={{ borderColor: `${r.color}55`, boxShadow: `0 30px 90px -34px ${r.color}` }}>
      <Rivets />
      {/* calor molten detrás */}
      <div className="absolute inset-x-0 bottom-0 h-2/3 pointer-events-none heat-glow" style={{ background: `radial-gradient(60% 70% at 50% 100%, ${isCrafting ? "rgba(255,85,0,.5)" : `${r.color}55`}, transparent 72%)` }} />
      <div className="absolute inset-0 pointer-events-none opacity-[0.05]" style={{ backgroundImage: "radial-gradient(#F59E0B 1px, transparent 1px)", backgroundSize: "26px 26px" }} />
      {/* embers solo cuando forja o siempre suaves */}
      {embers.map((l, i) => <span key={i} className="ember" style={{ left: `${l}%`, animationDelay: `${i * 0.38}s`, opacity: isCrafting ? 1 : 0.5 }} />)}

      <div className="relative flex-1 flex flex-col items-center justify-center p-6 sm:p-8">
        <div className="absolute top-4 right-4"><StatusBadge status={recipe.status} /></div>
        {/* render grande sobre yunque */}
        <div className="relative">
          <div className="absolute -inset-6 rounded-full heat-glow" style={{ background: `radial-gradient(circle, ${r.color}44, transparent 66%)` }} />
          <AnimatePresence mode="wait">
            <motion.div key={recipe.id} initial={{ opacity: 0, y: 20, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="relative w-56 h-56 sm:w-64 sm:h-64 lg:w-72 lg:h-72">
              <img src={recipe.image_url} alt={recipe.name} className="relative w-full h-full object-contain drop-shadow-[0_10px_30px_rgba(0,0,0,.7)]" />
            </motion.div>
          </AnimatePresence>
          <div className="forge-anvil-base absolute -bottom-3 left-1/2 -translate-x-1/2 w-52 h-7 rounded-[100%]" />
        </div>
        {/* identidad */}
        <h2 className="mt-6 font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-none text-center molten-text" style={{ color: "#FDE9C8" }}>{recipe.name}</h2>
        <div className="flex flex-wrap items-center justify-center gap-2 mt-3">
          <span className="text-[11px] font-black uppercase tracking-widest px-2.5 py-1 rounded" style={{ color: "#0a0b0f", background: r.color }}>{r.label}</span>
          {recipe.dino && <span className="text-[11px] font-semibold uppercase tracking-wide text-white/65 border border-white/12 rounded px-2.5 py-1">{recipe.dino}</span>}
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-amber-300"><Clock size={12} /> {fmtDur(recipe.crafting_time)}</span>
          <span className="text-[11px] font-mono text-emerald-300">{recipe.uses_granted} usos</span>
        </div>
      </div>

      {/* barra de acción de forja */}
      <div className="relative border-t border-white/8 bg-black/40 p-5">
        {isCrafting ? (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs"><span className="inline-flex items-center gap-1.5 text-orange-300 font-black uppercase tracking-wide"><Flame size={14} className="animate-pulse" /> Forjando…</span><span className="font-mono text-white/80">{fmtDur(prog.leftSecs)}</span></div>
            <HeatBar pct={prog.pct} />
            <button data-testid="detail-cancel-btn" disabled={busy[job.id]} onClick={() => onCancel(job.id)} className="w-full py-2.5 rounded-xl text-xs font-bold uppercase text-red-300 border border-red-400/30 hover:bg-red-500/10 transition">Cancelar forja</button>
          </div>
        ) : isReady ? (
          <button data-testid="detail-claim-btn" disabled={busy[job.id]} onClick={() => onClaim(job.id)}
            className="w-full inline-flex items-center justify-center gap-2 py-4 rounded-xl font-black uppercase tracking-widest text-black bg-gradient-to-r from-emerald-400 to-emerald-300 hover:brightness-105 disabled:opacity-60 transition craft-ready-pulse">
            {busy[job.id] ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />} Reclamar skin
          </button>
        ) : (
          <button data-testid="craft-btn" disabled={missing || busy[recipe.id] || !craftingEnabled} onClick={() => onCraft(recipe.id)}
            className="group relative w-full inline-flex items-center justify-center gap-2.5 py-4 rounded-xl font-black uppercase tracking-widest text-black overflow-hidden transition disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110"
            style={{ background: missing ? "#2a2f3a" : "linear-gradient(135deg,#FCD34D,#F59E0B 45%,#FF5500)", boxShadow: missing ? "none" : "0 14px 40px -12px rgba(255,85,0,.8)" }}>
            {busy[recipe.id] ? <Loader2 size={20} className="animate-spin" /> : <Hammer size={20} className="transition-transform group-hover:-rotate-12" />}
            {!craftingEnabled ? "Forja deshabilitada" : missing ? "Materiales insuficientes" : "Forjar skin"}
          </button>
        )}
      </div>
    </div>
  );
}

// ═══════════ Rail de recetas (selector) ═══════════
export function RecipeCard({ recipe, selected, onClick }) {
  const r = rarityOf(recipe.rarity);
  return (
    <motion.button layout data-testid={`recipe-card-${recipe.id}`} onClick={() => onClick(recipe)} whileHover={{ x: 3 }}
      className={`group relative w-full flex items-center gap-3 rounded-xl border p-2 text-left transition-colors ${selected ? "bg-amber-400/10 ring-1 ring-amber-400/60" : "bg-black/30 hover:bg-white/5"}`}
      style={{ borderColor: `${r.color}44` }}>
      <div className="relative h-14 w-14 rounded-lg overflow-hidden shrink-0" style={{ background: `radial-gradient(75% 65% at 50% 35%, ${r.color}55, #07080a 92%)` }}>
        <img src={recipe.image_url} alt={recipe.name} loading="lazy" className="absolute inset-0 w-full h-full object-contain p-1 transition-transform duration-500 group-hover:scale-110" />
        {recipe.status === "CRAFTING" && <><span className="forge-ember" style={{ left: "40%" }} /><span className="forge-ember" style={{ left: "62%", animationDelay: ".5s" }} /></>}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-display font-black uppercase tracking-tight text-[13px] truncate text-white">{recipe.name}</p>
        <p className="text-[10px] text-white/45 truncate">{recipe.dino}</p>
        <div className="mt-1"><StatusBadge status={recipe.status} /></div>
      </div>
      <span className="w-1.5 self-stretch rounded-full shrink-0" style={{ background: selected ? r.color : "transparent" }} />
    </motion.button>
  );
}

// ═══════════ Cola de forja (hornos) ═══════════
export function CraftQueue({ jobs, now, busy, onClaim, onCancel }) {
  const ready = jobs.filter((j) => j.status === "COMPLETED" || jobProgress(j, now).done);
  return (
    <div className="space-y-2.5" data-testid="craft-queue">
      {jobs.length === 0 && <div className="text-center py-8"><Flame size={26} className="mx-auto text-amber-400/30 mb-2" /><p className="text-xs text-white/40">La fragua está en reposo.</p></div>}
      {jobs.map((j) => {
        const r = rarityOf(j.recipe?.rarity);
        const { pct, leftSecs, done } = jobProgress(j, now);
        const isReady = j.status === "COMPLETED" || done;
        return (
          <div key={j.id} data-testid={`queue-job-${j.id}`} className={`relative rounded-xl border p-2.5 bg-black/40 overflow-hidden ${isReady ? "craft-ready-pulse" : ""}`} style={{ borderColor: isReady ? "rgba(52,211,153,0.5)" : `${r.color}40` }}>
            {!isReady && <span className="ember" style={{ left: "12%" }} />}
            <div className="flex items-center gap-2.5">
              <div className="relative h-11 w-11 rounded-lg overflow-hidden shrink-0" style={{ background: `radial-gradient(70% 70% at 50% 40%, ${isReady ? "rgba(16,185,129,.4)" : "rgba(255,85,0,.4)"}, #07080a)` }}>
                <img src={j.recipe?.image_url} alt="" className="absolute inset-0 w-full h-full object-contain p-0.5" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-black uppercase tracking-tight text-white truncate">{j.recipe?.name}</p>
                <p className="text-[10px] font-mono" style={{ color: isReady ? "#34D399" : "#fb923c" }}>{isReady ? "¡Lista para reclamar!" : `Restante ${fmtDur(leftSecs)}`}</p>
              </div>
              {isReady ? (
                <button data-testid={`claim-btn-${j.id}`} disabled={busy[j.id]} onClick={() => onClaim(j.id)} className="inline-flex items-center gap-1 text-[11px] font-black uppercase px-3 py-2 rounded-lg text-black bg-emerald-400 hover:bg-emerald-300 disabled:opacity-60 transition-colors">
                  {busy[j.id] ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Reclamar
                </button>
              ) : (
                <button data-testid={`cancel-btn-${j.id}`} disabled={busy[j.id]} onClick={() => onCancel(j.id)} className="p-2 rounded-lg text-white/40 hover:text-red-300 hover:bg-red-500/10 transition-colors"><X size={16} /></button>
              )}
            </div>
            {!isReady && <div className="mt-2"><HeatBar pct={pct} /></div>}
          </div>
        );
      })}
      {ready.length > 1 && (
        <button data-testid="claim-all-btn" onClick={() => ready.forEach((j) => onClaim(j.id))} className="w-full py-3 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-emerald-400 to-emerald-300 hover:brightness-105 transition">
          Reclamar todo ({ready.length})
        </button>
      )}
    </div>
  );
}
