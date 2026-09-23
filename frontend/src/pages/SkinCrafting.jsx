import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Hammer, Flame, ListChecks } from "lucide-react";
import { CraftingProvider, useCrafting } from "@/context/CraftingContext";
import { MaterialsTray, RecipeCard, CraftQueue, ForgeStage, RequirementsPanel } from "@/components/crafting/parts";
import { useSound } from "@/context/SoundContext";

const TABS = [
  { id: "all", label: "Todas" },
  { id: "carnivore", label: "Carnív." },
  { id: "herbivore", label: "Herbív." },
  { id: "owned", label: "Bóveda" },
  { id: "craftable", label: "Forjables" },
];

function CraftingInner() {
  const { play } = useSound();
  const { state, loading, busy, craft, claim, cancel, qtyOf, matById } = useCrafting();
  const [tab, setTab] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  const recipes = state?.recipes || [];
  const filtered = useMemo(() => recipes.filter((r) => {
    if (tab === "carnivore") return r.diet === "carnivore";
    if (tab === "herbivore") return r.diet === "herbivore";
    if (tab === "owned") return r.status === "OWNED";
    if (tab === "craftable") return r.status === "CRAFTABLE";
    return true;
  }), [recipes, tab]);

  useEffect(() => {
    if (!recipes.length) return;
    setSelectedId((cur) => (cur && recipes.some((r) => r.id === cur)) ? cur : (recipes.find((r) => r.status === "CRAFTABLE") || recipes[0])?.id);
  }, [recipes]);

  const selected = useMemo(() => recipes.find((r) => r.id === selectedId) || null, [recipes, selectedId]);
  const jobs = state?.active_jobs || [];
  const craftingEnabled = state?.settings?.crafting_enabled !== false;

  return (
    <div className="max-w-[1680px] mx-auto px-4 sm:px-6 lg:px-8 py-8" style={{ background: "radial-gradient(1200px 500px at 50% -6%, rgba(255,85,0,0.07), transparent 60%)" }}>
      {/* encabezado */}
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-amber-400/90 font-bold flex items-center gap-2"><Flame size={13} /> Estación de forja · La Isla Nublar</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-none mt-1 flex items-center gap-3">
          <Hammer className="text-amber-400" size={40} /> <span className="text-gold-clip molten-text">Forja de Skins</span>
        </h1>
      </motion.div>

      {loading ? (
        <div className="grid lg:grid-cols-12 gap-6">
          <div className="lg:col-span-3 h-[520px] rounded-2xl bg-white/[0.03] animate-pulse" />
          <div className="lg:col-span-6 h-[520px] rounded-3xl bg-white/[0.03] animate-pulse" />
          <div className="lg:col-span-3 h-[520px] rounded-2xl bg-white/[0.03] animate-pulse" />
        </div>
      ) : (
        <div className="grid lg:grid-cols-12 gap-6">
          {/* IZQUIERDA: cola (hornos) + rail de recetas */}
          <aside className="lg:col-span-3 order-2 lg:order-1 space-y-5">
            <div className="relative forge-panel rounded-2xl border border-orange-500/20 p-4">
              <h3 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.2em] text-orange-300/90 mb-3"><Flame size={14} /> Fragua activa</h3>
              <CraftQueue jobs={jobs} now={now} busy={busy} onClaim={claim} onCancel={cancel} />
            </div>
            <div className="forge-panel rounded-2xl border border-amber-500/20 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.2em] text-amber-400/90"><ListChecks size={14} /> Recetas</h3>
              </div>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {TABS.map((t) => (
                  <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => { setTab(t.id); play?.("click"); }}
                    className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wide transition-colors ${tab === t.id ? "bg-amber-400 text-black" : "bg-white/[0.04] text-white/50 hover:text-white border border-white/10"}`}>{t.label}</button>
                ))}
              </div>
              {filtered.length === 0 ? (
                <p className="text-center text-white/45 text-sm py-8">Sin recetas aquí.</p>
              ) : (
                <div className="space-y-2 lg:max-h-[440px] lg:overflow-y-auto lg:pr-1" data-testid="recipe-grid">
                  {filtered.map((r) => (
                    <RecipeCard key={r.id} recipe={r} selected={r.id === selectedId} onClick={(rr) => { setSelectedId(rr.id); play?.("open"); }} />
                  ))}
                </div>
              )}
            </div>
          </aside>

          {/* CENTRO: escenario de forja */}
          <section className="lg:col-span-6 order-1 lg:order-2">
            <ForgeStage recipe={selected} now={now} busy={busy} onCraft={craft} onClaim={claim} onCancel={cancel} craftingEnabled={craftingEnabled} />
          </section>

          {/* DERECHA: suministros + requisitos */}
          <aside className="lg:col-span-3 order-3 space-y-5 lg:sticky lg:top-6 self-start">
            <MaterialsTray materials={state?.materials || []} qtyOf={qtyOf} />
            <RequirementsPanel recipe={selected} qtyOf={qtyOf} matById={matById} />
          </aside>
        </div>
      )}
    </div>
  );
}

export default function SkinCrafting() {
  return <CraftingProvider><CraftingInner /></CraftingProvider>;
}
