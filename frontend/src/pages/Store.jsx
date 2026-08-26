import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, LayoutGrid, Beef, Leaf, CircleDot } from "lucide-react";
import { api } from "@/lib/api";
import { SkeletonCard } from "@/components/common/PageLoader";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { DinoPurchaseModal } from "@/components/store/DinoPurchaseModal";
import { RarityBadge, TYPE_COLORS } from "@/components/common/RarityBadge";
import { MEDIA } from "@/lib/media";

const PRIME_SURCHARGE = 1000;
const DIET_COLOR = { Carnivore: "#E24A4A", Herbivore: "#34D399", Omnivore: "#7CA842" };
const CATS = [
  { k: "All", label: "Todos", icon: LayoutGrid },
  { k: "Carnivore", label: "Carnívoro", icon: Beef },
  { k: "Herbivore", label: "Herbívoro", icon: Leaf },
  { k: "Omnivore", label: "Omnívoro", icon: CircleDot },
];
const DIET_LABEL = { Carnivore: "Carnívoro", Herbivore: "Herbívoro", Omnivore: "Omnívoro" };
const SORTS = [
  { k: "recommended", label: "Recomendado" },
  { k: "price-asc", label: "Precio: menor a mayor" },
  { k: "price-desc", label: "Precio: mayor a menor" },
  { k: "name", label: "Nombre (A–Z)" },
];
const RARITY_RANK = { Common: 0, Uncommon: 1, Rare: 2, Epic: 3, Legendary: 4, Mythic: 5, Apex: 6 };

function Shard({ className = "" }) {
  return <img src={MEDIA.coinVip} alt="Amberium" className={`inline-block w-4 h-4 object-contain drop-shadow ${className}`} />;
}

