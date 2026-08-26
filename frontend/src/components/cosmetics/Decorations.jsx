import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Check, Search, Egg as EggIcon, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { RarityBadge } from "@/components/common/RarityBadge";
import { HudCorners } from "@/components/common/Hud";
import { DecoPreview } from "@/components/cosmetics/deco";

export default function Decorations() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [data, setData] = useState(null);
  const [cat, setCat] = useState("color");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try { const r = await api.cosmeticsCatalog(); setData(r.data); } catch { /* ignore */ }
  };
  useEffect(() => { if (user) load(); }, [user?.id]);

  const counts = useMemo(() => {
    const c = {};
    (data?.items || []).forEach((it) => {
      c[it.category] = c[it.category] || { owned: 0, total: 0 };
      c[it.category].total += 1;
      if (it.owned) c[it.category].owned += 1;
    });
    return c;
  }, [data]);

  if (!data) return <div className="glass rounded-2xl p-10 text-center text-muted-foreground text-sm">Cargando decoraciones…</div>;

  const items = data.items.filter((it) => it.category === cat && (!q || it.name.toLowerCase().includes(q.toLowerCase())));

  const equip = async (it) => {
    if (!it.owned || busy) return;
    setBusy(it.id);
    const willUnequip = it.equipped;
    try {
      await api.cosmeticsEquip(it.category, willUnequip ? null : it.id);
      play(willUnequip ? "close" : "success");
      toast.success(willUnequip ? "Decoración quitada" : `${it.name} equipado`);
      await Promise.all([load(), refresh?.()]);
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo equipar."); }
    finally { setBusy(null); }
  };

  return (
    <div data-testid="decorations-panel">
      {/* Info: eggs open from the inventory */}
      <div className="relative overflow-hidden border border-gold/25 p-4 mb-5 flex items-center gap-3" style={{ borderRadius: 2, background: "linear-gradient(160deg,#14110a,#0a0806)" }}>
        <HudCorners color="rgba(124, 168, 66,0.6)" />
        <EggIcon size={22} className="text-gold shrink-0" />
        <p className="text-xs text-muted-foreground">
          Las decoraciones se consiguen abriendo <span className="text-gold font-semibold">Huevos de Dino</span>. Los huevos se ganan con el <span className="text-foreground">login diario</span> (días 3, 5 y 7), y se abren desde tu <span className="text-gold font-semibold">Inventario</span>.
        </p>
      </div>

      {/* Category tabs */}
      <div className="flex gap-2 flex-wrap mb-4" data-testid="deco-category-tabs">
        {data.categories.map((c) => {
          const cc = counts[c.key] || { owned: 0, total: 0 };
          const active = cat === c.key;
          return (
            <button key={c.key} onClick={() => { setCat(c.key); play("click"); }} data-testid={`deco-tab-${c.key}`}
              className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold transition-all ${active ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`} style={{ borderRadius: 2 }}>
              {c.label}
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${active ? "bg-black/20" : "bg-emerald-500/15 text-emerald-400"}`}>{cc.owned}/{cc.total}</span>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar decoraciones…" data-testid="deco-search"
          className="w-full bg-white/[0.03] border border-white/10 pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:border-gold/40 transition-colors" style={{ borderRadius: 2 }} />
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="deco-grid">
        {items.map((it, i) => (
          <motion.div key={it.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.25) }}
            data-testid={`deco-card-${it.id}`}
            className={`relative overflow-hidden border p-3 flex flex-col items-center gap-3 transition-all ${it.equipped ? "border-emerald-500/60 bg-emerald-500/[0.06]" : it.owned ? "border-white/12 bg-white/[0.02]" : "border-white/[0.06] bg-black/20"}`}
            style={{ borderRadius: 2 }}>
            {it.equipped && <HudCorners color="rgba(52,211,153,0.8)" size={12} />}
            {/* preview */}
            <div className={`w-full h-20 flex items-center justify-center ${!it.owned ? "opacity-40 grayscale" : ""}`}>
              <DecoPreview item={it} size={64} />
              {!it.owned && (
                <div className="absolute top-[42px] left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-black/70 border border-white/15 flex items-center justify-center">
                  <Lock size={14} className="text-muted-foreground" />
                </div>
              )}
            </div>
            <div className="text-center w-full">
              <p className="text-sm font-semibold truncate">{it.name}</p>
              <div className="flex justify-center mt-1"><RarityBadge rarity={it.rarity} /></div>
            </div>
            {/* action */}
            {it.category === "emote" ? (
              <span className={`text-[11px] font-bold uppercase tracking-wide ${it.owned ? "text-emerald-400" : "text-muted-foreground/60"}`}>
                {it.owned ? "Desbloqueado" : "Bloqueado"}
              </span>
            ) : it.owned ? (
              <button onClick={() => equip(it)} disabled={busy === it.id} data-testid={`deco-equip-${it.id}`}
                className={`w-full text-xs font-bold py-2 transition-all ${it.equipped ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/40" : "bg-gold text-background hover:brightness-110"}`} style={{ borderRadius: 2 }}>
                {it.equipped ? <span className="inline-flex items-center justify-center gap-1"><Check size={12} /> Equipado</span> : "Equipar"}
              </button>
            ) : (
              <span className="w-full text-center text-[11px] text-muted-foreground/60 py-2 border border-dashed border-white/10 inline-flex items-center justify-center gap-1" style={{ borderRadius: 2 }}>
                <EggIcon size={12} /> Del Huevo
              </span>
            )}
          </motion.div>
        ))}
      </div>
      {items.length === 0 && <p className="text-center text-muted-foreground text-sm py-10">Sin resultados.</p>}
    </div>
  );
}
