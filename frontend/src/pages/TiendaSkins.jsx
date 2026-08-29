import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Flame, Sparkles, PackageOpen, Clock, Skull } from "lucide-react";
import { api, shopWsUrl } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { SkinCard } from "@/components/shop/SkinCard";
import { SkinDetailModal } from "@/components/shop/SkinDetailModal";
import { PurchaseCelebration } from "@/components/shop/PurchaseCelebration";
import { RARITY, RARITY_ORDER } from "@/components/shop/shopRarity";
import { SkeletonCard } from "@/components/common/PageLoader";

const ORDER = ["destacados", "diario", "temporada"];
const SECTION_META = {
  destacados: { n: "01", title: "Destacados", icon: Flame, color: "#f59e0b", sub: "Lo más codiciado ahora mismo" },
  diario: { n: "02", title: "Diario", icon: Sparkles, color: "#38bdf8", sub: "Rota cada 24 horas" },
  temporada: { n: "03", title: "Temporada", icon: Skull, color: "#a855f7", sub: "Ediciones limitadas de evento" },
};

// bento span pattern for Destacados (aggressive, editorial arrangement)
function featSpan(i) {
  if (i === 0) return "col-span-2 row-span-2";
  if (i === 1) return "col-span-2 row-span-1";
  return "col-span-1 row-span-1";
}

function nextResetLabel() {
  const d = new Date();
  d.setUTCHours(24, 0, 0, 0);
  return d.toISOString();
}

