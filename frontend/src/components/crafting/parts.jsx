import React from "react";
import { motion } from "framer-motion";
import { Check, X, Hammer, Clock, Loader2, PackageCheck, Sparkles, AlertTriangle } from "lucide-react";
import { rarityOf } from "@/components/shop/shopRarity";

export const fmtDur = (secs) => {
  secs = Math.max(0, Math.floor(secs));
  const h = String(Math.floor(secs / 3600)).padStart(2, "0");
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
  const s = String(secs % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
};

const STATUS_META = {
  CRAFTABLE: { label: "Fabricable", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-400/40", icon: Hammer },
  MISSING: { label: "Faltan materiales", cls: "bg-red-500/15 text-red-300 border-red-400/30", icon: AlertTriangle },
  CRAFTING: { label: "Fabricando", cls: "bg-amber-500/20 text-amber-300 border-amber-400/40", icon: Loader2 },
  READY: { label: "¡Lista!", cls: "bg-emerald-500/25 text-emerald-200 border-emerald-400/60", icon: Sparkles },
  OWNED: { label: "En tu bóveda", cls: "bg-white/10 text-white/60 border-white/15", icon: PackageCheck },
};

export function StatusBadge({ status, className = "" }) {
  const m = STATUS_META[status] || STATUS_META.MISSING;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md border ${m.cls} ${className}`}>
      <Icon size={9} className={status === "CRAFTING" ? "animate-spin" : ""} /> {m.label}
    </span>
  );
}

export function MaterialsBar({ materials, qtyOf }) {
  return (
    <div className="flex flex-wrap items-center gap-2.5" data-testid="materials-bar">
      {materials.map((m) => {
        const r = rarityOf(m.rarity);
        return (
          <div key={m.id} data-testid={`material-chip-${m.id}`}
            className="group flex items-center gap-2 rounded-xl border pl-1.5 pr-3 py-1.5 bg-[#0d0f14]/80"
            style={{ borderColor: `${r.color}44` }}>
            <div className="relative h-9 w-9 rounded-lg overflow-hidden shrink-0" style={{ background: `radial-gradient(70% 70% at 50% 40%, ${r.color}44, #07080a)` }}>
              {m.icon ? <img src={m.icon} alt={m.name} className="absolute inset-0 w-full h-full object-contain p-0.5" /> : null}
            </div>
            <div className="leading-tight">
              <p className="text-[11px] font-bold text-white/85 whitespace-nowrap">{m.name}</p>
              <p className="font-code font-black tabular-nums text-sm" style={{ color: r.color }}>{qtyOf(m.id)}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function RecipeCard({ recipe, selected, onClick }) {
  const r = rarityOf(recipe.rarity);
  return (
    <motion.button layout data-testid={`recipe-card-${recipe.id}`} onClick={() => onClick(recipe)}
      whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 320, damping: 22 }}
      className={`group relative w-full text-left rounded-2xl overflow-hidden border transition-colors ${selected ? "ring-2 ring-amber-400/70" : ""}`}
      style={{ borderColor: `${r.color}55`, background: "#0a0b0f", boxShadow: `0 18px 50px -30px ${r.color}` }}>
      <div className="relative aspect-square overflow-hidden">
        <div className="absolute inset-0" style={{ background: `radial-gradient(75% 60% at 50% 30%, ${r.color}55, #07080a 92%)` }} />
        <img src={recipe.image_url} alt={recipe.name} loading="lazy" className="absolute inset-0 w-full h-full object-contain p-3 drop-shadow-xl transition-transform duration-500 group-hover:scale-105" />
        <div className="absolute top-2 left-2"><StatusBadge status={recipe.status} /></div>
        <span className="absolute top-2 right-2 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md" style={{ color: "#0a0b0f", background: r.color }}>{r.label}</span>
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/95 to-transparent px-3 pt-6 pb-2.5">
          <p className="font-display font-black uppercase tracking-tight text-[15px] leading-none truncate text-white">{recipe.name}</p>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[10px] text-white/55 truncate">{recipe.dino}</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-code text-amber-300/90"><Clock size={10} /> {fmtDur(recipe.crafting_time)}</span>
          </div>
        </div>
      </div>
    </motion.button>
  );
}

function ProgressBar({ pct, color = "#F59E0B" }) {
  return (
    <div className="h-2 rounded-full bg-white/10 overflow-hidden">
      <div className="h-full rounded-full transition-[width] duration-1000 ease-linear" style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: `linear-gradient(90deg, ${color}, #FCD34D)` }} />
    </div>
  );
}

