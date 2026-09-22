import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { Search, PackageOpen, Crown, Gem, ShoppingCart, Check, Loader2, Sparkles, ShieldCheck, Layers, Tag, Clock } from "lucide-react";
import { api, shopWsUrl, externalRedirect } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { PurchaseCelebration } from "@/components/shop/PurchaseCelebration";
import { RARITY_ORDER, rarityOf } from "@/components/shop/shopRarity";
import { Countdown } from "@/components/shop/Countdown";
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

// ====== VITRINA (display case) — panel grande maestro ======
function DisplayCase({ skin, busy, equippedNow, onBuy, onEquip }) {
  if (!skin) {
    return (
      <div className="relative rounded-3xl border border-amber-500/20 min-h-[520px] flex items-center justify-center" style={{ background: "linear-gradient(140deg,#101219,#0a0b0f)" }} data-testid="display-empty">
        <div className="text-center">
          <PackageOpen size={40} className="mx-auto text-amber-400/50 mb-3" />
          <p className="text-white/50 text-sm">Selecciona una skin de la vitrina</p>
        </div>
      </div>
    );
  }
  const r = rarityOf(skin.rarity);
  const holo = skin.rarity === "legendary" || skin.rarity === "mythic";
  const mythic = skin.rarity === "mythic";
  const sparks = [10, 24, 40, 56, 72, 86, 94];

  return (
    <div className={`relative overflow-hidden rounded-3xl border ${mythic ? "lux-mythic-aura" : ""}`}
      data-testid="hero-skin-banner"
      style={{ borderColor: `${r.color}55`, background: "linear-gradient(140deg,#12141d 0%,#0b0d12 55%,#050608 100%)", boxShadow: mythic ? undefined : `0 30px 90px -34px ${r.color}` }}>
      {/* iluminación cenital + tinte de rareza */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(70% 55% at 50% -6%, ${r.color}44, transparent 62%)` }} />
      <div className="absolute inset-0 pointer-events-none lux-gold-glow" style={{ background: "radial-gradient(50% 40% at 50% 8%, rgba(245,158,11,0.20), transparent 70%)" }} />
      <div className="absolute inset-0 pointer-events-none opacity-[0.05]" style={{ backgroundImage: "radial-gradient(#F59E0B 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

      <div className="relative p-6 sm:p-9 flex flex-col min-h-[520px]">
        {/* rareza + estado */}
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-md" style={{ color: "#0a0b0f", background: r.color, boxShadow: `0 3px 14px -2px ${r.color}` }}>
            {holo ? <Crown size={12} /> : <Gem size={12} />} {r.label}
          </span>
          {skin.owned && <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-md bg-emerald-500/25 text-emerald-200 border border-emerald-400/50"><Check size={11} /> En tu colección</span>}
        </div>

        {/* render en pedestal */}
        <div className="relative flex-1 flex items-center justify-center py-7 min-h-[260px]">
          <div className="absolute w-72 h-72 rounded-full lux-gold-glow" style={{ background: `radial-gradient(circle, ${r.color}55, transparent 66%)` }} />
          {sparks.map((l, i) => <span key={i} className="lux-spark" style={{ left: `${l}%`, animationDelay: `${i * 0.45}s` }} />)}
          <AnimatePresence mode="wait">
            <motion.div key={skin.id}
              initial={{ opacity: 0, y: 24, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -18, scale: 0.95 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="relative w-60 h-60 sm:w-72 sm:h-72 lg:w-80 lg:h-80 rounded-3xl overflow-hidden border lux-float"
              style={{ borderColor: `${r.color}66`, boxShadow: `0 0 70px -6px ${r.color}` }}>
              <div className="absolute inset-0" style={{ background: `radial-gradient(72% 62% at 50% 40%, ${r.color}55, #07080a 92%)` }} />
              <img src={skin.image_url} alt={skin.name} className={`absolute inset-0 w-full h-full object-cover ${skin.owned ? "grayscale opacity-85" : ""}`} />
              {holo && <span className="lux-holo pointer-events-none absolute inset-0 opacity-75" aria-hidden />}
              <div className="absolute inset-0 bg-gradient-to-t from-black/45 to-transparent" />
            </motion.div>
          </AnimatePresence>
          {/* reflejo/base del pedestal */}
          <div className="absolute bottom-4 w-64 h-8 rounded-[100%] blur-md" style={{ background: `radial-gradient(closest-side, ${r.color}66, transparent)` }} />
        </div>

        {/* identidad */}
        <div>
          <span className="block h-[3px] w-14 rounded-full mb-3" style={{ background: "linear-gradient(90deg,#FEF08A,#F59E0B)", boxShadow: "0 0 12px rgba(245,158,11,0.85)" }} />
          <h2 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-[0.9]" data-testid="display-skin-name">
            <span className="text-gold-clip">{skin.name}</span>
          </h2>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {skin.dino_species && <span className="text-[11px] font-semibold uppercase tracking-wide text-white/65 border border-white/12 rounded-md px-2.5 py-1">{skin.dino_species}</span>}
            {skin.skin_type && <span className="text-[11px] font-semibold uppercase tracking-wide text-white/45">{skin.skin_type}</span>}
          </div>
          <p className="text-sm text-white/60 mt-4 leading-relaxed max-w-xl">{skin.description || RARITY_FLAVOR[skin.rarity] || RARITY_FLAVOR.common}</p>

          {/* atributos */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-5">
            {[
              { icon: Gem, label: "Rareza", value: r.label, accent: true },
              { icon: Layers, label: "Especie", value: skin.dino_species || "Universal" },
              { icon: Tag, label: "Tipo", value: skin.skin_type || "Estándar" },
              { icon: Clock, label: "Disponible", value: skin.end_at ? "Limitada" : "Permanente" },
            ].map((a) => (
              <div key={a.label} className="rounded-xl px-3 py-2.5 border" style={{ background: "rgba(255,255,255,.03)", borderColor: a.accent ? `${r.color}44` : "rgba(245,158,11,.14)" }}>
                <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-white/45"><a.icon size={11} style={a.accent ? { color: r.color } : { color: "#F59E0B" }} /> {a.label}</span>
                <span className="block text-sm font-bold mt-0.5 truncate" style={a.accent ? { color: r.color } : {}}>{a.value}</span>
              </div>
            ))}
          </div>

          {/* perks + disponibilidad */}
          <div className="mt-4 space-y-1.5">
            <span className="flex items-center gap-2 text-xs text-white/65"><ShieldCheck size={14} className="text-amber-400" /> Se aplica a tu {skin.dino_species || "dinosaurio"} en el servidor</span>
            <span className="flex items-center gap-2 text-xs text-white/65 font-code">
              <Clock size={14} className="text-amber-400" />
              {skin.end_at ? <>Disponible por <Countdown endAt={skin.end_at} className="text-amber-200" /></> : "Disponible por tiempo indefinido"}
            </span>
          </div>

          {/* precio + acción */}
          <div className="flex items-end justify-between gap-4 mt-6">
            <div className="leading-none">
              <p className="text-[10px] uppercase tracking-widest text-white/40">Precio</p>
              <p className="font-code font-black text-3xl text-amber-300 mt-1">${skin.price_usd.toFixed(2)}</p>
            </div>
            {skin.owned ? (
              equippedNow ? (
                <button disabled data-testid="skin-equipped-btn"
                  className="inline-flex items-center justify-center gap-2 px-7 py-4 rounded-xl font-black uppercase tracking-wide bg-emerald-500/20 text-emerald-200 border-2 border-emerald-400/50">
                  <Check size={18} /> Equipada
                </button>
              ) : (
                <button onClick={onEquip} disabled={busy} data-testid={`equip-btn-${skin.id}`}
                  className="inline-flex items-center justify-center gap-2 px-7 py-4 rounded-xl font-black uppercase tracking-wide text-black transition-transform hover:scale-[1.03] active:scale-95 disabled:opacity-60"
                  style={{ background: "linear-gradient(135deg,#B8DA7E,#7CA842)" }}>
                  {busy ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />} Equipar al dino
                </button>
              )
            ) : (
              <button onClick={onBuy} disabled={busy} data-testid={`buy-btn-${skin.id}`}
                className="inline-flex items-center justify-center gap-2 px-7 py-4 rounded-xl font-black uppercase tracking-wide text-black transition-transform hover:scale-[1.03] active:scale-95 disabled:opacity-60"
                style={{ background: "linear-gradient(135deg,#FCD34D,#F59E0B)", boxShadow: "0 14px 38px -14px rgba(245,158,11,0.9)" }}>
                {busy ? <Loader2 size={18} className="animate-spin" /> : <ShoppingCart size={18} />}
                {busy ? "Redirigiendo…" : "Comprar con Stripe"}
              </button>
            )}
          </div>
          <p className="text-right text-[10px] text-white/35 mt-2">Pago seguro por Stripe · Skin coleccionable ligada a tu cuenta</p>
        </div>
      </div>
    </div>
  );
}

// ====== FILA de la lista lateral ======
function SkinRow({ skin, active, onSelect, play }) {
  const r = rarityOf(skin.rarity);
  return (
    <button data-testid={`skin-card-${skin.id}`}
      onMouseEnter={() => play?.("hover")} onClick={() => onSelect(skin)}
      className={`group relative w-full flex items-center gap-3 rounded-xl border p-2.5 text-left transition-colors ${active ? "bg-amber-400/10" : "bg-white/[0.02] hover:bg-white/[0.05]"}`}
      style={{ borderColor: active ? "rgba(245,158,11,0.6)" : `${r.color}33`, boxShadow: active ? `inset 3px 0 0 ${r.color}, 0 0 26px -12px ${r.color}` : `inset 3px 0 0 ${r.color}` }}>
      <div className="relative h-14 w-16 shrink-0 rounded-lg overflow-hidden border border-white/5">
        <div className="absolute inset-0" style={{ background: `radial-gradient(80% 80% at 50% 40%, ${r.color}55, #07080a 90%)` }} />
        <img src={skin.image_url} alt={skin.name} loading="lazy" className={`absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-110 ${skin.owned ? "grayscale opacity-70" : ""}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: r.color, boxShadow: `0 0 8px ${r.color}` }} />
          <p className="font-display font-bold text-sm truncate text-white">{skin.name}</p>
          {skin.owned && <Check size={12} className="text-emerald-400 shrink-0" />}
        </div>
        <p className="text-[11px] text-white/45 truncate mt-0.5">{skin.dino_species || "—"}{skin.skin_type ? ` · ${skin.skin_type}` : ""}</p>
      </div>
      <span className="font-code font-black tabular-nums text-sm shrink-0 pr-1 text-amber-300">${skin.price_usd.toFixed(2)}</span>
    </button>
  );
}

export default function TiendaSkins() {
  const { play } = useSound();
  const { refresh } = useAuth();
  const [data, setData] = useState(null);
  const [celebrate, setCelebrate] = useState(null);
  const [dino, setDino] = useState("all");
  const [type, setType] = useState("all");
  const [sort, setSort] = useState("featured");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [equippedNow, setEquippedNow] = useState(false);

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
      return 0;
    });
    return out;
  }, [items, dino, type, sort, q]);

  // Agrupar por rareza (mítica -> común) respetando el orden ya aplicado.
  const groups = useMemo(() => {
    const byR = {};
    for (const s of filtered) (byR[s.rarity] ||= []).push(s);
    return [...RARITY_ORDER].reverse().map((rk) => ({ key: rk, meta: rarityOf(rk), skins: byR[rk] || [] })).filter((g) => g.skins.length);
  }, [filtered]);

  // Selección por defecto = destacada; se mantiene si sigue existiendo.
  useEffect(() => {
    if (!items.length) return;
    setSelectedId((cur) => (cur && items.some((s) => s.id === cur)) ? cur : featured?.id || null);
  }, [items, featured]);

  const selected = useMemo(() => items.find((s) => s.id === selectedId) || featured, [items, selectedId, featured]);
  useEffect(() => { setEquippedNow(!!selected?.equipped); }, [selected]);

  const onSelect = (s) => { play?.("open"); setSelectedId(s.id); if (window.innerWidth < 1024) window.scrollTo({ top: 0, behavior: "smooth" }); };

  const onBuy = async () => {
    if (!selected) return;
    setBusy(true); play?.("purchase");
    try {
      const { data } = await api.shopCheckout(selected.id);
      if (data?.checkout_url) externalRedirect(data.checkout_url);
      else { toast.error("No se pudo iniciar el pago"); setBusy(false); }
    } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo iniciar el pago"); setBusy(false); }
  };
  const onEquip = async () => {
    if (!selected) return;
    setBusy(true); play?.("click");
    try {
      await api.shopEquip(selected.id);
      play?.("success"); toast.success(`${selected.name} equipada`); setEquippedNow(true);
      load(); refresh?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo equipar"); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 py-8"
      style={{ background: "radial-gradient(1200px 460px at 50% -8%, rgba(245,158,11,0.06), transparent 60%)" }}>
      {/* encabezado compacto */}
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="mb-6">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-amber-400/90 font-bold">Vitrina de cosméticos · Edición coleccionista</p>
        <h1 className="font-display font-black uppercase tracking-tighter text-3xl sm:text-4xl lg:text-5xl leading-none mt-1">
          <span className="text-gold-clip">Tienda de Skins</span>
        </h1>
      </motion.div>

      {/* SALA DE EXHIBICIÓN: vitrina (izq) + lista navegable (der) */}
      <div className="grid lg:grid-cols-12 gap-6">
        {/* vitrina maestra (sticky) */}
        <div className="lg:col-span-7 lg:sticky lg:top-6 self-start">
          {!data ? (
            <div className="rounded-3xl border border-amber-500/20 min-h-[520px] animate-pulse" style={{ background: "linear-gradient(140deg,#101219,#0a0b0f)" }} />
          ) : (
            <DisplayCase skin={selected} busy={busy} equippedNow={equippedNow} onBuy={onBuy} onEquip={onEquip} />
          )}
        </div>

        {/* lista lateral con filtros */}
        <div className="lg:col-span-5">
          <div className="sticky top-6 z-30 p-3 rounded-2xl border border-amber-500/20 shadow-xl mb-4"
            style={{ background: "rgba(13,15,20,0.92)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)" }}>
            <div className="relative mb-2.5">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-amber-400/60" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar skins…" data-testid="skin-search"
                className="pl-9 pr-3 py-2.5 rounded-lg bg-white/[0.03] border border-amber-500/20 text-sm w-full outline-none focus:border-amber-400/50 transition-colors" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={dino} onValueChange={(v) => { setDino(v); play?.("click"); }}>
                <SelectTrigger className="flex-1 min-w-[130px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-dino"><SelectValue placeholder="Todos los dinos" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos los dinos</SelectItem>
                  {(data?.dinos || []).map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={type} onValueChange={(v) => { setType(v); play?.("click"); }}>
                <SelectTrigger className="flex-1 min-w-[120px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-type"><SelectValue placeholder="Tipo" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas las skins</SelectItem>
                  {(data?.types || []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={sort} onValueChange={(v) => { setSort(v); play?.("click"); }}>
                <SelectTrigger className="flex-1 min-w-[120px] bg-white/[0.03] border-amber-500/20 focus:border-amber-400/50" data-testid="filter-sort"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(SORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          {!data ? (
            <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-[74px] rounded-xl bg-white/[0.03] animate-pulse" />)}</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-20 rounded-2xl border border-amber-500/15">
              <PackageOpen size={36} className="mx-auto text-amber-400/60 mb-3" />
              <p className="text-base font-bold">No hay skins que coincidan</p>
              <p className="text-sm text-white/45 mt-1">Prueba con otro filtro o búsqueda.</p>
            </div>
          ) : (
            <div className="lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto lg:pr-1.5 space-y-5" data-testid="skins-list">
              <p className="text-xs text-white/45 font-mono" data-testid="catalog-count">{filtered.length} skins en la vitrina</p>
              {groups.map((g) => (
                <div key={g.key}>
                  <div className="flex items-center gap-2 mb-2 px-0.5">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: g.meta.color, boxShadow: `0 0 10px ${g.meta.color}` }} />
                    <h3 className="text-[11px] font-black uppercase tracking-[0.18em]" style={{ color: g.meta.color }}>{g.meta.label}</h3>
                    <span className="text-[10px] text-white/30 font-mono">{g.skins.length}</span>
                    <span className="flex-1 h-px ml-1" style={{ background: `linear-gradient(90deg, ${g.meta.color}44, transparent)` }} />
                  </div>
                  <div className="space-y-2">
                    <AnimatePresence initial={false}>
                      {g.skins.map((s) => (
                        <motion.div key={s.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                          <SkinRow skin={s} active={s.id === selectedId} onSelect={onSelect} play={play} />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <PurchaseCelebration skin={celebrate} play={play} onDone={() => setCelebrate(null)} />
    </div>
  );
}
