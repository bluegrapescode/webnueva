import React, { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Volume2, VolumeX, ShoppingCart, Menu, X, LogOut, User as UserIcon, ChevronDown, Ticket } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { useCart } from "@/context/CartContext";
import { CoinChip } from "@/components/common/CoinChip";
import { BalanceHUD } from "@/components/common/BalanceHUD";
import { startSteamLogin } from "@/lib/api";

const LINKS = [
  { to: "/", id: "home", label: "Inicio" },
  { to: "/dashboard", id: "dashboard", label: "Panel" },
  { to: "/my-dino", id: "live-dino", label: "Dino en Vivo" },
  { to: "/store", id: "store", label: "Tienda" },
  { to: "/marketplace", id: "market", label: "Mercado" },
  // Sits beside the Mercado on purpose: the two lanes move the same animals and
  // a player looking for one will look where the other is.
  { to: "/intercambios", id: "trades", label: "Intercambios" },
  { to: "/battle-pass", id: "battlepass", label: "Pase de Batalla" },
  { to: "/quests", id: "quests", label: "Misiones" },
  { to: "/leaderboard", id: "leaderboard", label: "Clasificación" },
  { to: "/proximity-voice", id: "proximity-voice", label: "Radio de Proximidad" },
  { to: "/creator/dashboard", id: "creator", label: "Creators" },
];

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

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => { setMobile(false); setProfileOpen(false); }, [location.pathname]);

  const steamLogin = () => { play("click"); startSteamLogin(); };

  const navLinks = [
    ...LINKS,
    // Visible to every signed-in user: non-Patreons can preview the designer and get
    // the full explanation of how to unlock applying (the apply lane itself is gated).
    ...(user ? [{ to: "/skin-editor", id: "skin-lab", label: "Patreon" }] : []),
    // Renamed 2026-08-13 (owner ask): streamers were being flagged by the
    // platforms' gambling filters on the word "Casino". Label, heading and URL
    // all say Mini Juegos now; /casino still redirects so old links survive.
    ...(user ? [{ to: "/mini-juegos", id: "mini-juegos", label: "Mini Juegos" }] : []),
    ...(user?.role === "admin" ? [{ to: "/admin", id: "admin", label: "Admin" }] : []),
  ];

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${scrolled ? "glass-strong shadow-2xl" : "bg-transparent"}`}
      data-testid="navbar"
    >
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 h-[68px] flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 group" data-testid="nav-logo" onMouseEnter={() => play("hover")}>
          <img src={MEDIA.logo} alt="Isla Nublar LATAM" className="h-10 w-auto group-hover:scale-105 transition-transform" />
        </Link>

        <div className="hidden xl:flex items-center gap-1">
          {navLinks.map((l) => {
            const active = location.pathname === l.to;
            return (
              <Link
                key={l.to}
                to={l.to}
                data-testid={`nav-link-${l.id}`}
                onMouseEnter={() => play("hover")}
                onClick={() => play("click")}
                className={`relative px-4 py-2 text-sm font-semibold transition-colors ${active ? "text-gold" : "text-muted-foreground hover:text-foreground"}`}
              >
                {l.label}
                {active && (
                  <motion.span layoutId="nav-active" className="absolute inset-x-3 -bottom-0.5 h-0.5 bg-gold rounded-full" />
                )}
              </Link>
            );
          })}
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
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
            <div className="px-4 py-4 flex flex-col gap-1">
              {navLinks.map((l) => (
                <Link key={l.to} to={l.to} className="px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5" onClick={() => play("click")}>
                  {l.label}
                </Link>
              ))}
              {user ? (
                <Link to="/profile" className="px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/5" onClick={() => play("click")}>Perfil</Link>
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
