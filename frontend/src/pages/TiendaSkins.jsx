import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Search, LayoutGrid, List as ListIcon, PackageOpen } from "lucide-react";
import { api, shopWsUrl } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { GalleryCard } from "@/components/shop/GalleryCard";
import { SkinDetailModal } from "@/components/shop/SkinDetailModal";
import { PurchaseCelebration } from "@/components/shop/PurchaseCelebration";
import { RARITY_ORDER } from "@/components/shop/shopRarity";
import { SkeletonCard } from "@/components/common/PageLoader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SORTS = {
  featured: "Destacados",
  price_desc: "Precio: mayor",
  price_asc: "Precio: menor",
  name: "Nombre A-Z",
  rarity: "Rareza",
};

export default function TiendaSkins() {
  const { play } = useSound();
  const { refresh } = useAuth();
  const [data, setData] = useState(null); // { items, dinos, types }
  const [selected, setSelected] = useState(null);
  const [celebrate, setCelebrate] = useState(null);
  const [dino, setDino] = useState("all");
  const [type, setType] = useState("all");
  const [sort, setSort] = useState("featured");
  const [q, setQ] = useState("");
  const [view, setView] = useState("grid");

  const load = useCallback(async () => {
    try { const { data } = await api.shopCatalog(); setData(data); }
    catch { setData({ items: [], dinos: [], types: [] }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(shopWsUrl());
      ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg.type === "shop_update") load();
        else if (msg.type === "purchase_success") {
          setCelebrate({ id: msg.skin_id, name: msg.name, image_url: msg.image_url, rarity: msg.rarity });
          load(); refresh?.();
        }
      };
      const ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch {} }, 25000);
      ws._ping = ping;
    } catch {}
    return () => { try { clearInterval(ws?._ping); ws?.close(); } catch {} };
  }, [load, refresh]);

  const items = data?.items || [];
  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    let out = items.filter((s) =>
      (dino === "all" || s.dino_species === dino) &&
      (type === "all" || s.skin_type === type) &&
      (!term || s.name.toLowerCase().includes(term) || (s.dino_species || "").toLowerCase().includes(term)));
    const rIdx = (r) => RARITY_ORDER.indexOf(r);
    out = [...out].sort((a, b) => {
      if (sort === "price_desc") return b.price_usd - a.price_usd;
      if (sort === "price_asc") return a.price_usd - b.price_usd;
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "rarity") return rIdx(b.rarity) - rIdx(a.rarity);
      return 0; // featured = backend order (newest first)
    });
    return out;
  }, [items, dino, type, sort, q]);

  const openSkin = (s) => { play?.("open"); setSelected(s); };

  return (
    <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-10">
      {/* header */}
      <div className="mb-7">
        <p className="label-overline text-xs text-gold">Cosméticos del servidor</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-4xl sm:text-5xl leading-none">Catálogo de Skins</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-xl">Explora todas las skins disponibles por especie. Toca cualquiera para ver el detalle y comprarla con Stripe.</p>
      </div>

      {/* filter bar */}
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-6">
        <div className="flex flex-wrap items-center gap-2.5">
          <Select value={dino} onValueChange={(v) => { setDino(v); play?.("click"); }}>
            <SelectTrigger className="w-[180px] bg-white/[0.03] border-white/10" data-testid="filter-dino"><SelectValue placeholder="Todos los dinos" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los dinos</SelectItem>
              {(data?.dinos || []).map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={type} onValueChange={(v) => { setType(v); play?.("click"); }}>
            <SelectTrigger className="w-[160px] bg-white/[0.03] border-white/10" data-testid="filter-type"><SelectValue placeholder="Todas las skins" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas las skins</SelectItem>
              {(data?.types || []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={(v) => { setSort(v); play?.("click"); }}>
            <SelectTrigger className="w-[170px] bg-white/[0.03] border-white/10" data-testid="filter-sort"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(SORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2.5 lg:ml-auto">
          <div className="relative flex-1 lg:flex-none">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar skins…" data-testid="skin-search"
              className="pl-9 pr-3 py-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-sm w-full lg:w-64 outline-none focus:border-gold/50" />
          </div>
          <div className="flex rounded-lg overflow-hidden border border-white/10 shrink-0">
            <button onClick={() => { setView("grid"); play?.("click"); }} data-testid="view-grid" aria-label="Vista cuadrícula"
              className={`p-2.5 transition-colors ${view === "grid" ? "bg-gold/20 text-gold" : "text-muted-foreground hover:text-foreground"}`}><LayoutGrid size={17} /></button>
            <button onClick={() => { setView("list"); play?.("click"); }} data-testid="view-list" aria-label="Vista lista"
              className={`p-2.5 transition-colors ${view === "list" ? "bg-gold/20 text-gold" : "text-muted-foreground hover:text-foreground"}`}><ListIcon size={17} /></button>
          </div>
        </div>
      </div>

      {/* results */}
      {!data ? (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-24">
          <PackageOpen size={40} className="mx-auto text-muted-foreground mb-4" />
          <p className="text-lg font-bold">No hay skins que coincidan</p>
          <p className="text-sm text-muted-foreground mt-1">Prueba con otro filtro o búsqueda.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground mb-3 font-mono" data-testid="catalog-count">{filtered.length} skins</p>
          {view === "grid" ? (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4" data-testid="skins-grid">
              <AnimatePresence mode="popLayout">
                {filtered.map((s) => <GalleryCard key={s.id} skin={s} onClick={openSkin} play={play} view="grid" />)}
              </AnimatePresence>
            </div>
          ) : (
            <div className="space-y-2" data-testid="skins-list">
              <AnimatePresence mode="popLayout">
                {filtered.map((s) => <GalleryCard key={s.id} skin={s} onClick={openSkin} play={play} view="list" />)}
              </AnimatePresence>
            </div>
          )}
        </>
      )}

      <SkinDetailModal skin={selected} open={!!selected} onClose={() => setSelected(null)} play={play}
        onEquipped={() => { load(); refresh?.(); }} />
      <PurchaseCelebration skin={celebrate} play={play} onDone={() => setCelebrate(null)} />
    </div>
  );
}
