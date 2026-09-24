import React, { useState, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Volume2, VolumeX, Menu, X, LogOut, User as UserIcon,
  ChevronDown, Ticket, Home, LayoutDashboard, Bone, Store, Tag, ArrowLeftRight,
  Gamepad2, Swords, Target, BarChart3, Radio, Video, Palette, ShieldCheck,
  Spade, Dices, Gift, Package, Activity, MapPin, Dna, Skull, Sparkles, Crosshair, Hammer, Shield,
} from "lucide-react";

// True when the given "to" (which may carry a ?query) matches current location.
const linkMatches = (to, pathname, search) =>
  to.includes("?") ? `${pathname}${search}` === to : pathname === to;
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { BalanceHUD } from "@/components/common/BalanceHUD";
import { startSteamLogin } from "@/lib/api";

// Grouped navigation. Items can be single links or dropdown groups holding
// several children. `auth` restricts to signed-in users, `admin` to admins.
function buildNav(user) {
  return [
    { type: "link", to: "/", id: "home", label: "Inicio", icon: Home },
    { type: "link", to: "/dashboard", id: "dashboard", label: "Panel", icon: LayoutDashboard },
    {
      type: "group", id: "dino", label: "Dino en Vivo", icon: Bone,
      children: [
        { to: "/my-dino?tab=stats", id: "dino-stats", label: "Estadísticas", icon: Activity, desc: "Vitales y crecimiento en vivo" },
        { to: "/my-dino?tab=equipo", id: "dino-equipo", label: "Equipo", icon: Package, desc: "Bóveda e inventario" },
        { to: "/my-dino?tab=map", id: "dino-map", label: "Mapa", icon: MapPin, desc: "Ubicación en tiempo real" },
        { to: "/my-dino?tab=gen0", id: "dino-gen0", label: "GEN-Ø", icon: Dna, desc: "Estado de infección GEN-Ø" },
        { to: "/cementerio", id: "cementerio", label: "Cementerio", icon: Skull, desc: "Dinos caídos y resurrección con Fósiles" },
      ],
    },
    {
      type: "group", id: "tienda", label: "Tienda", icon: Store,
      children: [
        { to: "/store", id: "store", label: "Tienda", icon: Store, desc: "Compra dinos, cofres y más" },
        { to: "/tienda-skins", id: "skins-shop", label: "Skins", icon: Sparkles, desc: "Skins únicas por tiempo limitado" },
        { to: "/crafteo", id: "crafteo", label: "Crafteo de Skins", icon: Hammer, desc: "Fabrica skins con materiales del mapa" },
        { to: "/marketplace", id: "market", label: "Mercado", icon: Tag, desc: "Compra y vende entre jugadores" },
        { to: "/intercambios", id: "trades", label: "Intercambios", icon: ArrowLeftRight, desc: "Intercambia animales y objetos" },
      ],
    },
    {
      type: "group", id: "minijuegos", label: "Mini Juegos", icon: Gamepad2,
      children: [
        { to: "/mini-juegos?tab=wheel", id: "game-wheel", label: "Ruleta Diaria", icon: Gift, desc: "Giro gratis cada día" },
        { to: "/mini-juegos?tab=blackjack", id: "game-blackjack", label: "Blackjack", icon: Spade, desc: "Vence a la casa en el 21" },
        { to: "/mini-juegos?tab=roll", id: "game-roll", label: "Roll", icon: Dices, desc: "Apuesta y multiplica tu tirada" },
        { to: "/mini-juegos?tab=crates", id: "game-crates", label: "Cajas", icon: Package, desc: "Abre cofres con premios" },
        { to: "/battle-pass", id: "battlepass", label: "Pase de Batalla", icon: Swords, desc: "Sube de nivel y reclama premios" },
      ],
    },
    { type: "link", to: "/quests", id: "quests", label: "Misiones", icon: Target },
    { type: "link", to: "/leaderboard", id: "leaderboard", label: "Clasificación", icon: BarChart3 },
    {
      type: "group", id: "comunidad", label: "Comunidad", icon: Radio,
      children: [
        { to: "/proximity-voice", id: "proximity-voice", label: "Radio de Proximidad", icon: Radio, desc: "Voz por cercanía en el juego" },
        { to: "/bounty", id: "bounty", label: "Bounty Global", icon: Crosshair, desc: "Objetivo global ☠️ — elimínalo y gana" },
        { to: "/clanes", id: "clanes", label: "Clanes", icon: Shield, desc: "Funda tu clan, chatea y domina territorios" },
        { to: "/creator/dashboard", id: "creator", label: "Creators", icon: Video, desc: "Programa de creadores de contenido" },
        ...(user ? [{ to: "/skin-editor", id: "skin-lab", label: "Patreon", icon: Palette, desc: "Editor de skins para Patreons" }] : []),
      ],
    },
    ...(user?.role === "admin" ? [{ type: "link", to: "/admin", id: "admin", label: "Admin", icon: ShieldCheck }] : []),
  ];
}

