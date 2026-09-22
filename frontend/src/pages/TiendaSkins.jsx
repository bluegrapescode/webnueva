import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Search, LayoutGrid, List as ListIcon, PackageOpen, Crown, Sparkles, ArrowRight, Gem } from "lucide-react";
import { api, shopWsUrl } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { GalleryCard } from "@/components/shop/GalleryCard";
import { SkinDetailModal } from "@/components/shop/SkinDetailModal";
import { PurchaseCelebration } from "@/components/shop/PurchaseCelebration";
import { RARITY_ORDER, rarityOf } from "@/components/shop/shopRarity";
import { Countdown } from "@/components/shop/Countdown";
import { SkeletonCard } from "@/components/common/PageLoader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SORTS = {
  featured: "Destacados",
  price_desc: "Precio: mayor",
  price_asc: "Precio: menor",
  name: "Nombre A-Z",
  rarity: "Rareza",
};

const RARITY_FLAVOR = {
  common: "Cosmético estándar del servidor.",
  uncommon: "Acabado poco común con detalles mejorados.",
  rare: "Diseño raro con tonalidades exclusivas.",
  epic: "Skin épica de edición especial, muy solicitada.",
  legendary: "Pieza legendaria con acabado premium y brillo único.",
  mythic: "Rareza mítica: de las más exclusivas del catálogo.",
};