function jobProgress(job, now) {
  const s = new Date(job.started_at).getTime(), f = new Date(job.finish_at).getTime();
  const total = Math.max(1, f - s), left = Math.max(0, f - now);
  return { pct: ((total - left) / total) * 100, leftSecs: left / 1000, done: left <= 0 };
}

export function CraftQueue({ jobs, now, busy, onClaim, onCancel }) {
  const ready = jobs.filter((j) => j.status === "COMPLETED" || jobProgress(j, now).done);
  return (
    <div className="space-y-2.5" data-testid="craft-queue">
      {jobs.length === 0 && <p className="text-xs text-white/40 text-center py-8">No hay crafteos activos.</p>}
      {jobs.map((j) => {
        const r = rarityOf(j.recipe?.rarity);
        const { pct, leftSecs, done } = jobProgress(j, now);
        const isReady = j.status === "COMPLETED" || done;
        return (
          <div key={j.id} data-testid={`queue-job-${j.id}`} className="rounded-xl border p-2.5 bg-[#0d0f14]/80" style={{ borderColor: isReady ? "rgba(52,211,153,0.5)" : `${r.color}40` }}>
            <div className="flex items-center gap-2.5">
              <div className="relative h-11 w-11 rounded-lg overflow-hidden shrink-0" style={{ background: `radial-gradient(70% 70% at 50% 40%, ${r.color}55, #07080a)` }}>
                <img src={j.recipe?.image_url} alt="" className="absolute inset-0 w-full h-full object-contain p-0.5" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-bold text-white truncate">{j.recipe?.name}</p>
                <p className="text-[10px] font-code" style={{ color: isReady ? "#34D399" : "#fbbf24" }}>
                  {isReady ? "¡Lista para reclamar!" : `Restante: ${fmtDur(leftSecs)}`}
                </p>
              </div>
              {isReady ? (
                <button data-testid={`claim-btn-${j.id}`} disabled={busy[j.id]} onClick={() => onClaim(j.id)}
                  className="inline-flex items-center gap-1 text-[11px] font-black uppercase px-3 py-2 rounded-lg text-black bg-emerald-400 hover:bg-emerald-300 disabled:opacity-60 transition-colors">
                  {busy[j.id] ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Reclamar
                </button>
              ) : (
                <button data-testid={`cancel-btn-${j.id}`} disabled={busy[j.id]} onClick={() => onCancel(j.id)}
                  className="p-2 rounded-lg text-white/40 hover:text-red-300 hover:bg-red-500/10 transition-colors" title="Cancelar">
                  <X size={16} />
                </button>
              )}
            </div>
            {!isReady && <div className="mt-2"><ProgressBar pct={pct} color={r.color} /></div>}
          </div>
        );
      })}
      {ready.length > 1 && (
        <button data-testid="claim-all-btn" onClick={() => ready.forEach((j) => onClaim(j.id))}
          className="w-full py-3 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-emerald-400 to-emerald-300 hover:brightness-105 transition">
          Reclamar todo ({ready.length})
        </button>
      )}
    </div>
  );
}

export function RecipeDetail({ recipe, now, busy, qtyOf, matById, onCraft, onClaim, onCancel, craftingEnabled }) {
  if (!recipe) return (
    <div className="flex items-center justify-center h-full min-h-[420px] text-center">
      <div><Hammer size={38} className="mx-auto text-amber-400/50 mb-3" /><p className="text-sm text-white/45">Selecciona una skin para ver la receta</p></div>
    </div>
  );
  const r = rarityOf(recipe.rarity);
  const job = recipe.job;
  const isCrafting = recipe.status === "CRAFTING" && job;
  const isReady = recipe.status === "READY" && job;
  const missing = recipe.materials.some((m) => !m.ok);
  const prog = job ? jobProgress(job, now) : null;

  return (
    <div data-testid="recipe-detail" className="flex flex-col h-full">
      <div className="relative rounded-2xl overflow-hidden border mb-4" style={{ borderColor: `${r.color}55` }}>
        <div className="relative aspect-[16/10]" style={{ background: `radial-gradient(70% 80% at 50% 20%, ${r.color}55, #07080a 92%)` }}>
          <img src={recipe.image_url} alt={recipe.name} className="absolute inset-0 w-full h-full object-contain p-4 drop-shadow-2xl" />
          <span className="absolute top-3 right-3 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md" style={{ color: "#0a0b0f", background: r.color }}>{r.label}</span>
        </div>
      </div>
      <h2 className="font-display font-black uppercase tracking-tighter text-2xl sm:text-3xl leading-none text-white">{recipe.name}</h2>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-white/65 border border-white/12 rounded-md px-2 py-0.5">{recipe.dino}</span>
        <span className="inline-flex items-center gap-1 text-[11px] font-code text-amber-300"><Clock size={12} /> {fmtDur(recipe.crafting_time)}</span>
      </div>

      {/* Recibirás */}
      <div className="mt-4 rounded-xl border border-amber-500/25 bg-white/[0.03] p-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-amber-400/80 mb-1.5">Recibirás</p>
        <div className="flex items-center justify-between">
          <span className="text-sm font-bold text-white">{recipe.name} <span className="text-white/50 font-normal">· skin</span></span>
          <span className="text-[11px] font-code text-emerald-300">{recipe.uses_granted} usos</span>
        </div>
      </div>

      {/* Requisitos */}
      <div className="mt-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-white/50 mb-2">Requisitos</p>
        <div className="space-y-1.5">
          {recipe.materials.map((m) => {
            const meta = matById(m.material_id);
            const have = qtyOf(m.material_id);
            return (
              <div key={m.material_id} data-testid={`req-${m.material_id}`} className="flex items-center gap-2.5 rounded-lg border px-2.5 py-2" style={{ borderColor: m.ok ? "rgba(52,211,153,0.35)" : "rgba(248,113,113,0.35)", background: m.ok ? "rgba(52,211,153,0.06)" : "rgba(248,113,113,0.05)" }}>
                <div className="relative h-8 w-8 rounded-md overflow-hidden shrink-0 bg-black/40">
                  {meta?.icon ? <img src={meta.icon} alt="" className="absolute inset-0 w-full h-full object-contain p-0.5" /> : null}
                </div>
                <span className="flex-1 text-[13px] font-semibold text-white/85 truncate">{meta?.name || m.material_id}</span>
                <span className={`font-code font-black tabular-nums text-sm ${m.ok ? "text-emerald-300" : "text-red-300"}`}>{have} / {m.required}</span>
                {m.ok ? <Check size={16} className="text-emerald-400" /> : <X size={16} className="text-red-400" />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Acción */}
      <div className="mt-auto pt-5">
        {isCrafting ? (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs"><span className="text-amber-300 font-bold uppercase tracking-wide">Fabricando</span><span className="font-code text-white/70">{fmtDur(prog.leftSecs)}</span></div>
            <ProgressBar pct={prog.pct} color={r.color} />
            <button data-testid="detail-cancel-btn" disabled={busy[job.id]} onClick={() => onCancel(job.id)} className="w-full py-2.5 rounded-xl text-xs font-bold uppercase text-red-300 border border-red-400/30 hover:bg-red-500/10 transition">Cancelar crafteo</button>
          </div>
        ) : isReady ? (
          <button data-testid="detail-claim-btn" disabled={busy[job.id]} onClick={() => onClaim(job.id)}
            className="w-full inline-flex items-center justify-center gap-2 py-4 rounded-xl font-black uppercase tracking-wide text-black bg-gradient-to-r from-emerald-400 to-emerald-300 hover:brightness-105 disabled:opacity-60 transition">
            {busy[job.id] ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />} Reclamar skin
          </button>
        ) : (
          <button data-testid="craft-btn" disabled={missing || busy[recipe.id] || !craftingEnabled} onClick={() => onCraft(recipe.id)}
            className="w-full inline-flex items-center justify-center gap-2 py-4 rounded-xl font-black uppercase tracking-wide text-black transition disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-105"
            style={{ background: missing ? "#3a3f4b" : "linear-gradient(135deg,#B8DA7E,#7CA842)" }}>
            {busy[recipe.id] ? <Loader2 size={18} className="animate-spin" /> : <Hammer size={18} />}
            {!craftingEnabled ? "Crafteo deshabilitado" : missing ? "Materiales insuficientes" : "Fabricar (CRAFT)"}
          </button>
        )}
      </div>
    </div>
  );
}
