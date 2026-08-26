import React, { useState, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Volume2, VolumeX, ShoppingCart, Menu, X, LogOut, User as UserIcon,
  ChevronDown, Ticket, Home, LayoutDashboard, Bone, Store, Tag, ArrowLeftRight,
  Gamepad2, Swords, Target, BarChart3, Radio, Video, Palette, ShieldCheck,
} from "lucide-react";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { useCart } from "@/context/CartContext";
import { BalanceHUD } from "@/components/common/BalanceHUD";
import { startSteamLogin } from "@/lib/api";

// Grouped navigation. Items can be single links or dropdown groups holding
// several children. `auth` restricts to signed-in users, `admin` to admins.
function buildNav(user) {
  return [
    { type: "link", to: "/", id: "home", label: "Inicio", icon: Home },
    { type: "link", to: "/dashboard", id: "dashboard", label: "Panel", icon: LayoutDashboard },
    { type: "link", to: "/my-dino", id: "live-dino", label: "Dino en Vivo", icon: Bone },
    {
      type: "group", id: "tienda", label: "Tienda", icon: Store,
      children: [
        { to: "/store", id: "store", label: "Tienda", icon: Store, desc: "Compra dinos, cofres y más" },
        { to: "/marketplace", id: "market", label: "Mercado", icon: Tag, desc: "Compra y vende entre jugadores" },
        { to: "/intercambios", id: "trades", label: "Intercambios", icon: ArrowLeftRight, desc: "Intercambia animales y objetos" },
      ],
    },
    {
      type: "group", id: "minijuegos", label: "Mini Juegos", icon: Gamepad2,
      children: [
        ...(user ? [{ to: "/mini-juegos", id: "mini-juegos", label: "Mini Juegos", icon: Gamepad2, desc: "Ruleta, Crash, Dados y más" }] : []),
        { to: "/battle-pass", id: "battlepass", label: "Pase de Batalla", icon: Swords, desc: "Sube de nivel y reclama premios" },
      ],
    },
    { type: "link", to: "/quests", id: "quests", label: "Misiones", icon: Target },
    { type: "link", to: "/leaderboard", id: "leaderboard", label: "Clasificación", icon: BarChart3 },
    {
      type: "group", id: "comunidad", label: "Comunidad", icon: Radio,
      children: [
        { to: "/proximity-voice", id: "proximity-voice", label: "Radio de Proximidad", icon: Radio, desc: "Voz por cercanía en el juego" },
        { to: "/creator/dashboard", id: "creator", label: "Creators", icon: Video, desc: "Programa de creadores de contenido" },
        ...(user ? [{ to: "/skin-editor", id: "skin-lab", label: "Patreon", icon: Palette, desc: "Editor de skins para Patreons" }] : []),
      ],
    },
    ...(user?.role === "admin" ? [{ type: "link", to: "/admin", id: "admin", label: "Admin", icon: ShieldCheck }] : []),
  ];
}