// Shared, unified motion — every dropdown opens with the same easing/timing so
// they feel synchronized. The panel fades/scales in while its items cascade.
const EASE = [0.16, 1, 0.3, 1];
const panelVariants = {
  hidden: { opacity: 0, y: 10, scale: 0.97 },
  show: {
    opacity: 1, y: 0, scale: 1,
    transition: { duration: 0.22, ease: EASE, staggerChildren: 0.05, delayChildren: 0.06 },
  },
  exit: { opacity: 0, y: 8, scale: 0.97, transition: { duration: 0.14, ease: "easeIn" } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: EASE } },
};

// Desktop dropdown group — opens on hover/click with a small close delay so the
// cursor can travel from the trigger into the panel without it collapsing.
function NavGroup({ item, activePath, activeSearch, play }) {
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const anyActive = item.children.some((c) => linkMatches(c.to, activePath, activeSearch));

  const doOpen = () => {
    clearTimeout(timer.current);
    setOpen((was) => { if (!was) play("menu"); return true; });
  };
  const doClose = (immediate = false) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen((was) => { if (was) play("menuClose"); return false; }), immediate ? 0 : 120);
  };

  // Click-only: close when clicking outside the group or pressing Escape.
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) doClose(true); };
    const onEsc = (e) => { if (e.key === "Escape") doClose(true); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onEsc); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={wrapRef} className="relative h-full flex items-center" data-testid={`nav-group-${item.id}`}>
      <button
        onClick={() => (open ? doClose(true) : doOpen())}
        data-testid={`nav-group-trigger-${item.id}`}
        className={`relative h-full flex items-center gap-1.5 px-3.5 text-[12px] font-bold uppercase tracking-[0.08em] transition-colors duration-200 ${anyActive || open ? "text-gold bg-gold/[0.06]" : "text-muted-foreground hover:text-foreground hover:bg-white/[0.05]"}`}
      >
        {item.label}
        <ChevronDown size={13} className={`transition-transform duration-300 ease-out ${open ? "rotate-180" : ""}`} />
        {(anyActive || open) && <motion.span layoutId="nav-active" className="absolute inset-x-0 -bottom-px h-[3px] bg-gold" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            variants={panelVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            className="absolute left-1/2 -translate-x-1/2 top-full pt-2 w-72"
            data-testid={`nav-dropdown-${item.id}`}
          >
            <div className="bg-[#0c0d0a]/95 backdrop-blur-xl rounded-md p-1.5 shadow-[0_16px_50px_rgba(0,0,0,0.6)] border border-gold/20 border-t-2 border-t-gold/60">
              {item.children.map((c) => {
                const Icon = c.icon;
                const active = linkMatches(c.to, activePath, activeSearch);
                return (
                  <motion.div key={c.to} variants={itemVariants}>
                    <Link
                      to={c.to}
                      data-testid={`nav-link-${c.id}`}
                      onClick={() => { play("click"); doClose(true); }}
                      className={`group/item flex items-start gap-3 px-2.5 py-2.5 rounded-sm border-l-2 transition-colors duration-200 ${active ? "bg-gold/10 border-gold" : "border-transparent hover:bg-white/5 hover:border-gold/40"}`}
                    >
                      <span className={`mt-0.5 flex-shrink-0 grid place-items-center w-9 h-9 rounded-md border transition-all duration-200 ${active ? "border-gold/40 bg-gold/15 text-gold" : "border-white/10 bg-white/5 text-muted-foreground group-hover/item:text-gold group-hover/item:border-gold/30"}`}>
                        <Icon size={16} />
                      </span>
                      <span className="min-w-0">
                        <span className={`block text-[13px] font-bold uppercase tracking-wide ${active ? "text-gold" : "text-foreground"}`}>{c.label}</span>
                        {c.desc && <span className="block text-xs text-muted-foreground leading-tight mt-0.5 normal-case tracking-normal font-normal">{c.desc}</span>}
                      </span>
                    </Link>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Navbar() {
  const { user, logout } = useAuth();
  const { enabled, toggle, play } = useSound();
  const location = useLocation();
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [openMobileGroup, setOpenMobileGroup] = useState(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => { setMobile(false); setProfileOpen(false); setOpenMobileGroup(null); }, [location.pathname]);

  const steamLogin = () => { play("click"); startSteamLogin(); };
  const nav = buildNav(user);
  const activePath = location.pathname;
  const activeSearch = location.search;

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 border-b ${scrolled ? "bg-[#0b0c09]/90 backdrop-blur-xl border-gold/30 shadow-[0_10px_40px_rgba(0,0,0,0.55)]" : "bg-gradient-to-b from-black/70 to-transparent border-white/5"}`}
      data-testid="navbar"
    >
      <span aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold/40 to-transparent" />
      <nav className="max-w-[90rem] mx-auto px-4 sm:px-6 h-[72px] flex items-center justify-between gap-2">
        <Link to="/" className="flex items-center gap-3 group flex-shrink-0 pr-4 mr-1 border-r border-white/10" data-testid="nav-logo" onMouseEnter={() => play("hover")}>
          <img src={MEDIA.logo} alt="Isla Nublar LATAM" className="h-10 w-auto group-hover:scale-105 transition-transform" />
        </Link>

        <div className="hidden xl:flex items-center h-full">
          {nav.map((item) =>
            item.type === "group" ? (
              <NavGroup key={item.id} item={item} activePath={activePath} activeSearch={activeSearch} play={play} />
            ) : (
              <Link
                key={item.to}
                to={item.to}
                data-testid={`nav-link-${item.id}`}
                onMouseEnter={() => play("hover")}
                onClick={() => play("click")}
                className={`relative h-full flex items-center px-3.5 text-[12px] font-bold uppercase tracking-[0.08em] transition-colors duration-200 ${activePath === item.to ? "text-gold bg-gold/[0.06]" : "text-muted-foreground hover:text-foreground hover:bg-white/[0.05]"}`}
              >
                {item.label}
                {activePath === item.to && <motion.span layoutId="nav-active" className="absolute inset-x-0 -bottom-px h-[3px] bg-gold" />}
              </Link>
            )
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          <button
            onClick={() => { toggle(); play("click"); }}
            data-testid="sound-toggle"
            aria-label="Activar o desactivar sonido"
            className="p-2 rounded-md text-muted-foreground hover:text-gold hover:bg-white/5 transition-colors"
          >
            {enabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
          </button>

          {user ? (
            <div className="flex items-center gap-3">
              <BalanceHUD />
              <div className="relative hidden sm:block">
              <button
                onClick={() => { setProfileOpen((o) => !o); play("click"); }}
                onMouseEnter={() => play("hover")}
                data-testid="profile-menu-button"
                className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-md border border-white/10 bg-white/5 hover:border-gold/40 transition-colors"
              >
                <img src={user.avatar || MEDIA.logo} alt="" className="w-7 h-7 rounded-full object-cover border border-gold/30" />
                <ChevronDown size={14} className={`text-muted-foreground transition-transform ${profileOpen ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {profileOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.96 }}
                    transition={{ duration: 0.18 }}
                    className="absolute right-0 mt-2 w-56 glass-strong rounded-xl p-2 shadow-2xl"
                    data-testid="profile-dropdown"
                  >
                    <div className="px-3 py-2 border-b border-white/5 mb-1">
                      <p className="font-display font-bold truncate">{user.persona_name}</p>
                      <p className="text-xs text-muted-foreground">{user.rank}</p>
                    </div>
                    <Link to="/profile" data-testid="dropdown-profile" onClick={() => play("click")} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-white/5 transition-colors">
                      <UserIcon size={15} /> Perfil
                    </Link>
                    <Link to="/redeem" data-testid="dropdown-redeem" onClick={() => play("click")} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-white/5 transition-colors">
                      <Ticket size={15} /> Redimir códigos
                    </Link>
                    <button onClick={() => { logout(); play("close"); navigate("/"); }} data-testid="logout-button" className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-crimson hover:bg-crimson/10 transition-colors">
                      <LogOut size={15} /> Cerrar sesión
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            </div>
          ) : (
            <button
              onClick={steamLogin}
              onMouseEnter={() => play("hover")}
              data-testid="steam-login-button"
              className="hidden sm:inline-flex items-center gap-2 bg-gold text-background font-extrabold text-[12px] uppercase tracking-wider px-4 py-2.5 rounded-md hover:brightness-110 hover:gold-glow transition-all"
            >
              Iniciar sesión con Steam
            </button>
          )}

          <button onClick={() => { setMobile((m) => !m); play("click"); }} data-testid="mobile-menu-button" className="xl:hidden p-2 rounded-md border border-white/10 hover:bg-white/5">
            {mobile ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {mobile && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="xl:hidden overflow-hidden glass-strong border-t border-white/5"
            data-testid="mobile-menu"
          >
            <div className="px-4 py-4 flex flex-col gap-1 max-h-[70vh] overflow-y-auto">
              {nav.map((item) =>
                item.type === "group" ? (
                  <div key={item.id} data-testid={`mobile-group-${item.id}`}>
                    <button
                      onClick={() => { setOpenMobileGroup((g) => { const opening = g !== item.id; play(opening ? "menu" : "menuClose"); return opening ? item.id : null; }); }}
                      data-testid={`mobile-group-trigger-${item.id}`}
                      className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5"
                    >
                      <span className="flex items-center gap-2"><item.icon size={16} className="text-gold" /> {item.label}</span>
                      <ChevronDown size={16} className={`transition-transform duration-300 ${openMobileGroup === item.id ? "rotate-180" : ""}`} />
                    </button>
                    <AnimatePresence>
                      {openMobileGroup === item.id && (
                        <motion.div
                          variants={panelVariants}
                          initial="hidden"
                          animate="show"
                          exit="exit"
                          className="overflow-hidden pl-4 border-l border-white/10 ml-4"
                        >
                          {item.children.map((c) => (
                            <motion.div key={c.to} variants={itemVariants}>
                              <Link to={c.to} data-testid={`mobile-link-${c.id}`} className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm hover:bg-white/5 text-muted-foreground hover:text-foreground" onClick={() => play("click")}>
                                <c.icon size={15} /> {c.label}
                              </Link>
                            </motion.div>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ) : (
                  <Link key={item.to} to={item.to} data-testid={`mobile-link-${item.id}`} className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5" onClick={() => play("click")}>
                    <item.icon size={16} className="text-muted-foreground" /> {item.label}
                  </Link>
                )
              )}
              {user ? (
                <Link to="/profile" className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5" onClick={() => play("click")}><UserIcon size={16} /> Perfil</Link>
              ) : (
                <button onClick={steamLogin} className="mt-2 bg-gold text-background font-bold text-sm px-4 py-2.5 rounded-lg">Iniciar sesión con Steam</button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