function PriceBox({ label, amount, prime, onClick, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className={`flex-1 rounded-[2px] py-2 px-2 border transition-all group/price ${prime ? "border-gold/50 bg-gold/[0.06] hover:bg-gold/15" : "border-white/10 bg-white/[0.02] hover:bg-white/[0.06]"}`}>
      <p className={`text-[9px] font-bold uppercase tracking-widest mb-1 ${prime ? "text-gold/80" : "text-muted-foreground"}`}>{label}</p>
      <p className={`inline-flex items-center gap-1.5 font-display font-bold text-sm tabular-nums ${prime ? "text-gold" : "text-foreground"}`}>
        <Shard /> {amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
      </p>
    </button>
  );
}

export default function Store() {
  const { play } = useSound();
  const { user, refresh } = useAuth();
  const [search, setSearch] = useState("");
  const [items, setItems] = useState(null);
  const [cat, setCat] = useState("All");
  const [sort, setSort] = useState("recommended");
  const [dinoBuy, setDinoBuy] = useState(null); // { item, tier }

  const load = () => {
    setItems(null);
    api.storeItems({ category: "Dinosaurs", search: search || undefined }).then((r) => setItems(r.data)).catch(() => setItems([]));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { const t = setTimeout(load, 350); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [search]);

  const counts = useMemo(() => {
    const c = { All: items?.length || 0, Carnivore: 0, Herbivore: 0, Omnivore: 0 };
    (items || []).forEach((i) => { if (c[i.type] !== undefined) c[i.type] += 1; });
    return c;
  }, [items]);

  const visible = useMemo(() => {
    let list = (items || []).filter((i) => cat === "All" || i.type === cat);
    if (sort === "price-asc") list = [...list].sort((a, b) => a.price - b.price);
    else if (sort === "price-desc") list = [...list].sort((a, b) => b.price - a.price);
    else if (sort === "name") list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    else if (sort === "recommended") list = [...list].sort((a, b) => (b.featured - a.featured) || ((RARITY_RANK[b.rarity] || 0) - (RARITY_RANK[a.rarity] || 0)));
    return list;
  }, [items, cat, sort]);

  const balance = (cur) => (cur === "vip" ? user?.vip_coins : user?.coins) ?? 0;
  const openBuy = (item, tier) => { play("open"); setDinoBuy({ item, tier }); };

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="label-overline text-xs text-gold mb-2">La Tienda</p>
          <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Tienda de Dinos</h1>
          <p className="text-muted-foreground mt-3 max-w-lg">Compra dinos con <span className="text-gold font-semibold">Amberium</span>. Elige mutaciones y Prime al pagar.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-52">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar especie…" data-testid="store-search"
              className="w-full glass rounded-[2px] pl-9 pr-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/40" />
          </div>
          <select value={sort} onChange={(e) => setSort(e.target.value)} data-testid="store-sort"
            className="glass rounded-[2px] px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/40 cursor-pointer [&>option]:bg-background">
            {SORTS.map((s) => <option key={s.k} value={s.k}>{s.label}</option>)}
          </select>
        </div>
      </motion.div>

      {/* Category tabs */}
      <div className="flex flex-wrap gap-2.5 mt-8" data-testid="store-cats">
        {CATS.map((c) => {
          const sel = cat === c.k;
          return (
            <button key={c.k} onClick={() => { setCat(c.k); play("click"); }} data-testid={`store-cat-${c.k.toLowerCase()}`}
              className={`inline-flex items-center gap-2 pl-3 pr-2.5 py-2 rounded-[2px] text-xs font-bold uppercase tracking-wider transition-all border ${sel ? "border-gold/50 bg-gold/10 text-gold" : "border-white/10 text-muted-foreground hover:text-foreground hover:border-gold/30"}`}>
              <c.icon size={14} /> {c.label}
              <span className={`ml-1 text-[10px] px-1.5 py-0.5 rounded-full ${sel ? "bg-gold/20 text-gold" : "bg-white/[0.06] text-muted-foreground"}`}>{counts[c.k] ?? 0}</span>
            </button>
          );
        })}
        <span className="ml-auto self-center label-overline text-[10px] text-muted-foreground">{visible.length} especies</span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 mt-8" data-testid="store-grid">
        {items === null
          ? Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} className="aspect-[3/4]" />)
          : visible.length === 0
          ? <p className="text-muted-foreground col-span-full py-12 text-center">No se encontraron dinosaurios.</p>
          : visible.map((item, i) => {
              const dc = DIET_COLOR[item.type] || "#7CA842";
              return (
                <motion.div key={item.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: Math.min(i * 0.04, 0.35) }}
                  className="group glass rounded-[2px] overflow-hidden flex flex-col hover:border-gold/30 hover:-translate-y-1 transition-all duration-300"
                  data-testid={`store-item-${item.id}`}>
                  {/* image */}
                  <button onClick={() => openBuy(item, "basic")} className="relative aspect-[4/3] overflow-hidden block" aria-label={`Ver ${item.name}`}>
                    <div className="absolute inset-0" style={{ background: `radial-gradient(72% 72% at 50% 42%, ${dc}20, transparent 70%)` }} />
                    <img src={item.image} alt={item.name} className="relative w-full h-full object-contain p-4 group-hover:scale-105 transition-transform duration-500" />
                    <span className="absolute top-3 left-3 z-10"><RarityBadge rarity={item.rarity} /></span>
                    <div className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-background/80 to-transparent" />
                  </button>
                  {/* body */}
                  <div className="p-4 pt-3 flex flex-col flex-1">
                    <span className={`label-overline text-[10px] ${TYPE_COLORS[item.type] || "text-muted-foreground"}`}>{DIET_LABEL[item.type] || item.type || "Dinosaurio"}</span>
                    <h3 className="font-display font-bold text-lg leading-tight mb-3 mt-0.5">{item.name.replace(/ Slot$/, "")}</h3>
                    <div className="flex gap-2 mt-auto">
                      <PriceBox label="Normal" amount={item.price} onClick={() => openBuy(item, "basic")} testid={`buy-normal-${item.id}`} />
                      <PriceBox label="Prime" prime amount={item.price + PRIME_SURCHARGE} onClick={() => openBuy(item, "prime")} testid={`buy-prime-${item.id}`} />
                    </div>
                  </div>
                </motion.div>
              );
            })}
      </div>

      <AnimatePresence>
        {dinoBuy && (
          <DinoPurchaseModal
            item={dinoBuy.item}
            initialTier={dinoBuy.tier}
            balance={balance}
            play={play}
            onClose={() => setDinoBuy(null)}
            onPurchased={async () => { await refresh(); setDinoBuy(null); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