// Desktop dropdown group — opens on hover with a small close delay so the
// cursor can travel from the trigger into the panel without it collapsing.
function NavGroup({ item, activePath, play }) {
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const anyActive = item.children.some((c) => activePath === c.to);

  const enter = () => { clearTimeout(timer.current); setOpen(true); };
  const leave = () => { timer.current = setTimeout(() => setOpen(false), 120); };

  return (
    <div className="relative" onMouseEnter={() => { enter(); play("hover"); }} onMouseLeave={leave} data-testid={`nav-group-${item.id}`}>
      <button
        data-testid={`nav-group-trigger-${item.id}`}
        className={`relative flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${anyActive || open ? "text-gold" : "text-muted-foreground hover:text-foreground"}`}
      >
        {item.label}
        <ChevronDown size={14} className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
        {anyActive && <motion.span layoutId="nav-active" className="absolute inset-x-3 -bottom-0.5 h-0.5 bg-gold rounded-full" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-1/2 -translate-x-1/2 top-full pt-3 w-72"
            data-testid={`nav-dropdown-${item.id}`}
          >
            <div className="glass-strong rounded-2xl p-2 shadow-2xl border border-white/10 ring-1 ring-gold/5">
              {item.children.map((c) => {
                const Icon = c.icon;
                const active = activePath === c.to;
                return (
                  <Link
                    key={c.to}
                    to={c.to}
                    data-testid={`nav-link-${c.id}`}
                    onClick={() => { play("click"); setOpen(false); }}
                    className={`group/item flex items-start gap-3 px-3 py-2.5 rounded-xl transition-colors ${active ? "bg-gold/10" : "hover:bg-white/5"}`}
                  >
                    <span className={`mt-0.5 flex-shrink-0 grid place-items-center w-9 h-9 rounded-lg border transition-colors ${active ? "border-gold/40 bg-gold/15 text-gold" : "border-white/10 bg-white/5 text-muted-foreground group-hover/item:text-gold group-hover/item:border-gold/30"}`}>
                      <Icon size={16} />
                    </span>
                    <span className="min-w-0">
                      <span className={`block text-sm font-semibold ${active ? "text-gold" : "text-foreground"}`}>{c.label}</span>
                      {c.desc && <span className="block text-xs text-muted-foreground leading-tight mt-0.5">{c.desc}</span>}
                    </span>
                  </Link>
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
  const { count } = useCart();
  const { setOpen } = useCart();
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

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${scrolled ? "glass-strong shadow-2xl" : "bg-transparent"}`}
      data-testid="navbar"
    >
      <nav className="max-w-[88rem] mx-auto px-4 sm:px-6 h-[68px] flex items-center justify-between gap-2">
        <Link to="/" className="flex items-center gap-2 group flex-shrink-0" data-testid="nav-logo" onMouseEnter={() => play("hover")}>
          <img src={MEDIA.logo} alt="Isla Nublar LATAM" className="h-10 w-auto group-hover:scale-105 transition-transform" />
        </Link>

        <div className="hidden xl:flex items-center gap-0.5">
          {nav.map((item) =>
            item.type === "group" ? (
              <NavGroup key={item.id} item={item} activePath={activePath} play={play} />
            ) : (
              <Link
                key={item.to}
                to={item.to}
                data-testid={`nav-link-${item.id}`}
                onMouseEnter={() => play("hover")}
                onClick={() => play("click")}
                className={`relative px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${activePath === item.to ? "text-gold" : "text-muted-foreground hover:text-foreground"}`}
              >
                {item.label}
                {activePath === item.to && <motion.span layoutId="nav-active" className="absolute inset-x-3 -bottom-0.5 h-0.5 bg-gold rounded-full" />}
              </Link>
            )
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          <button
            onClick={() => { toggle(); play("click"); }}
            data-testid="sound-toggle"
            aria-label="Activar o desactivar sonido"
            className="p-2 rounded-lg text-muted-foreground hover:text-gold hover:bg-white/5 transition-colors"
          >
            {enabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
          </button>

          <button onClick={() => { setOpen(true); play("click"); }} data-testid="nav-cart" className="relative p-2 rounded-lg text-muted-foreground hover:text-gold hover:bg-white/5 transition-colors">
            <ShoppingCart size={18} />
            {count > 0 && <span className="absolute -top-0.5 -right-0.5 bg-crimson text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">{count}</span>}
          </button>

          {user ? (
            <div className="flex items-center gap-3">
              <BalanceHUD />
              <div className="relative hidden sm:block">
              <button
                onClick={() => { setProfileOpen((o) => !o); play("click"); }}
                onMouseEnter={() => play("hover")}
                data-testid="profile-menu-button"
                className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-full glass hover:border-gold/40 transition-colors"
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
              className="hidden sm:inline-flex items-center gap-2 bg-gold text-background font-bold text-sm px-4 py-2 rounded-lg hover:brightness-110 hover:gold-glow transition-all"
            >
              Iniciar sesión con Steam
            </button>
          )}

          <button onClick={() => { setMobile((m) => !m); play("click"); }} data-testid="mobile-menu-button" className="xl:hidden p-2 rounded-lg hover:bg-white/5">
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
                      onClick={() => { setOpenMobileGroup((g) => (g === item.id ? null : item.id)); play("click"); }}
                      data-testid={`mobile-group-trigger-${item.id}`}
                      className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5"
                    >
                      <span className="flex items-center gap-2"><item.icon size={16} className="text-gold" /> {item.label}</span>
                      <ChevronDown size={16} className={`transition-transform ${openMobileGroup === item.id ? "rotate-180" : ""}`} />
                    </button>
                    <AnimatePresence>
                      {openMobileGroup === item.id && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden pl-4 border-l border-white/10 ml-4">
                          {item.children.map((c) => (
                            <Link key={c.to} to={c.to} data-testid={`mobile-link-${c.id}`} className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm hover:bg-white/5 text-muted-foreground hover:text-foreground" onClick={() => play("click")}>
                              <c.icon size={15} /> {c.label}
                            </Link>
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
