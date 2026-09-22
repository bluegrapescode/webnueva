import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Hammer, ListChecks } from "lucide-react";
import { CraftingProvider, useCrafting } from "@/context/CraftingContext";
import { MaterialsBar, RecipeCard, CraftQueue, RecipeDetail } from "@/components/crafting/parts";
import { useSound } from "@/context/SoundContext";

const TABS = [
  { id: "all", label: "Todas" },
  { id: "carnivore", label: "Carnívoros" },
  { id: "herbivore", label: "Herbívoros" },
  { id: "owned", label: "En bóveda" },
  { id: "craftable", label: "Fabricables" },
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
    setSelectedId((cur) => (cur && recipes.some((r) => r.id === cur)) ? cur
      : (recipes.find((r) => r.status === "CRAFTABLE") || recipes[0])?.id);
  }, [recipes]);

  const selected = useMemo(() => recipes.find((r) => r.id === selectedId) || null, [recipes, selectedId]);
  const jobs = state?.active_jobs || [];
  const craftingEnabled = state?.settings?.crafting_enabled !== false;

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8"
      style={{ background: "radial-gradient(1200px 460px at 50% -8%, rgba(124,168,66,0.08), transparent 60%)" }}>
      {/* encabezado */}
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="mb-5">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-emerald-400/90 font-bold">Estación de fabricación · La Isla Nublar</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-none mt-1 flex items-center gap-3">
          <Hammer className="text-amber-400" size={38} /> <span className="text-gold-clip">Skin Crafting</span>
        </h1>
      </motion.div>

      {/* inventario de materiales */}
      <div className="mb-6"><MaterialsBar materials={state?.materials || []} qtyOf={qtyOf} /></div>

      {loading ? (
        <div className="grid lg:grid-cols-12 gap-6">
          <div className="lg:col-span-3 h-96 rounded-2xl bg-white/[0.03] animate-pulse" />
          <div className="lg:col-span-6 h-96 rounded-2xl bg-white/[0.03] animate-pulse" />
          <div className="lg:col-span-3 h-96 rounded-2xl bg-white/[0.03] animate-pulse" />
        </div>
      ) : (
        <div className="grid lg:grid-cols-12 gap-6">
          {/* IZQUIERDA: cola de crafteo */}
          <aside className="lg:col-span-3 order-2 lg:order-1">
            <div className="rounded-2xl border border-emerald-500/20 bg-[#0b0d12]/70 p-4 lg:sticky lg:top-6">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-white/80 mb-3"><ListChecks size={16} className="text-emerald-400" /> Cola de Crafteo</h3>
              <CraftQueue jobs={jobs} now={now} busy={busy} onClaim={claim} onCancel={cancel} />
            </div>
          </aside>

          {/* CENTRO: tabs + grid */}
          <section className="lg:col-span-6 order-1 lg:order-2">
            <div className="flex flex-wrap gap-2 mb-4">
              {TABS.map((t) => (
                <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => { setTab(t.id); play?.("click"); }}
                  className={`px-4 py-2 rounded-lg text-xs font-black uppercase tracking-wide transition-colors ${tab === t.id ? "bg-amber-400 text-black" : "bg-white/[0.04] text-white/55 hover:text-white border border-white/10"}`}>
                  {t.label}
                </button>
              ))}
            </div>
            {filtered.length === 0 ? (
              <div className="text-center py-20 rounded-2xl border border-white/10"><p className="text-white/50">No hay skins en esta categoría.</p></div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4" data-testid="recipe-grid">
                {filtered.map((r) => (
                  <RecipeCard key={r.id} recipe={r} selected={r.id === selectedId} onClick={(rr) => { setSelectedId(rr.id); play?.("open"); }} />
                ))}
              </div>
            )}
          </section>

          {/* DERECHA: detalle */}
          <aside className="lg:col-span-3 order-3">
            <div className="rounded-2xl border border-amber-500/25 bg-[#0b0d12]/70 p-4 lg:sticky lg:top-6 lg:min-h-[560px] flex flex-col">
              <RecipeDetail recipe={selected} now={now} busy={busy} qtyOf={qtyOf} matById={matById}
                onCraft={craft} onClaim={claim} onCancel={cancel} craftingEnabled={craftingEnabled} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default function SkinCrafting() {
  return <CraftingProvider><CraftingInner /></CraftingProvider>;
}