export default function TiendaSkins() {
  const { play } = useSound();
  const { refresh } = useAuth();
  const [sections, setSections] = useState(null);
  const [selected, setSelected] = useState(null);
  const [celebrate, setCelebrate] = useState(null);
  const dailyReset = useRef(nextResetLabel());

  const load = useCallback(async () => {
    try { const { data } = await api.shopSkins(); setSections(data.sections); }
    catch { setSections({ destacados: [], diario: [], temporada: [] }); }
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

  const onEquipped = (skinId) => {
    setSections((prev) => {
      if (!prev) return prev;
      const clone = { ...prev };
      for (const k of ORDER) clone[k] = (clone[k] || []).map((s) => ({ ...s, equipped: s.id === skinId }));
      return clone;
    });
    setSelected((s) => (s ? { ...s, equipped: s.id === skinId, owned: true } : s));
    refresh?.();
  };

  const total = sections ? ORDER.reduce((n, k) => n + (sections[k]?.length || 0), 0) : 0;

  return (
    <div className="relative min-h-screen" data-testid="tienda-skins-page">
      {/* animated technical backdrop */}
      <div className="pointer-events-none fixed inset-0 shop-grid-bg opacity-40" />
      <div className="pointer-events-none fixed inset-0" style={{ background: "radial-gradient(80% 50% at 50% -10%, rgba(124,168,66,0.12), transparent 60%)" }} />

      <div className="relative max-w-[1400px] mx-auto px-6 py-10">
        {/* HERO */}
        <motion.div initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}
          className="relative overflow-hidden clip-notch border border-white/10 p-8 sm:p-12 mb-12"
          style={{ background: "linear-gradient(115deg,#141a0e 0%,#0b0d09 55%)" }}>
          <div className="absolute -right-16 -top-24 w-96 h-96 rounded-full blur-3xl opacity-30" style={{ background: "radial-gradient(circle,#7CA842,transparent)" }} />
          <div className="absolute -left-10 bottom-0 w-72 h-72 rounded-full blur-3xl opacity-20" style={{ background: "radial-gradient(circle,#f59e0b,transparent)" }} />
          <div className="relative">
            <p className="label-overline text-[11px] text-[#f59e0b] mb-3 flex items-center gap-2">
              <Flame size={14} /> Tienda rotativa · Ediciones únicas
            </p>
            <h1 className="font-display font-black uppercase tracking-tighter leading-[0.85] text-5xl sm:text-7xl lg:text-8xl">
              <span className="text-white">Skin</span>{" "}
              <span style={{ background: "linear-gradient(120deg,#B8DA7E,#7CA842 40%,#f59e0b)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>Vault</span>
            </h1>
            <p className="text-white/55 mt-4 max-w-xl text-sm sm:text-base">
              Colecciona skins <b className="text-white">únicas</b> y legendarias por tiempo limitado. Cuando rotan, desaparecen. Consíguelas y equípalas a tus dinos.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <div className="inline-flex items-center gap-2 clip-notch-sm border border-white/10 bg-black/40 px-4 py-2 font-code text-xs text-white/70">
                <Clock size={13} className="text-[#38bdf8]" /> Diario rota en <DailyTimer target={dailyReset.current} />
              </div>
              {/* rarity legend */}
              <div className="inline-flex items-center gap-2.5 clip-notch-sm border border-white/10 bg-black/40 px-4 py-2">
                {RARITY_ORDER.map((k) => (
                  <span key={k} title={RARITY[k].label} className="w-3 h-3 rounded-sm" style={{ background: RARITY[k].color, boxShadow: `0 0 8px ${RARITY[k].color}` }} />
                ))}
                <span className="text-[10px] text-white/40 uppercase tracking-wider ml-1">Rareza</span>
              </div>
            </div>
          </div>
        </motion.div>

        {sections === null ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} className="aspect-[3/4]" />)}
          </div>
        ) : total === 0 ? (
          <div className="text-center py-28 text-white/40" data-testid="shop-empty">
            <PackageOpen size={52} className="mx-auto mb-4 opacity-50" />
            <p className="text-lg">La bóveda está vacía por ahora.</p>
            <p className="text-sm mt-1">Vuelve pronto — nuevas skins caen cada semana.</p>
          </div>
        ) : (
          <div className="space-y-16">
            {ORDER.map((key) => {
              const items = sections[key] || [];
              if (items.length === 0) return null;
              const m = SECTION_META[key];
              return (
                <section key={key} data-testid={`shop-section-${key}`}>
                  {/* section header */}
                  <div className="flex items-center gap-4 mb-6">
                    <span className="font-display font-black text-5xl sm:text-6xl leading-none opacity-20" style={{ color: m.color }}>{m.n}</span>
                    <div className="flex-1">
                      <h2 className="font-display font-black uppercase tracking-tight text-2xl sm:text-4xl flex items-center gap-2.5">
                        <m.icon size={26} style={{ color: m.color }} /> {m.title}
                      </h2>
                      <p className="text-xs text-white/45 mt-0.5">{m.sub}</p>
                    </div>
                    <div className="hidden sm:block h-[2px] flex-[0.4]" style={{ background: `linear-gradient(90deg,transparent,${m.color})` }} />
                    <span className="font-code text-xs text-white/45 whitespace-nowrap">{items.length} skins</span>
                  </div>

                  {/* grids per section */}
                  {key === "destacados" ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 auto-rows-[190px] gap-4">
                      <AnimatePresence>
                        {items.map((skin, i) => (
                          <div key={skin.id} className={featSpan(i)}>
                            <SkinCard skin={skin} onClick={setSelected} play={play} featured={i === 0} />
                          </div>
                        ))}
                      </AnimatePresence>
                    </div>
                  ) : key === "temporada" ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 auto-rows-[260px] gap-4">
                      <AnimatePresence>
                        {items.map((skin, i) => (
                          <div key={skin.id} className={i === 0 ? "md:col-span-2" : ""}>
                            <SkinCard skin={skin} onClick={setSelected} play={play} featured={i === 0} />
                          </div>
                        ))}
                      </AnimatePresence>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 auto-rows-[260px] gap-4">
                      <AnimatePresence>
                        {items.map((skin) => (
                          <div key={skin.id}>
                            <SkinCard skin={skin} onClick={setSelected} play={play} />
                          </div>
                        ))}
                      </AnimatePresence>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>

      <SkinDetailModal skin={selected} open={!!selected} onClose={() => setSelected(null)} play={play} onEquipped={onEquipped} />
      <PurchaseCelebration skin={celebrate} onDone={() => setCelebrate(null)} play={play} />
    </div>
  );
}

function DailyTimer({ target }) {
  const [, force] = useState(0);
  useEffect(() => { const id = setInterval(() => force((n) => n + 1), 1000); return () => clearInterval(id); }, []);
  const ms = new Date(target).getTime() - Date.now();
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return <span className="text-[#38bdf8] tabular-nums font-bold">{h}:{m}:{sec}</span>;
}