// Banner destacado: muestra la skin de mayor prestigio del catálogo.
function FeaturedHero({ skin, onOpen, play }) {
  if (!skin) return null;
  const r = rarityOf(skin.rarity);
  const holo = skin.rarity === "legendary" || skin.rarity === "mythic";
  const sparks = [12, 28, 44, 60, 76, 88];
  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}
      data-testid="hero-skin-banner"
      className="relative overflow-hidden rounded-3xl border border-amber-500/30 p-6 sm:p-9 lg:p-11 min-h-[420px] lg:min-h-[460px]"
      style={{ background: "linear-gradient(135deg,#12141d 0%,#0b0d12 52%,#050608 100%)", boxShadow: "0 26px 90px -30px rgba(245,158,11,0.28)" }}>
      {/* luz dorada + tinte de rareza */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(60% 80% at 82% 30%, ${r.color}33, transparent 65%)` }} />
      <div className="absolute inset-0 pointer-events-none lux-gold-glow" style={{ background: "radial-gradient(45% 60% at 78% 40%, rgba(245,158,11,0.22), transparent 70%)" }} />
      <div className="absolute inset-0 pointer-events-none opacity-[0.06]" style={{ backgroundImage: "radial-gradient(#F59E0B 1px, transparent 1px)", backgroundSize: "22px 22px" }} />

      <div className="relative grid lg:grid-cols-12 gap-6 lg:gap-8 items-center h-full">
        {/* texto */}
        <div className="lg:col-span-7 min-w-0">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-[0.2em] px-3 py-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 text-amber-300">
            <Sparkles size={12} /> Pieza destacada de la vitrina
          </span>
          <h2 className="font-display font-black uppercase tracking-tighter text-4xl sm:text-5xl lg:text-6xl leading-[0.9] mt-4">
            <span className="text-gold-clip">{skin.name}</span>
          </h2>
          <div className="flex flex-wrap items-center gap-2 mt-4">
            <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md" style={{ color: "#0a0b0f", background: r.color }}>
              {holo ? <Crown size={11} /> : <Gem size={11} />} {r.label}
            </span>
            {skin.dino_species && <span className="text-[11px] font-semibold uppercase tracking-wide text-white/60 border border-white/12 rounded-md px-2.5 py-1">{skin.dino_species}</span>}
            {skin.skin_type && <span className="text-[11px] font-semibold uppercase tracking-wide text-white/50">{skin.skin_type}</span>}
          </div>
          <p className="text-sm sm:text-base text-white/60 mt-4 max-w-lg leading-relaxed">{skin.description || RARITY_FLAVOR[skin.rarity] || RARITY_FLAVOR.common}</p>
          {skin.end_at && (
            <p className="text-xs font-code text-amber-300/90 mt-3">Disponible por <Countdown endAt={skin.end_at} className="text-amber-200" /></p>
          )}
          <div className="flex items-center gap-4 mt-7">
            <button data-testid="hero-buy-btn" onClick={() => { play?.("open"); onOpen?.(skin); }}
              className="group inline-flex items-center gap-2 px-6 py-3.5 rounded-xl font-black uppercase tracking-wider text-black transition-transform hover:scale-[1.03] active:scale-95"
              style={{ background: "linear-gradient(135deg,#FCD34D,#F59E0B)", boxShadow: "0 12px 34px -12px rgba(245,158,11,0.9)" }}>
              {skin.owned ? "Ver en tu colección" : "Ver y comprar"} <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </button>
            <div className="leading-none">
              <p className="text-[10px] uppercase tracking-widest text-white/40">Precio</p>
              <p className="font-code font-black text-2xl text-amber-300 mt-0.5">${skin.price_usd.toFixed(2)}</p>
            </div>
          </div>
        </div>

        {/* render flotante */}
        <div className="lg:col-span-5 relative flex items-center justify-center min-h-[220px]">
          <div className="absolute w-64 h-64 rounded-full lux-gold-glow" style={{ background: `radial-gradient(circle, ${r.color}55, transparent 68%)` }} />
          {sparks.map((l, i) => <span key={i} className="lux-spark" style={{ left: `${l}%`, animationDelay: `${i * 0.5}s` }} />)}
          <div className="relative w-56 h-56 sm:w-64 sm:h-64 lg:w-72 lg:h-72 rounded-3xl overflow-hidden border lux-float" style={{ borderColor: `${r.color}66`, boxShadow: `0 0 60px -6px ${r.color}` }}>
            <div className="absolute inset-0" style={{ background: `radial-gradient(70% 60% at 50% 40%, ${r.color}55, #07080a 92%)` }} />
            <img src={skin.image_url} alt={skin.name} className={`absolute inset-0 w-full h-full object-cover ${skin.owned ? "grayscale opacity-80" : ""}`} />
            {holo && <span className="lux-holo pointer-events-none absolute inset-0 opacity-75" aria-hidden />}
            <div className="absolute inset-0 bg-gradient-to-t from-black/45 to-transparent" />
          </div>
        </div>
      </div>
    </motion.section>
  );
}

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

  // Skin destacada del hero: prioriza sección "destacados", luego rareza, luego precio.
  const featured = useMemo(() => {
    if (!items.length) return null;
    const rIdx = (s) => RARITY_ORDER.indexOf(s.rarity);
    return [...items].sort((a, b) => {
      const sa = a.section === "destacados" ? 1 : 0;
      const sb = b.section === "destacados" ? 1 : 0;
      if (sb !== sa) return sb - sa;
      if (rIdx(b) !== rIdx(a)) return rIdx(b) - rIdx(a);
      return b.price_usd - a.price_usd;
    })[0];
  }, [items]);

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
    <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-9"
      style={{ background: "radial-gradient(1200px 500px at 50% -8%, rgba(245,158,11,0.06), transparent 60%)" }}>
      {/* encabezado */}
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-amber-400/90 font-bold">Vitrina de cosméticos · Edición coleccionista</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-4xl sm:text-5xl lg:text-6xl leading-none mt-1">
          <span className="text-gold-clip">Tienda de Skins</span>
        </h1>
        <p className="text-sm sm:text-base text-white/55 mt-2 max-w-2xl leading-relaxed">Piezas exclusivas para tu dinosaurio. Cada rareza brilla distinto — toca cualquier skin para ver el detalle y comprarla con Stripe.</p>
      </motion.div>

      {/* hero destacado */}
      {featured && <FeaturedHero skin={featured} onOpen={openSkin} play={play} />}

      {/* barra de filtros de lujo (glass + oro) */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.1 }}
        className="sticky top-3 z-30 flex flex-col lg:flex-row lg:items-center gap-3 p-3.5 rounded-2xl border border-amber-500/20 shadow-xl"
        style={{ background: "rgba(13,15,20,0.9)", backdropFilter: "blur(18px)", WebkitBackdropFilter: "blur(18px)" }}>
        <div className="flex flex-wrap items-center gap-2.5">
          <Select value={dino} onValueChange={(v) => { setDino(v); play?.("click"); }}>
            <SelectTrigger className="w-[180px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-dino"><SelectValue placeholder="Todos los dinos" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los dinos</SelectItem>
              {(data?.dinos || []).map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={type} onValueChange={(v) => { setType(v); play?.("click"); }}>
            <SelectTrigger className="w-[160px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-type"><SelectValue placeholder="Todas las skins" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas las skins</SelectItem>
              {(data?.types || []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={(v) => { setSort(v); play?.("click"); }}>
            <SelectTrigger className="w-[170px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-sort"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(SORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2.5 lg:ml-auto">
          <div className="relative flex-1 lg:flex-none">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-amber-400/60" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar skins…" data-testid="skin-search"
              className="pl-9 pr-3 py-2.5 rounded-lg bg-white/[0.03] border border-amber-500/20 text-sm w-full lg:w-64 outline-none focus:border-amber-400/50 transition-colors" />
          </div>
          <div className="flex rounded-lg overflow-hidden border border-amber-500/20 shrink-0">
            <button onClick={() => { setView("grid"); play?.("click"); }} data-testid="view-grid" aria-label="Vista cuadrícula"
              className={`p-2.5 transition-colors ${view === "grid" ? "bg-amber-400/20 text-amber-300" : "text-white/45 hover:text-white"}`}><LayoutGrid size={17} /></button>
            <button onClick={() => { setView("list"); play?.("click"); }} data-testid="view-list" aria-label="Vista lista"
              className={`p-2.5 transition-colors ${view === "list" ? "bg-amber-400/20 text-amber-300" : "text-white/45 hover:text-white"}`}><ListIcon size={17} /></button>
          </div>
        </div>
      </motion.div>

      {/* resultados */}
      {!data ? (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-5">
          {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-24">
          <PackageOpen size={40} className="mx-auto text-amber-400/60 mb-4" />
          <p className="text-lg font-bold">No hay skins que coincidan</p>
          <p className="text-sm text-white/45 mt-1">Prueba con otro filtro o búsqueda.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-white/45 font-mono" data-testid="catalog-count">{filtered.length} skins en la vitrina</p>
          {view === "grid" ? (
            <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-5 lg:gap-6" data-testid="skins-grid">
              <AnimatePresence mode="popLayout">
                {filtered.map((s, i) => <GalleryCard key={s.id} skin={s} onClick={openSkin} play={play} view="grid" index={i} />)}
              </AnimatePresence>
            </div>
          ) : (
            <div className="space-y-3" data-testid="skins-list">
              <AnimatePresence mode="popLayout">
                {filtered.map((s, i) => <GalleryCard key={s.id} skin={s} onClick={openSkin} play={play} view="list" index={i} />)}
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
