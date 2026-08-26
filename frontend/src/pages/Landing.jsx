import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, Users, Clock, Server, Zap, ShieldCheck, Coins } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { ParticleField } from "@/components/effects/ParticleField";
import { AnimatedCounter } from "@/components/common/AnimatedCounter";
import { Reveal } from "@/components/common/Reveal";
import { CoinChip } from "@/components/common/CoinChip";
import { RarityBadge, TYPE_COLORS } from "@/components/common/RarityBadge";
import { StatusDot } from "@/components/common/Hud";
import { TopCreatorsBanner } from "@/components/creator/TopCreatorsBanner";
import { LiveProgramCounter } from "@/components/creator/LiveProgramCounter";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";
import { api, startSteamLogin } from "@/lib/api";

const DIET_LABEL = { Carnivore: "Carnívoro", Herbivore: "Herbívoro", Omnivore: "Omnívoro" };

export default function Landing() {
  const { play } = useSound();
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [dinos, setDinos] = useState([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    api.serverStatus().then((r) => setStatus(r.data)).catch(() => {});
    api.dinosaurs().then((r) => setDinos(r.data.filter((d) => d.featured).concat(r.data).slice(0, 5))).catch(() => {});
  }, []);

  useEffect(() => {
    if (dinos.length < 2) return;
    const t = setInterval(() => setActive((a) => (a + 1) % dinos.length), 4000);
    return () => clearInterval(t);
  }, [dinos]);

  const featured = dinos[active];

  return (
    <div>
      {/* HERO */}
      <section className="relative min-h-[92vh] flex items-center grain overflow-hidden">
        <div className="absolute inset-0">
          <img src={MEDIA.heroBg} alt="" className="w-full h-full object-cover opacity-40" />
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-background/70 to-background" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-transparent to-transparent" />
        </div>
        <ParticleField density={70} />

        <div className="relative z-10 max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-10 items-center w-full pt-10">
          <div>
            <motion.div
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
              className="inline-flex items-center gap-2 glass rounded-full px-4 py-1.5 mb-6"
            >
              <StatusDot online={status?.online !== false} label={status?.online === false ? "Servidor desconectado" : "Servidor en linea"} />
              {status && <span className="text-xs text-muted-foreground">· {status.players}/{status.max_players} supervivientes</span>}
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }}
              className="font-display font-extrabold tracking-tighter text-5xl sm:text-6xl lg:text-7xl leading-[0.95]"
            >
              SOBREVIVE EN<br />
              <span className="text-gradient-gold">ISLA NUBLAR</span> LATAM
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.25 }}
              className="mt-6 text-base sm:text-lg text-muted-foreground max-w-lg"
            >
              El servidor comunitario n.º 1 de The Isle: Evrima en Latinoamérica. Caza como un depredador ápice, construye dinastías y escala una economía viva de doble moneda.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.4 }}
              className="mt-8 flex flex-wrap gap-3"
            >
              {!user && (
                <button
                  onClick={() => { play("click"); startSteamLogin(); }}
                  onMouseEnter={() => play("hover")}
                  data-testid="hero-steam-button"
                  className="group inline-flex items-center gap-2 bg-gold text-background font-bold px-6 py-3 rounded-xl hover:brightness-110 hover:gold-glow transition-all"
                >
                  Únete con Steam <ChevronRight size={18} className="group-hover:translate-x-1 transition-transform" />
                </button>
              )}
              <Link
                to="/store"
                onMouseEnter={() => play("hover")} onClick={() => play("click")}
                data-testid="hero-dinos-button"
                className="inline-flex items-center gap-2 glass font-semibold px-6 py-3 rounded-xl hover:border-gold/40 transition-all"
              >
                Explorar la Tienda
              </Link>
            </motion.div>
          </div>

          {/* Dino showcase */}
          <div className="relative h-[420px] hidden lg:block">
            <AnimatePresence mode="popLayout">
              {featured && (
                <motion.div
                  key={featured.slug}
                  initial={{ opacity: 0, scale: 0.9, filter: "blur(8px)" }}
                  animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                  exit={{ opacity: 0, scale: 1.05, filter: "blur(8px)" }}
                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                  className="absolute inset-0"
                >
                  <div className="absolute inset-0 rounded-3xl overflow-hidden glass-strong">
                    <img src={featured.image} alt={featured.name} className="w-full h-full object-contain p-6 animate-float" />
                    <div className="absolute inset-0 bg-gradient-to-t from-background/70 via-transparent to-transparent pointer-events-none" />
                  </div>
                  <div className="absolute bottom-6 left-6 right-6 glass-strong rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`label-overline text-[11px] ${TYPE_COLORS[featured.type]}`}>{DIET_LABEL[featured.type] || featured.type}</span>
                      <RarityBadge rarity={featured.rarity} />
                    </div>
                    <h3 className="font-display font-bold text-2xl">{featured.name}</h3>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
            <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
              {dinos.map((_, i) => (
                <button key={i} onClick={() => setActive(i)} className={`h-1.5 rounded-full transition-all ${i === active ? "w-6 bg-gold" : "w-1.5 bg-white/20"}`} />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* LIVE STATS STRIP */}
      <section className="relative -mt-10 z-20 max-w-6xl mx-auto px-6">
        <Reveal>
          <div className="glass-strong rounded-2xl grid grid-cols-2 md:grid-cols-4 divide-x divide-white/5">
            {[
              { icon: Users, label: "Jugadores en linea", value: status?.players ?? 0, color: "text-emerald" },
              { icon: Clock, label: "Actividad (hrs)", value: status?.uptime_hours ?? 0, color: "text-gold" },
              { icon: Server, label: "Rendimiento", value: status?.tickrate ?? 30, color: "text-sky-400" },
              { icon: Zap, label: "Plazas max.", value: status?.max_players ?? 120, color: "text-crimson" },
            ].map((s, i) => (
              <div key={i} className="p-6 text-center">
                <s.icon className={`mx-auto mb-2 ${s.color}`} size={22} />
                <div className="font-display font-extrabold text-3xl">
                  <AnimatedCounter value={s.value} />
                </div>
                <div className="label-overline text-[10px] text-muted-foreground mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* FEATURED DINOS */}
      <section className="max-w-7xl mx-auto px-6 py-24">
        <Reveal className="flex items-end justify-between mb-10">
          <div>
            <p className="label-overline text-xs text-gold mb-2">El Plantel</p>
            <h2 className="font-display font-extrabold text-3xl sm:text-4xl tracking-tight">Contendientes Ápice</h2>
          </div>
          <Link to="/store" onMouseEnter={() => play("hover")} className="text-sm text-gold font-semibold inline-flex items-center gap-1 hover:gap-2 transition-all">
            Ver todos <ChevronRight size={16} />
          </Link>
        </Reveal>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {dinos.slice(0, 3).map((d, i) => (
            <Reveal key={d.slug} delay={i * 0.08}>
              <Link
                to="/store"
                onMouseEnter={() => play("hover")} onClick={() => play("click")}
                className="group block relative rounded-2xl overflow-hidden glass hover:border-gold/40 hover:-translate-y-1 transition-all duration-300"
                data-testid={`featured-dino-${d.slug}`}
              >
                <div className="aspect-[4/3] overflow-hidden relative">
                  <img src={d.image} alt={d.name} className="w-full h-full object-contain p-4 group-hover:scale-105 transition-transform duration-700" />
                  <div className="absolute inset-0 bg-gradient-to-t from-background to-transparent pointer-events-none" />
                </div>
                <div className="absolute bottom-0 inset-x-0 p-5">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`label-overline text-[10px] ${TYPE_COLORS[d.type]}`}>{DIET_LABEL[d.type] || d.type}</span>
                    <RarityBadge rarity={d.rarity} />
                  </div>
                  <h3 className="font-display font-bold text-xl">{d.name}</h3>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* DUAL ECONOMY */}
      <section className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid lg:grid-cols-2 gap-6">
          {[
            { type: "normal", title: "PrimeMeat", desc: "Se gana jugando, completando misiones, sobreviviendo eventos y con recompensas diarias. La savia de la economía de la isla.", how: ["Tiempo de juego", "Misiones", "Eventos", "Recompensa diaria"] },
            { type: "vip", title: "Amberium", desc: "La moneda premium de la isla. Se obtiene vía Patreon y eventos especiales del staff.", how: ["Patreon", "Suscripciones", "Eventos especiales"] },
          ].map((c, i) => (
            <Reveal key={c.type} delay={i * 0.1}>
              <div className={`relative rounded-2xl p-8 glass overflow-hidden ${c.type === "vip" ? "hover:crimson-glow" : "hover:gold-glow"} transition-all duration-500`}>
                <div className="grain absolute inset-0 opacity-50" />
                <div className="relative flex items-start gap-5">
                  <CoinChip type={c.type} size="xl" />
                  <div className="flex-1">
                    <h3 className="font-display font-bold text-2xl mb-2">{c.title}</h3>
                    <p className="text-sm text-muted-foreground mb-4">{c.desc}</p>
                    <div className="flex flex-wrap gap-2">
                      {c.how.map((h) => (
                        <span key={h} className="text-xs glass px-3 py-1 rounded-full text-muted-foreground">{h}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid sm:grid-cols-3 gap-6">
          {[
            { icon: ShieldCheck, title: "Anti-trampas", desc: "Límites de peticiones y protección contra XSS e inyección mantienen la isla justa." },
            { icon: Coins, title: "Economía Viva", desc: "Doble moneda, gráficas, historial completo de transacciones y analíticas." },
            { icon: Zap, title: "Sincronizacion instantanea", desc: "Steam, Patreon y Discord sincronizados en un único perfil premium." },
          ].map((f, i) => (
            <Reveal key={i} delay={i * 0.08}>
              <div className="glass rounded-2xl p-7 h-full hover:border-gold/30 transition-colors">
                <f.icon className="text-gold mb-4" size={26} />
                <h3 className="font-display font-bold text-lg mb-2">{f.title}</h3>
                <p className="text-sm text-muted-foreground">{f.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* CREATOR PROGRAM (auto-hidden if no creators / no activity yet; each
          of these two manages its own max-width/padding, same as every
          other top-level section on this page) */}
      <LiveProgramCounter />
      <TopCreatorsBanner />

      {/* CTA */}
      <section className="max-w-5xl mx-auto px-6 py-20">
        <Reveal>
          <div className="relative rounded-3xl overflow-hidden glass-strong text-center p-12 grain">
            <img src={MEDIA.carno} alt="" className="absolute inset-0 w-full h-full object-cover opacity-10" />
            <div className="relative">
              <h2 className="font-display font-extrabold text-3xl sm:text-5xl tracking-tight mb-4">Tu dinastía te espera</h2>
              <p className="text-muted-foreground max-w-xl mx-auto mb-8">Inicia sesión con Steam para reclamar tu bono de bienvenida y pisar la isla.</p>
              {!user ? (
                <button onClick={() => { play("click"); startSteamLogin(); }} className="bg-gold text-background font-bold px-8 py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all">
                  Iniciar sesión con Steam
                </button>
              ) : (
                <Link to="/dashboard" className="inline-block bg-gold text-background font-bold px-8 py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all">
                  Ir al Panel
                </Link>
              )}
            </div>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
